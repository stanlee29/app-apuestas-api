"""Almacenamiento e investigación histórica en Supabase REST.

La service-role key se consume exclusivamente desde el backend. Nunca se expone
al navegador ni al cliente móvil. Los datos históricos se consultan bajo demanda.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests


class ResearchStorageError(RuntimeError):
    """Error de comunicación o configuración del archivo histórico."""


class ResearchStorage:
    ARCHIVE_TABLES = (
        "historical_matches",
        "historical_match_features",
        "market_odds_summary",
        "team_identity_map",
        "event_identity_aliases",
        "research_snapshots",
    )

    def __init__(self, timeout: float = 12.0):
        self.url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        # Prefer the current sb_secret_ key. Keep legacy service_role support
        # for existing deployments while Supabase deprecates the old JWT keys.
        self.key = (
            os.getenv("SUPABASE_SECRET_KEY", "").strip()
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        )
        self.table = os.getenv("SUPABASE_RESEARCH_TABLE", "research_snapshots").strip()
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        if not self.url or not self.key:
            return False
        parsed = urlparse(self.url)
        valid_table = bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.table))
        return parsed.scheme == "https" and bool(parsed.netloc) and valid_table

    def status(self) -> dict[str, Any]:
        return {
            "proveedor": "Supabase REST",
            "configurado": self.configured,
            "tabla_snapshots": self.table,
            "tablas_archivo": list(self.ARCHIVE_TABLES),
            "modo": "servidor privado; clave secreta de Supabase" if self.configured else "desactivado",
            "nota": (
                "El archivo histórico de AppApuestas ya está preparado. "
                "Incluye resultados de fútbol y MLB, métricas avanzadas de fútbol, "
                "resúmenes de cuotas e identidades de equipos/eventos. "
                "La API lo consulta cuando SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY "
                "están configuradas en Render."
            ),
        }

    def _headers(self) -> dict[str, str]:
        if not self.configured:
            raise ResearchStorageError("Supabase no está configurado para AppApuestas.")
        headers = {
            "apikey": self.key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        # New sb_secret_ keys are not JWTs: send them only as apikey.
        # Legacy service_role keys are JWTs and retain Authorization support.
        if not self.key.startswith("sb_secret_"):
            headers["Authorization"] = "Bearer " + self.key
        return headers

    def _get_rows(self, table: str, params: dict[str, str], context: str) -> list[dict[str, Any]]:
        if not self.configured:
            raise ResearchStorageError("Supabase no está configurado para AppApuestas.")
        if table not in self.ARCHIVE_TABLES and table != self.table:
            raise ValueError("Tabla de archivo no permitida.")
        try:
            response = requests.get(
                f"{self.url}/rest/v1/{table}",
                params=params,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ResearchStorageError(f"No se pudo consultar {context} en Supabase.") from exc
        if response.status_code >= 400:
            raise ResearchStorageError(
                f"Supabase rechazó la consulta de {context} (HTTP {response.status_code})."
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise ResearchStorageError(f"Supabase devolvió JSON no válido al consultar {context}.") from exc
        return data if isinstance(data, list) else []

    @staticmethod
    def _team_or_filter(team_names: str | list[str] | tuple[str, ...]) -> str:
        values = [team_names] if isinstance(team_names, str) else list(team_names)
        cleaned: list[str] = []
        for value in values:
            team = " ".join(str(value or "").split())
            # Validate every candidate before building a PostgREST OR filter.
            if not team or len(team) > 100 or not re.fullmatch(r"[\w\s.\-'’&]+", team, flags=re.UNICODE):
                raise ValueError("Nombre de equipo inválido.")
            if team.casefold() not in {item.casefold() for item in cleaned}:
                cleaned.append(team)
        if not cleaned or len(cleaned) > 8:
            raise ValueError("Lista de nombres de equipo inválida.")
        clauses = []
        for team in cleaned:
            quoted = team.replace("\\", "\\\\").replace('"', '\\"')
            clauses.extend((f'home_team.eq."{quoted}"', f'away_team.eq."{quoted}"'))
        return "(" + ",".join(clauses) + ")"

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number == number and abs(number) != float("inf") else None

    def save_snapshot(
        self,
        provider: str,
        match_id: str,
        snapshot_type: str,
        payload: dict[str, Any],
        source_timestamp: str | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            return {"guardado": False, "motivo": "SUPABASE_NOT_CONFIGURED"}
        if not provider or not match_id or not snapshot_type:
            raise ValueError("provider, match_id y snapshot_type son obligatorios.")
        snapshot_date = datetime.now(timezone.utc).date().isoformat()
        row = {
            "provider": provider[:40],
            "match_id": str(match_id)[:100],
            "snapshot_type": snapshot_type[:60],
            "snapshot_date": snapshot_date,
            "source_timestamp": source_timestamp,
            "model_version": os.getenv("APP_MODEL_VERSION", "research-1"),
            "payload": payload,
        }
        try:
            response = requests.post(
                f"{self.url}/rest/v1/{self.table}",
                params={"on_conflict": "provider,match_id,snapshot_type,snapshot_date"},
                headers=self._headers(),
                json=row,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ResearchStorageError("No se pudo guardar el snapshot en Supabase.") from exc
        if response.status_code >= 400:
            raise ResearchStorageError(
                f"Supabase rechazó el snapshot (HTTP {response.status_code}). "
                "Revisa la migración y las variables del servicio."
            )
        return {
            "guardado": True,
            "provider": row["provider"],
            "match_id": row["match_id"],
            "snapshot_date": snapshot_date,
        }

    def history(self, provider: str, match_id: str, limit: int = 30) -> list[dict[str, Any]]:
        safe_limit = max(1, min(100, int(limit)))
        return self._get_rows(
            self.table,
            {
                "select": "provider,match_id,snapshot_type,snapshot_date,source_timestamp,model_version,payload",
                "provider": "eq." + provider,
                "match_id": "eq." + str(match_id),
                "order": "snapshot_date.desc",
                "limit": str(safe_limit),
            },
            "el historial de snapshots",
        )

    def team_archive(
        self,
        team_name: str,
        before_date: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        requested_team = " ".join(str(team_name or "").split())
        if not requested_team:
            raise ValueError("Nombre de equipo inválido.")
        safe_limit = max(1, min(20, int(limit)))
        cutoff = date.fromisoformat(before_date).isoformat() if before_date else date.today().isoformat()

        # Resolve known provider aliases (for example canonical GanaPlay name
        # to FotMob display name) before searching archives with exact names.
        identity_rows = self._get_rows(
            "team_identity_map",
            {
                "select": "provider,provider_team_id,canonical_team_name,provider_team_name,confidence",
                "or": (
                    "(canonical_team_name.eq." + '"' + requested_team + '"' +
                    ",provider_team_name.eq." + '"' + requested_team + '"' + ")"
                ),
                "confidence": "gte.0.90",
                "limit": "8",
            },
            "el mapa de identidades de equipos",
        )
        candidates = [requested_team]
        for identity in identity_rows:
            for candidate in (identity.get("canonical_team_name"), identity.get("provider_team_name")):
                if candidate and str(candidate).casefold() not in {item.casefold() for item in candidates}:
                    candidates.append(str(candidate))
        team_filter = self._team_or_filter(candidates)

        result_params = {
            "select": "source,competition_name,season,match_date,home_team,away_team,home_goals,away_goals,ht_home_goals,ht_away_goals,stats",
            "source": "eq.Football-Data.co.uk",
            "or": team_filter,
            "match_date": "lt." + cutoff,
            "order": "match_date.desc",
            "limit": str(safe_limit),
        }
        result_rows = self._get_rows("historical_matches", result_params, "los resultados históricos")

        feature_params = {
            "select": (
                "source,source_license,competition_name,season_name,match_date,"
                "home_team,away_team,home_score,away_score,home_xg,away_xg,"
                "home_shots,away_shots,home_shots_on_target,away_shots_on_target,"
                "home_corners,away_corners,home_yellow_cards,away_yellow_cards,"
                "home_red_cards,away_red_cards"
            ),
            "source": "in.(american_soccer_analysis,statsbomb_open)",
            "or": team_filter,
            "match_date": "lt." + cutoff,
            "order": "match_date.desc",
            "limit": str(min(40, safe_limit * 2)),
        }
        feature_rows = self._get_rows(
            "historical_match_features", feature_params, "las métricas avanzadas históricas"
        )

        matches: list[dict[str, Any]] = []
        wins = draws = losses = 0
        goals_for: list[float] = []
        goals_against: list[float] = []
        shots_for: list[float] = []
        shots_against: list[float] = []
        for row in result_rows:
            home_team = str(row.get("home_team") or "")
            away_team = str(row.get("away_team") or "")
            is_home = home_team.casefold() == team_name.strip().casefold()
            own_score = self._number(row.get("home_goals" if is_home else "away_goals"))
            opp_score = self._number(row.get("away_goals" if is_home else "home_goals"))
            stats = row.get("stats") if isinstance(row.get("stats"), dict) else {}
            prefix = "h" if is_home else "a"
            opponent_prefix = "a" if is_home else "h"
            own_shots = self._number(stats.get(prefix + "s"))
            opp_shots = self._number(stats.get(opponent_prefix + "s"))
            if own_score is not None and opp_score is not None:
                goals_for.append(own_score)
                goals_against.append(opp_score)
                if own_score > opp_score:
                    result = "G"
                    wins += 1
                elif own_score < opp_score:
                    result = "P"
                    losses += 1
                else:
                    result = "E"
                    draws += 1
            else:
                result = None
            if own_shots is not None:
                shots_for.append(own_shots)
            if opp_shots is not None:
                shots_against.append(opp_shots)
            matches.append({
                "fuente": row.get("source"),
                "competicion": row.get("competition_name"),
                "temporada": row.get("season"),
                "fecha": row.get("match_date"),
                "condicion": "local" if is_home else "visitante",
                "equipo": requested_team,
                "nombre_en_fuente": home_name if is_home else away_name,
                "rival": away_team if is_home else home_team,
                "marcador": f"{int(own_score)}-{int(opp_score)}" if own_score is not None and opp_score is not None else None,
                "resultado": result,
                "goles_favor": own_score,
                "goles_contra": opp_score,
                "remates_favor": own_shots,
                "remates_contra": opp_shots,
                "remates_puerta_favor": self._number(stats.get(prefix + "st")),
                "remates_puerta_contra": self._number(stats.get(opponent_prefix + "st")),
                "corners_favor": self._number(stats.get(prefix + "c")),
                "corners_contra": self._number(stats.get(opponent_prefix + "c")),
                "amarillas_favor": self._number(stats.get(prefix + "y")),
                "amarillas_contra": self._number(stats.get(opponent_prefix + "y")),
                "rojas_favor": self._number(stats.get(prefix + "r")),
                "rojas_contra": self._number(stats.get(opponent_prefix + "r")),
            })

        def average(values: list[float]) -> float | None:
            return round(sum(values) / len(values), 3) if values else None

        advanced = []
        for row in feature_rows:
            home_name = str(row.get("home_team") or "")
            away_name = str(row.get("away_team") or "")
            matched_names = {candidate.casefold() for candidate in candidates}
            is_home = home_name.casefold() in matched_names
            is_away = away_name.casefold() in matched_names
            if not is_home and not is_away:
                continue
            if is_home and is_away:
                # Ambiguous same-name fixture: do not assign arbitrary venue stats.
                continue
            advanced.append({
                "fuente": row.get("source"),
                "licencia": row.get("source_license"),
                "competicion": row.get("competition_name"),
                "temporada": row.get("season_name"),
                "fecha": row.get("match_date"),
                "rival": row.get("away_team") if is_home else row.get("home_team"),
                "condicion": "local" if is_home else "visitante",
                "goles_favor": row.get("home_score") if is_home else row.get("away_score"),
                "goles_contra": row.get("away_score") if is_home else row.get("home_score"),
                "xg_favor": row.get("home_xg") if is_home else row.get("away_xg"),
                "xg_contra": row.get("away_xg") if is_home else row.get("home_xg"),
                "remates_favor": row.get("home_shots") if is_home else row.get("away_shots"),
                "remates_contra": row.get("away_shots") if is_home else row.get("home_shots"),
                "remates_puerta_favor": row.get("home_shots_on_target") if is_home else row.get("away_shots_on_target"),
                "remates_puerta_contra": row.get("away_shots_on_target") if is_home else row.get("home_shots_on_target"),
                "corners_favor": row.get("home_corners") if is_home else row.get("away_corners"),
                "corners_contra": row.get("away_corners") if is_home else row.get("home_corners"),
                "amarillas_favor": row.get("home_yellow_cards") if is_home else row.get("away_yellow_cards"),
                "amarillas_contra": row.get("away_yellow_cards") if is_home else row.get("home_yellow_cards"),
            })

        return {
            "equipo": requested_team,
            "nombres_alternativos": candidates[1:],
            "identidades_verificadas": identity_rows,
            "antes_de": cutoff,
            "fuente_resultados": "Football-Data.co.uk",
            "partidos": matches,
            "resumen": {
                "partidos": len(matches),
                "ganados": wins,
                "empatados": draws,
                "perdidos": losses,
                "goles_favor_promedio": average(goals_for),
                "goles_contra_promedio": average(goals_against),
                "remates_favor_promedio": average(shots_for),
                "remates_contra_promedio": average(shots_against),
            },
            "fuente_metricas_avanzadas": ["American Soccer Analysis", "StatsBomb Open Data"],
            "metricas_avanzadas": advanced,
            "cobertura": {
                "resultados": len(matches),
                "metricas_avanzadas": len(advanced),
                "xg": sum(1 for row in advanced if row.get("xg_favor") is not None and row.get("xg_contra") is not None),
            },
            "nota": (
                "El historial usa partidos anteriores a la fecha de corte. "
                "Las métricas avanzadas solo aparecen donde la fuente las publicó; "
                "no se rellenan valores ausentes con cero."
            ),
        }

    def market_archive(self, event_id: str, limit: int = 50) -> dict[str, Any]:
        selected_id = str(event_id or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9:_-]{1,120}", selected_id):
            raise ValueError("Identificador de evento inválido.")
        safe_limit = max(1, min(100, int(limit)))
        event_ids = [selected_id]
        aliases = self._get_rows(
            "event_identity_aliases",
            {
                "select": "canonical_event_id",
                "alias_event_id": "eq." + selected_id,
                "limit": "1",
            },
            "el mapa de identificadores de eventos",
        )
        if aliases:
            canonical = aliases[0].get("canonical_event_id")
            if canonical and canonical not in event_ids:
                event_ids.append(str(canonical))

        markets: list[dict[str, Any]] = []
        for selected in event_ids:
            rows = self._get_rows(
                "market_odds_summary",
                {
                    "select": (
                        "event_id,sport,league,home_team,away_team,market_key,selection,line,"
                        "bookmaker,provider,snapshot_phase,opening_odds,closing_odds,min_odds,"
                        "max_odds,average_odds,opening_implied_probability,closing_implied_probability,"
                        "opening_fair_probability,closing_fair_probability,average_overround,"
                        "closing_clv_probability_pp,closing_price_dislocation_pct,first_observed_at,"
                        "last_observed_at,kickoff_utc,is_closing_line,is_closing_snapshot,snapshot_count"
                    ),
                    "event_id": "eq." + selected,
                    "order": "last_observed_at.desc",
                    "limit": str(safe_limit),
                },
                "los resúmenes históricos de cuotas",
            )
            markets.extend(rows)
        return {
            "event_id": selected_id,
            "event_ids_consultados": event_ids,
            "total": len(markets),
            "mercados": markets[:safe_limit],
            "nota": (
                "Se conservan precios de apertura/cierre, rangos y cantidad de observaciones. "
                "No es una secuencia completa tick a tick; la probabilidad justa solo se muestra "
                "cuando la fuente la almacenó."
            ),
        }
