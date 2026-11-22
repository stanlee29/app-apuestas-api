"""Cliente de la API pública gratuita TheSportsDB.

Se utiliza como fuente auxiliar: sus límites gratuitos y la cobertura de cada
competición impiden tratarla como un feed completo o como fuente principal.
"""
from __future__ import annotations

import threading
import time
from datetime import date
from typing import Any

import requests

BASE_URL = "https://www.thesportsdb.com/api/v1/json/123"
CACHE: dict[str, tuple[float, Any]] = {}
CACHE_LOCK = threading.Lock()
REQUEST_LOCK = threading.Lock()
_LAST_REQUEST = 0.0
MIN_REQUEST_INTERVAL = 2.05
MAX_CACHE_ENTRIES = 250
ENDPOINTS = {
    "eventsday.php",
    "lookupevent.php",
    "lookuplineup.php",
    "lookupeventstats.php",
    "lookuptimeline.php",
    "lookup_all_players.php",
}


class TheSportsDBError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502, code: str = "THESPORTSDB_ERROR"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def thesportsdb_status() -> dict[str, Any]:
    return {
        "fuente": "TheSportsDB API v1",
        "disponible": True,
        "requiere_clave_propia": False,
        "clave": "pública compartida",
        "limite_publicado": "30 solicitudes por minuto",
        "estado": "auxiliar",
        "advertencia": "La API limita resultados por endpoint y no tiene cobertura completa en todas las ligas.",
    }


def _int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def normalize_event(raw: dict[str, Any]) -> dict[str, Any]:
    status_text = str(raw.get("strStatus") or "").upper()
    if raw.get("strPostponed") == "yes":
        status = "postponed"
    elif status_text in {"FT", "AET", "PEN", "FINAL"}:
        status = "finished"
    elif status_text in {"1H", "2H", "HT", "ET", "P", "LIVE"}:
        status = "live"
    else:
        status = "scheduled"
    return {
        "id": str(raw.get("idEvent") or ""),
        "league": raw.get("strLeague"),
        "date": raw.get("strTimestamp") or raw.get("dateEvent"),
        "date_local": raw.get("dateEventLocal") or raw.get("dateEvent"),
        "time_local": raw.get("strTimeLocal") or raw.get("strTime"),
        "status": status,
        "status_text": raw.get("strStatus") or "No publicado",
        "home_team": {
            "id": str(raw.get("idHomeTeam") or ""),
            "name": raw.get("strHomeTeam") or "Local",
            "badge": raw.get("strHomeTeamBadge"),
        },
        "away_team": {
            "id": str(raw.get("idAwayTeam") or ""),
            "name": raw.get("strAwayTeam") or "Visitante",
            "badge": raw.get("strAwayTeamBadge"),
        },
        "score_home": _int(raw.get("intHomeScore")),
        "score_away": _int(raw.get("intAwayScore")),
        "venue": raw.get("strVenue"),
        "season": raw.get("strSeason"),
        "round": raw.get("intRound"),
        "country": raw.get("strCountry"),
    }


def normalize_lineup(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        output.append({
            "player_id": str(row.get("idPlayer") or ""),
            "player": row.get("strPlayer") or "Jugador",
            "team_id": str(row.get("idTeam") or ""),
            "team": row.get("strTeam") or "Equipo",
            "side": "home" if str(row.get("strHome") or "").lower() == "yes" else "away",
            "starter": str(row.get("strSubstitute") or "").lower() != "yes",
            "number": row.get("intSquadNumber"),
            "position": row.get("strPosition"),
            "image": row.get("strCutout") or row.get("strThumb"),
        })
    output.sort(key=lambda row: (row["side"], not row["starter"], row["position"] or "", row["player"]))
    return output


def normalize_stats(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "name": row.get("strStat") or "Estadística",
        "home": row.get("intHome"),
        "away": row.get("intAway"),
    } for row in rows]


def normalize_roster(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        if str(row.get("strStatus") or "").lower() not in {"active", "playing"}:
            continue
        output.append({
            "id": str(row.get("idPlayer") or ""),
            "name": row.get("strPlayer") or "Jugador",
            "number": row.get("strNumber"),
            "position": row.get("strPosition"),
            "nationality": row.get("strNationality"),
            "date_born": row.get("dateBorn"),
            "image": row.get("strCutout") or row.get("strThumb"),
        })
    return output[:10]


class TheSportsDBClient:
    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "AppApuestasResearch/1.1",
        })

    def _get(
        self,
        endpoint: str,
        params: dict[str, Any],
        cache_seconds: int = 120,
        optional: bool = False,
    ) -> dict[str, Any]:
        if endpoint not in ENDPOINTS:
            raise ValueError("Endpoint TheSportsDB no permitido.")
        clean = {key: value for key, value in params.items() if value is not None}
        key = endpoint + repr(sorted(clean.items()))
        now = time.monotonic()
        with CACHE_LOCK:
            cached = CACHE.get(key)
            if cached and now - cached[0] < cache_seconds:
                return cached[1]
        global _LAST_REQUEST
        try:
            with REQUEST_LOCK:
                wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _LAST_REQUEST)
                if wait > 0:
                    time.sleep(wait)
                response = self.session.get(
                    BASE_URL + "/" + endpoint,
                    params=clean,
                    timeout=self.timeout,
                )
                _LAST_REQUEST = time.monotonic()
        except requests.RequestException as exc:
            raise TheSportsDBError("No fue posible conectar con TheSportsDB: " + str(exc)) from exc
        if response.status_code == 404 and optional:
            return {}
        if response.status_code == 429:
            raise TheSportsDBError("TheSportsDB alcanzó su límite gratuito; espera un minuto antes de reintentar.", 503, "THESPORTSDB_RATE_LIMIT")
        if response.status_code >= 500:
            raise TheSportsDBError("TheSportsDB respondió HTTP " + str(response.status_code) + ".", 502, "THESPORTSDB_UPSTREAM")
        if response.status_code >= 400:
            raise TheSportsDBError("TheSportsDB rechazó la consulta HTTP " + str(response.status_code) + ".", 502, "THESPORTSDB_BAD_REQUEST")
        try:
            data = response.json()
        except ValueError as exc:
            raise TheSportsDBError("TheSportsDB no devolvió JSON válido.") from exc
        if not isinstance(data, dict):
            raise TheSportsDBError("TheSportsDB devolvió una estructura inesperada.")
        with CACHE_LOCK:
            CACHE[key] = (now, data)
            if len(CACHE) > MAX_CACHE_ENTRIES:
                oldest = sorted(CACHE, key=lambda item: CACHE[item][0])[:len(CACHE) - MAX_CACHE_ENTRIES]
                for item in oldest:
                    CACHE.pop(item, None)
        return data

    def events_by_date(self, match_date: date) -> dict[str, Any]:
        payload = self._get(
            "eventsday.php",
            {"d": match_date.isoformat(), "s": "Soccer"},
            cache_seconds=60,
        )
        raw = payload.get("events") or []
        events = [normalize_event(item) for item in raw if isinstance(item, dict)]
        events = [item for item in events if item["id"]]
        events.sort(key=lambda item: (item.get("time_local") or "", item.get("league") or ""))
        return {
            "fuente": "TheSportsDB API v1",
            "fecha": match_date.isoformat(),
            "total_eventos": len(events),
            "eventos": events,
            "nota": "Cartelera de TheSportsDB para esa fecha. No representa necesariamente todos los partidos del mundo.",
        }

    def event_analysis(
        self,
        event_id: str,
        home_team_id: str | None = None,
        away_team_id: str | None = None,
    ) -> dict[str, Any]:
        if not event_id.isdigit() or len(event_id) > 20:
            raise ValueError("Identificador de evento no válido.")
        for team_id in (home_team_id, away_team_id):
            if team_id and (not team_id.isdigit() or len(team_id) > 15):
                raise ValueError("Identificador de equipo no válido.")
        # Dos consultas por evento; las muestras de jugadores son una acción separada.
        lineup_payload = self._get("lookuplineup.php", {"id": event_id}, cache_seconds=300, optional=True)
        stats_payload = self._get("lookupeventstats.php", {"id": event_id}, cache_seconds=300, optional=True)
        lineups = normalize_lineup(lineup_payload.get("lineup") or [])
        stats = normalize_stats(stats_payload.get("eventstats") or [])
        return {
            "fuente": "TheSportsDB API v1",
            "evento_id": event_id,
            "alineaciones": lineups,
            "estadisticas": stats,
            "advertencia": "La cobertura y actualización dependen de TheSportsDB. Contrasta nombres, alineaciones y estadísticas con PitchAPI antes de usarlos en un modelo.",
            "atribucion": "TheSportsDB",
        }

    def event_rosters(
        self,
        event_id: str,
        home_team_id: str | None,
        away_team_id: str | None,
    ) -> dict[str, Any]:
        if not event_id.isdigit() or len(event_id) > 20:
            raise ValueError("Identificador de evento no válido.")
        rosters: dict[str, Any] = {}
        for side, team_id in (("home", home_team_id), ("away", away_team_id)):
            if not team_id:
                rosters[side] = {"jugadores": [], "nota": "No se recibió el ID del club."}
                continue
            if not team_id.isdigit() or len(team_id) > 15:
                raise ValueError("Identificador de equipo no válido.")
            payload = self._get("lookup_all_players.php", {"id": team_id}, cache_seconds=21600, optional=True)
            players = normalize_roster(payload.get("player") or [])
            rosters[side] = {
                "jugadores": players,
                "total_muestra": len(players),
                "limite_gratuito": 10,
                "nota": "Muestra parcial de hasta 10 fichas activas; puede no incluir a toda la plantilla.",
            }
        return {
            "fuente": "TheSportsDB API v1",
            "evento_id": event_id,
            "plantillas": rosters,
        }
