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
MAX_CACHE_ENTRIES = 1200
_RATE_LIMIT_UNTIL = 0.0
_RATE_LIMIT_LOCK = threading.Lock()
try:
    CACHE_SECONDS = max(30, int(os.getenv("PITCHAPI_CACHE_SECONDS", "300")))
except (TypeError, ValueError):
    CACHE_SECONDS = 300


def _cache_read(key: str, now: float, ttl: int) -> tuple[bool, Any]:
    if ttl <= 0:
        return False, None
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is None:
            return False, None
        if now - cached[0] >= ttl:
            _CACHE.pop(key, None)
            return False, None
        return True, cached[1]


def _cache_write(key: str, value: Any, now: float, ttl: int) -> None:
    if ttl <= 0:
        return
    with _CACHE_LOCK:
        _CACHE[key] = (now, value)
        while len(_CACHE) > MAX_CACHE_ENTRIES:
            _CACHE.pop(next(iter(_CACHE)), None)


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
        global _RATE_LIMIT_UNTIL
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
        # Las respuestas recientes en caché se pueden seguir sirviendo durante
        # una pausa por 429; el limitador solo bloquea peticiones a la red.
        found, cached_value = _cache_read(cache_key, now, ttl)
        if found:
            return cached_value
        with _RATE_LIMIT_LOCK:
            retry_in = max(0, int(_RATE_LIMIT_UNTIL - now))
        if retry_in > 0:
            raise PitchAPIError(
                f"PitchAPI está en pausa local por límite de solicitudes. Reintenta en {retry_in} segundos.",
                status_code=503,
                code="PITCHAPI_RATE_LIMIT",
            )

        try:
            response = self.session.get(
                BASE_URL + clean_path,
                params=params or {},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise PitchAPIError(f"No fue posible conectar con PitchAPI: {exc}") from exc

        if response.status_code == 404 and optional:
            # 404 opcional incluye ANALYTICS_UNAVAILABLE: el partido existe,
            # pero no dispone de feed avanzado. Se guarda para evitar reintentos.
            _cache_write(cache_key, None, now, ttl)
            return None
        if response.status_code == 401:
            raise PitchAPIError(
                "PitchAPI rechazó la clave. Revisa PITCHAPI_API_KEY en Render.",
                status_code=502,
                code="PITCHAPI_UNAUTHORIZED",
            )
        if response.status_code == 429:
            retry_header = response.headers.get("Retry-After", "60")
            try:
                retry_seconds = max(10, min(600, int(retry_header)))
            except (TypeError, ValueError):
                retry_seconds = 60
            with _RATE_LIMIT_LOCK:
                _RATE_LIMIT_UNTIL = max(_RATE_LIMIT_UNTIL, time.monotonic() + retry_seconds)
            raise PitchAPIError(
                f"PitchAPI alcanzó su límite de consultas. El conector pausó nuevas llamadas durante {retry_seconds} segundos.",
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
        _cache_write(cache_key, data, now, ttl)
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
        # La ficha del partido es obligatoria. El resto de bloques son opcionales:
        # una liga/partido puede tener marcador sin disponer de eventos avanzados.
        match = self._get(f"/matches/{encoded}")
        warnings: list[dict[str, str]] = []
        upstream_paused = False

        def optional_block(name: str, path: str, params: dict[str, Any] | None = None) -> Any:
            nonlocal upstream_paused
            if upstream_paused:
                return {}
            try:
                return self._get(path, params, optional=True) or {}
            except PitchAPIError as exc:
                # No ocultamos la ficha obligatoria; preservamos el informe principal.
                if exc.code in {"PITCHAPI_UNAUTHORIZED", "PITCHAPI_NOT_CONFIGURED"}:
                    raise
                warnings.append({
                    "bloque": name,
                    "codigo": exc.code,
                    "mensaje": str(exc),
                })
                if exc.code == "PITCHAPI_RATE_LIMIT":
                    upstream_paused = True
                return {}

        shots_data = optional_block("remates", f"/matches/{encoded}/shots")
        stats_data = optional_block("estadisticas_equipo", f"/matches/{encoded}/stats")
        players_data = optional_block("estadisticas_jugadores", f"/matches/{encoded}/players")
        h2h_data = optional_block("h2h", f"/matches/{encoded}/h2h")
        heatmaps_data = optional_block(
            "mapas_calor", f"/matches/{encoded}/heatmaps", {"frame": "home_ltr"}
        )
        advanced_data = optional_block("analitica_avanzada", f"/matches/{encoded}/advanced")
        advanced_players_data = optional_block(
            "analitica_avanzada_jugadores", f"/matches/{encoded}/advanced/players"
        )
        network_data = optional_block("red_pases", f"/matches/{encoded}/advanced/network")
        lineups_data = optional_block("alineaciones", f"/matches/{encoded}/lineups")
        events_data = optional_block("eventos", f"/matches/{encoded}/events")
        momentum_data = optional_block("momentum", f"/matches/{encoded}/momentum")

        periods = shots_data.get("periods", []) if isinstance(shots_data, dict) else []
        shots: list[dict[str, Any]] = []
        for period in periods if isinstance(periods, list) else []:
            if not isinstance(period, dict):
                continue
            for shot in period.get("shots", []) if isinstance(period.get("shots"), list) else []:
                if not isinstance(shot, dict):
                    continue
                item = dict(shot)
                item.setdefault("period", period.get("period"))
                # Coordenadas documentadas en metros (105 x 68), con dirección
                # normalizada por PitchAPI: no invertir el visitante en el cliente.
                for axis, upper in (("x", 105.0), ("y", 68.0)):
                    try:
                        value = float(item[axis]) if item.get(axis) is not None else None
                    except (TypeError, ValueError):
                        value = None
                    item[axis] = value if value is not None and 0 <= value <= upper else None
                try:
                    item["expected_goals"] = (
                        float(item["expected_goals"])
                        if item.get("expected_goals") is not None else None
                    )
                except (TypeError, ValueError):
                    item["expected_goals"] = None
                shots.append(item)

        home = match.get("home_team") or {}
        away = match.get("away_team") or {}
        home_id, away_id = home.get("id"), away.get("id")

        def summarize_team(team_id: Any) -> dict[str, Any]:
            team_shots = [
                shot for shot in shots
                if str(shot.get("team_id") or "") == str(team_id or "")
            ]
            xg_values = [
                shot["expected_goals"] for shot in team_shots
                if isinstance(shot.get("expected_goals"), (int, float))
            ]
            return {
                "remates": len(team_shots),
                "remates_a_puerta": sum(1 for shot in team_shots if shot.get("is_on_target") is True),
                "goles_en_remates": sum(
                    1 for shot in team_shots
                    if str(shot.get("event_type") or "").casefold() == "goal"
                ),
                "xg": round(sum(xg_values), 4) if xg_values else None,
                "xg_por_remate": round(sum(xg_values) / len(xg_values), 4) if xg_values else None,
                "remates_con_xg": len(xg_values),
            }

        # Solo mostramos el periodo All como estadísticas completas. Si el proveedor
        # no lo publica, no etiquetamos la primera mitad como si fuese el partido entero.
        stats: list[dict[str, Any]] = []
        periods_stats = stats_data.get("periods", []) if isinstance(stats_data, dict) else []
        all_period = next(
            (
                period for period in periods_stats
                if isinstance(period, dict) and str(period.get("period") or "").casefold() == "all"
            ),
            None,
        ) if isinstance(periods_stats, list) else None
        for group in all_period.get("groups", []) if isinstance(all_period, dict) else []:
            if not isinstance(group, dict):
                continue
            for item in group.get("items", []) if isinstance(group.get("items"), list) else []:
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

        player_stats = (
            players_data if isinstance(players_data, list)
            else players_data.get("players", []) if isinstance(players_data, dict)
            else []
        )
        advanced_player_stats = (
            advanced_players_data if isinstance(advanced_players_data, list)
            else advanced_players_data.get("players", []) if isinstance(advanced_players_data, dict)
            else []
        )
        heatmap_teams = heatmaps_data.get("teams", []) if isinstance(heatmaps_data, dict) else []
        heatmap_players = heatmaps_data.get("players", []) if isinstance(heatmaps_data, dict) else []
        pass_networks = network_data.get("networks", []) if isinstance(network_data, dict) else []
        advanced_teams = advanced_data.get("teams", []) if isinstance(advanced_data, dict) else []
        events = events_data if isinstance(events_data, list) else (
            events_data.get("events", []) if isinstance(events_data, dict) else []
        )
        momentum_points = momentum_data if isinstance(momentum_data, list) else (
            momentum_data.get("points", []) if isinstance(momentum_data, dict) else []
        )

        availability = {
            "remates_xg": bool(shots),
            "estadisticas_equipo": bool(stats),
            "estadisticas_jugadores": bool(player_stats),
            "h2h": bool(h2h_data.get("recent_matches")) if isinstance(h2h_data, dict) else bool(h2h_data),
            "mapas_calor": bool(heatmap_teams or heatmap_players),
            "analitica_avanzada": bool(advanced_teams),
            "analitica_avanzada_jugadores": bool(advanced_player_stats),
            "red_pases": bool(pass_networks),
            "alineaciones": bool(
                lineups_data.get("home") or lineups_data.get("away")
            ) if isinstance(lineups_data, dict) else bool(lineups_data),
            "eventos": bool(events),
            "momentum": bool(momentum_points),
        }
        not_available = [name for name, available in availability.items() if not available]

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
            "estadisticas_por_tiempo": stats_data.get("stats_halves", {}) if isinstance(stats_data, dict) else {},
            "estadisticas_jugadores": player_stats,
            "analitica_avanzada_jugadores": advanced_player_stats,
            "h2h": h2h_data,
            "mapas_calor": heatmaps_data,
            "red_pases": network_data,
            "alineaciones": lineups_data,
            "analitica_avanzada": advanced_data,
            "eventos": events,
            "momentum": momentum_points,
            "disponibilidad": availability,
            "bloques_sin_cobertura": not_available,
            "advertencias": warnings,
            "consultado_en": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "nota": (
                "xG procede del modelo de PitchAPI. No mezcles xG, xT o VAEP de proveedores "
                "distintos como si fueran la misma métrica. ANALYTICS_UNAVAILABLE significa "
                "que existe el partido pero no fue calificado con feed de eventos."
            ),
        }


def pitchapi_status() -> dict[str, Any]:
    configured = bool(os.getenv("PITCHAPI_API_KEY", "").strip())
    with _RATE_LIMIT_LOCK:
        retry_in = max(0, int(_RATE_LIMIT_UNTIL - time.monotonic()))
    return {
        "proveedor": "PitchAPI",
        "configurado": configured,
        "rate_limit_activo": retry_in > 0,
        "reintento_en_segundos": retry_in,
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
