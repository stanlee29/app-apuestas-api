"""Integración oficial de PitchAPI para análisis avanzado de fútbol.

La clave se mantiene exclusivamente en Render mediante PITCHAPI_API_KEY.
No se incrusta en Flutter ni en el repositorio.
"""
from __future__ import annotations

import os
import re
import threading
import time
from datetime import date
from typing import Any
from urllib.parse import quote

import requests


BASE_URL = "https://api.pitchapi.dev/v1"
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = threading.Lock()
CACHE_SECONDS = max(30, int(os.getenv("PITCHAPI_CACHE_SECONDS", "300")))


class PitchAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502, code: str = "PITCHAPI_ERROR"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class PitchAPIClient:
    def __init__(self, api_key: str | None = None, timeout: float = 20.0):
        self.api_key = (api_key if api_key is not None else os.getenv("PITCHAPI_API_KEY", "")).strip()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "X-API-KEY": self.api_key,
            "User-Agent": "AppApuestas-Research/1.0",
        })

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        optional: bool = False,
        cache_seconds: int | None = None,
    ) -> Any:
        if not self.configured:
            raise PitchAPIError(
                "PitchAPI aún no está conectado. Crea una clave gratuita y guárdala en Render "
                "como variable privada PITCHAPI_API_KEY.",
                status_code=503,
                code="PITCHAPI_NOT_CONFIGURED",
            )

        clean_path = "/" + path.lstrip("/")
        query = tuple(sorted((str(k), str(v)) for k, v in (params or {}).items() if v is not None))
        cache_key = clean_path + repr(query)
        now = time.monotonic()
        ttl = CACHE_SECONDS if cache_seconds is None else max(0, cache_seconds)
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if ttl > 0 and cached and now - cached[0] < ttl:
                return cached[1]

        try:
            response = self.session.get(
                BASE_URL + clean_path,
                params=params or {},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise PitchAPIError(f"No fue posible conectar con PitchAPI: {exc}") from exc

        if response.status_code == 404 and optional:
            return None
        if response.status_code == 401:
            raise PitchAPIError(
                "PitchAPI rechazó la clave. Revisa PITCHAPI_API_KEY en Render.",
                status_code=502,
                code="PITCHAPI_UNAUTHORIZED",
            )
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "unos segundos")
            raise PitchAPIError(
                f"PitchAPI solicitó reducir la frecuencia de consulta. Reintenta después de {retry_after}.",
                status_code=503,
                code="PITCHAPI_RATE_LIMIT",
            )
        if response.status_code >= 500:
            raise PitchAPIError(
                f"PitchAPI presenta un error temporal (HTTP {response.status_code}).",
                status_code=502,
                code="PITCHAPI_UPSTREAM_ERROR",
            )
        if response.status_code >= 400:
            try:
                error = response.json().get("error", {})
                message = error.get("message") or error.get("code") or response.reason
                code = error.get("code") or "PITCHAPI_BAD_REQUEST"
            except (ValueError, AttributeError):
                message, code = response.reason, "PITCHAPI_BAD_REQUEST"
            raise PitchAPIError(
                f"PitchAPI: {message}",
                status_code=502,
                code=code,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise PitchAPIError("PitchAPI devolvió una respuesta que no es JSON.") from exc

        if not isinstance(payload, dict) or "error" in payload:
            raw_error = payload.get("error", {}) if isinstance(payload, dict) else {}
            error = raw_error if isinstance(raw_error, dict) else {"message": str(raw_error)}
            raise PitchAPIError(
                str(error.get("message") or "Respuesta no válida de PitchAPI."),
                code=str(error.get("code") or "PITCHAPI_BAD_RESPONSE"),
            )

        data = payload.get("data", payload)
        if ttl > 0:
            with _CACHE_LOCK:
                _CACHE[cache_key] = (now, data)
        return data

    def list_leagues(self) -> list[dict[str, Any]]:
        data = self._get("/leagues")
        leagues = data.get("leagues", []) if isinstance(data, dict) else []
        return leagues if isinstance(leagues, list) else []

    def matches_by_date(self, day: str, status: str = "all") -> dict[str, Any]:
        parsed = date.fromisoformat(day)
        if status not in {"played", "upcoming", "all"}:
            raise ValueError("status debe ser played, upcoming o all.")
        data = self._get(f"/date/{parsed.isoformat()}", {"status": status})
        return data if isinstance(data, dict) else {}

    def league_matches(
        self,
        league_id: str,
        season: str | None = None,
        status: str = "all",
    ) -> dict[str, Any]:
        if not re.fullmatch(r"l_[A-Za-z0-9]{6}", league_id):
            raise ValueError("Identificador de liga PitchAPI no válido.")
        if status not in {"played", "upcoming", "all"}:
            raise ValueError("status debe ser played, upcoming o all.")
        data = self._get(
            f"/leagues/{quote(league_id, safe='')}/matches",
            {"season": season, "status": status},
        )
        return data if isinstance(data, dict) else {}

    def match_live(self, match_id: str) -> dict[str, Any]:
        self._validate_match_id(match_id)
        # El proveedor indica que el endpoint live no se consulte a intervalos menores de 10 s.
        # Una caché de 10 s evita solicitar snapshots más rápido que ese intervalo.
        data = self._get(f"/matches/{quote(match_id, safe='')}/live", cache_seconds=10)
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _validate_match_id(match_id: str) -> None:
        if not re.fullmatch(r"m_[A-Za-z0-9]{6}", match_id):
            raise ValueError("Identificador de partido PitchAPI no válido.")

    def match_analysis(self, match_id: str) -> dict[str, Any]:
        self._validate_match_id(match_id)
        encoded = quote(match_id, safe="")
        match = self._get(f"/matches/{encoded}")
        shots_data = self._get(f"/matches/{encoded}/shots", optional=True) or {}
        stats_data = self._get(f"/matches/{encoded}/stats", optional=True) or {}
        players_data = self._get(f"/matches/{encoded}/players", optional=True) or {}
        h2h_data = self._get(f"/matches/{encoded}/h2h", optional=True) or {}
        heatmaps_data = self._get(
            f"/matches/{encoded}/heatmaps", {"frame": "home_ltr"}, optional=True
        ) or {}
        advanced_data = self._get(f"/matches/{encoded}/advanced", optional=True) or {}
        advanced_players_data = self._get(f"/matches/{encoded}/advanced/players", optional=True) or {}
        network_data = self._get(f"/matches/{encoded}/advanced/network", optional=True) or {}
        lineups_data = self._get(f"/matches/{encoded}/lineups", optional=True) or {}
        events_data = self._get(f"/matches/{encoded}/events", optional=True) or {}
        momentum_data = self._get(f"/matches/{encoded}/momentum", optional=True) or {}

        periods = shots_data.get("periods", []) if isinstance(shots_data, dict) else []
        shots: list[dict[str, Any]] = []
        for period in periods if isinstance(periods, list) else []:
            for shot in period.get("shots", []) if isinstance(period, dict) else []:
                if isinstance(shot, dict):
                    item = dict(shot)
                    item.setdefault("period", period.get("period"))
                    shots.append(item)

        home = match.get("home_team") or {}
        away = match.get("away_team") or {}
        home_id, away_id = home.get("id"), away.get("id")

        def summarize_team(team_id: Any) -> dict[str, Any]:
            team_shots = [s for s in shots if s.get("team_id") == team_id]
            xg_values = [
                float(s["expected_goals"])
                for s in team_shots
                if isinstance(s.get("expected_goals"), (int, float))
            ]
            return {
                "remates": len(team_shots),
                "remates_a_puerta": sum(1 for s in team_shots if s.get("is_on_target") is True),
                "goles_en_remates": sum(1 for s in team_shots if str(s.get("event_type", "")).casefold() == "goal"),
                "xg": round(sum(xg_values), 4) if xg_values else None,
                "xg_por_remate": round(sum(xg_values) / len(xg_values), 4) if xg_values else None,
            }

        stats: list[dict[str, Any]] = []
        periods_stats = stats_data.get("periods", []) if isinstance(stats_data, dict) else []
        if isinstance(periods_stats, list):
            # El endpoint entrega grupos por periodo ("All", "FirstHalf", "SecondHalf").
            # Priorizamos "All" para no duplicar las métricas de las dos mitades.
            all_period = next(
                (period for period in periods_stats if isinstance(period, dict) and period.get("period") == "All"),
                periods_stats[0] if periods_stats else {},
            )
            for group in all_period.get("groups", []) if isinstance(all_period, dict) else []:
                if not isinstance(group, dict):
                    continue
                for item in group.get("items", []):
                    if not isinstance(item, dict):
                        continue
                    stats.append({
                        "grupo": group.get("group_name"),
                        "key": item.get("key"),
                        "title": item.get("title"),
                        "home": item.get("home"),
                        "away": item.get("away"),
                        "format_type": item.get("format_type"),
                    })

        return {
            "fuente": "PitchAPI",
            "partido": match,
            "metricas_calculadas_desde_remates": {
                "local": summarize_team(home_id),
                "visitante": summarize_team(away_id),
            },
            "remates": shots,
            "estadisticas_equipo": stats,
            "estadisticas_equipo_raw": stats_data,
            "estadisticas_jugadores": players_data.get("players", []) if isinstance(players_data, dict) else [],
            "analitica_avanzada_jugadores": advanced_players_data.get("players", []) if isinstance(advanced_players_data, dict) else [],
            "h2h": h2h_data,
            "mapas_calor": heatmaps_data,
            "red_pases": network_data,
            "alineaciones": lineups_data,
            "analitica_avanzada": advanced_data,
            "eventos": events_data.get("events", []) if isinstance(events_data, dict) else [],
            "momentum": momentum_data.get("points", []) if isinstance(momentum_data, dict) else [],
            "disponibilidad": {
                "remates_xg": bool(shots),
                "estadisticas_equipo": bool(stats),
                "estadisticas_jugadores": bool(players_data),
                "h2h": bool(h2h_data),
                "mapas_calor": bool(heatmaps_data),
                "analitica_avanzada": bool(advanced_data),
                "analitica_avanzada_jugadores": bool(advanced_players_data),
                "red_pases": bool(network_data),
                "alineaciones": bool(lineups_data),
                "eventos": bool(events_data),
                "momentum": bool(momentum_data),
            },
            "nota": (
                "Las métricas xG y los datos de remates corresponden al modelo de PitchAPI. "
                "No deben mezclarse como si fueran iguales con xG calculados por otros proveedores."
            ),
        }


def pitchapi_status() -> dict[str, Any]:
    configured = bool(os.getenv("PITCHAPI_API_KEY", "").strip())
    return {
        "proveedor": "PitchAPI",
        "configurado": configured,
        "tipo_datos": [
            "77 ligas de fútbol en catálogo (según documentación del proveedor)",
            "fixtures e históricos desde 2021",
            "remates con xG y coordenadas",
            "estadísticas de equipos y jugadores",
            "H2H",
            "mapas de calor de equipos y jugadores",
            "momentum y eventos",
            "analítica avanzada",
        ],
        "clave_requerida": True,
        "url_clave_gratuita": "https://pitchapi.dev/",
        "documentacion": "https://pitchapi.dev/",
        "nota": (
            "La fuente requiere una clave gratuita configurada en el backend. "
            "La disponibilidad de xG, mapas y analítica avanzada depende de la cobertura del partido."
        ),
    }
