"""Cliente ligero de los endpoints JSON públicos de ESPN Soccer.

No usa navegador, proxy ni mecanismos para evadir controles. La API no está
documentada como producto público estable: debe tratarse como fuente experimental.
"""
from __future__ import annotations

import threading
import time
from datetime import date
from typing import Any

import requests

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer"
CACHE: dict[str, tuple[float, Any]] = {}
CACHE_LOCK = threading.Lock()
REQUEST_LOCK = threading.Lock()
_LAST_REQUEST = 0.0
MIN_REQUEST_INTERVAL = 0.30
MAX_CACHE_ENTRIES = 300

LEAGUES = {
    "eng.1": {"name": "Premier League", "country": "Inglaterra"},
    "eng.2": {"name": "EFL Championship", "country": "Inglaterra"},
    "esp.1": {"name": "LaLiga", "country": "España"},
    "ita.1": {"name": "Serie A", "country": "Italia"},
    "ger.1": {"name": "Bundesliga", "country": "Alemania"},
    "fra.1": {"name": "Ligue 1", "country": "Francia"},
    "ned.1": {"name": "Eredivisie", "country": "Países Bajos"},
    "por.1": {"name": "Primeira Liga", "country": "Portugal"},
    "usa.1": {"name": "MLS", "country": "Estados Unidos"},
    "mex.1": {"name": "Liga MX", "country": "México"},
    "bra.1": {"name": "Brasileirão Série A", "country": "Brasil"},
    "arg.1": {"name": "Liga Profesional", "country": "Argentina"},
    "uefa.champions": {"name": "Champions League", "country": "Europa"},
    "uefa.europa": {"name": "Europa League", "country": "Europa"},
}


class ESPNDataError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502, code: str = "ESPN_ERROR"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def espn_status() -> dict[str, Any]:
    return {
        "fuente": "ESPN Soccer public JSON",
        "disponible": True,
        "requiere_clave": False,
        "estado": "experimental",
        "ligas_configuradas": len(LEAGUES),
        "advertencia": "Endpoint público no documentado como API estable; cobertura y formato pueden cambiar.",
    }


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def normalize_event(raw: dict[str, Any], league_slug: str) -> dict[str, Any]:
    competitions = raw.get("competitions") or []
    competition = competitions[0] if competitions and isinstance(competitions[0], dict) else {}
    competitors = competition.get("competitors") or []
    home = next((item for item in competitors if item.get("homeAway") == "home"), {})
    away = next((item for item in competitors if item.get("homeAway") == "away"), {})
    home_team = home.get("team") or {}
    away_team = away.get("team") or {}
    raw_status = competition.get("status") or raw.get("status") or {}
    status_type = raw_status.get("type") or {}
    state = str(status_type.get("state") or "").lower()
    if status_type.get("completed") is True or state == "post":
        status = "finished"
    elif state == "in":
        status = "live"
    else:
        status = "scheduled"
    league = LEAGUES.get(league_slug, {})
    return {
        "id": str(raw.get("id") or ""),
        "league_id": league_slug,
        "league": league.get("name") or league_slug,
        "date": raw.get("date") or competition.get("date"),
        "status": status,
        "status_text": status_type.get("shortDetail") or status_type.get("detail") or status_type.get("description"),
        "clock": raw_status.get("displayClock"),
        "score_home": _as_int(home.get("score")),
        "score_away": _as_int(away.get("score")),
        "home_team": {
            "id": str(home_team.get("id") or home.get("id") or ""),
            "name": home_team.get("displayName") or home_team.get("name") or "Local",
            "abbreviation": home_team.get("abbreviation"),
            "logo": home_team.get("logo"),
            "form": home.get("form"),
        },
        "away_team": {
            "id": str(away_team.get("id") or away.get("id") or ""),
            "name": away_team.get("displayName") or away_team.get("name") or "Visitante",
            "abbreviation": away_team.get("abbreviation"),
            "logo": away_team.get("logo"),
            "form": away.get("form"),
        },
        "venue": (competition.get("venue") or {}).get("fullName"),
        "season": (raw.get("season") or {}).get("year"),
    }


def normalize_team_stats(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    boxscore = payload.get("boxscore") or {}
    for team_row in boxscore.get("teams") or []:
        team = team_row.get("team") or {}
        stats = []
        for item in team_row.get("statistics") or []:
            stats.append({
                "key": item.get("name"),
                "label": item.get("label") or item.get("name"),
                "value": item.get("displayValue"),
            })
        result.append({
            "team_id": str(team.get("id") or ""),
            "team": team.get("displayName") or team.get("name") or "Equipo",
            "logo": team.get("logo"),
            "side": team_row.get("homeAway"),
            "statistics": stats,
        })
    return result


def normalize_roster(payload: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for athlete in payload.get("athletes") or []:
        stats: dict[str, Any] = {}
        split = ((athlete.get("statistics") or {}).get("splits") or {})
        for category in split.get("categories") or []:
            for item in category.get("stats") or []:
                key = item.get("name")
                if key:
                    stats[key] = item.get("displayValue", item.get("value"))
        position = athlete.get("position") or {}
        injuries = athlete.get("injuries") or []
        rows.append({
            "id": str(athlete.get("id") or ""),
            "name": athlete.get("displayName") or athlete.get("fullName") or "Jugador",
            "jersey": athlete.get("jersey"),
            "age": athlete.get("age"),
            "nationality": athlete.get("citizenship"),
            "position": position.get("abbreviation") or position.get("displayName"),
            "status": (athlete.get("status") or {}).get("name"),
            "injured": bool(injuries),
            "stats": {
                "appearances": stats.get("appearances"),
                "goals": stats.get("totalGoals"),
                "assists": stats.get("goalAssists"),
                "shots": stats.get("totalShots"),
                "shots_on_target": stats.get("shotsOnTarget"),
                "yellow_cards": stats.get("yellowCards"),
                "red_cards": stats.get("redCards"),
                "fouls_committed": stats.get("foulsCommitted"),
            },
        })
    rows.sort(key=lambda row: (_as_int(row["stats"]["appearances"]) or 0, row["name"]), reverse=True)
    return {
        "season": payload.get("season", {}).get("displayName") or payload.get("season", {}).get("name"),
        "timestamp": payload.get("timestamp"),
        "total_jugadores": len(rows),
        "jugadores": rows[:40],
    }


def normalize_leaders(payload: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    for team_group in payload.get("leaders") or []:
        team_name = (team_group.get("team") or {}).get("displayName") or "Equipo"
        for category in team_group.get("leaders") or []:
            values = category.get("leaders") or []
            if not values:
                continue
            top = values[0]
            athlete = top.get("athlete") or {}
            output.append({
                "team": team_name,
                "category": category.get("displayName") or category.get("name") or "Líder",
                "player": athlete.get("displayName") or athlete.get("fullName") or "Jugador",
                "value": top.get("displayValue") or top.get("value"),
            })
    return output


class ESPNPublicClient:
    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "AppApuestasResearch/1.1 (+https://app-apuestas-api.onrender.com)",
        })

    def _get(
        self,
        league: str,
        resource: str,
        params: dict[str, Any] | None = None,
        cache_seconds: int = 120,
        optional: bool = False,
    ) -> dict[str, Any]:
        if league not in LEAGUES:
            raise ValueError("Liga ESPN no soportada por el conector.")
        if not resource or resource.startswith("/") or ".." in resource:
            raise ValueError("Recurso ESPN no válido.")
        clean_params = {key: value for key, value in (params or {}).items() if value is not None}
        cache_key = league + "/" + resource + repr(sorted(clean_params.items()))
        now = time.monotonic()
        with CACHE_LOCK:
            cached = CACHE.get(cache_key)
            if cache_seconds > 0 and cached and now - cached[0] < cache_seconds:
                return cached[1]
        global _LAST_REQUEST
        try:
            with REQUEST_LOCK:
                wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _LAST_REQUEST)
                if wait > 0:
                    time.sleep(wait)
                response = self.session.get(
                    BASE_URL + "/" + league + "/" + resource,
                    params=clean_params,
                    timeout=self.timeout,
                )
                _LAST_REQUEST = time.monotonic()
        except requests.RequestException as exc:
            raise ESPNDataError("No fue posible conectar con ESPN: " + str(exc)) from exc

        if response.status_code == 404 and optional:
            return {}
        if response.status_code == 429:
            raise ESPNDataError("ESPN limitó temporalmente las consultas. Espera y vuelve a intentar.", 503, "ESPN_RATE_LIMIT")
        if response.status_code >= 500:
            raise ESPNDataError("ESPN respondió con un error temporal HTTP " + str(response.status_code) + ".", 502, "ESPN_UPSTREAM_ERROR")
        if response.status_code >= 400:
            raise ESPNDataError("ESPN rechazó la consulta HTTP " + str(response.status_code) + ".", 502, "ESPN_BAD_REQUEST")
        try:
            data = response.json()
        except ValueError as exc:
            raise ESPNDataError("ESPN no devolvió JSON válido.") from exc
        if not isinstance(data, dict):
            raise ESPNDataError("ESPN devolvió una estructura JSON inesperada.")
        if cache_seconds > 0:
            with CACHE_LOCK:
                CACHE[cache_key] = (now, data)
                if len(CACHE) > MAX_CACHE_ENTRIES:
                    oldest = sorted(CACHE, key=lambda key: CACHE[key][0])[:len(CACHE) - MAX_CACHE_ENTRIES]
                    for key in oldest:
                        CACHE.pop(key, None)
        return data

    def leagues(self) -> list[dict[str, str]]:
        return [
            {"id": slug, "name": values["name"], "country": values["country"]}
            for slug, values in LEAGUES.items()
        ]

    def scoreboard(self, league: str, match_date: date, limit: int = 100) -> dict[str, Any]:
        if league not in LEAGUES:
            raise ValueError("Liga ESPN no soportada por el conector.")
        if not 1 <= limit <= 100:
            raise ValueError("El límite debe estar entre 1 y 100.")
        payload = self._get(
            league,
            "scoreboard",
            {"dates": match_date.strftime("%Y%m%d"), "limit": limit},
            cache_seconds=45,
        )
        raw_events = payload.get("events") or []
        events = [normalize_event(item, league) for item in raw_events if isinstance(item, dict)]
        events.sort(key=lambda item: item.get("date") or "")
        league_data = (payload.get("leagues") or [{}])[0]
        return {
            "fuente": "ESPN public JSON",
            "liga": league_data.get("name") or LEAGUES[league]["name"],
            "liga_id": league,
            "fecha": match_date.isoformat(),
            "temporada": (payload.get("season") or {}).get("year"),
            "total_eventos": len(events),
            "eventos": events,
            "consultado_en": date.today().isoformat(),
            "nota": "Cartelera pública de ESPN; la cobertura puede variar por competición y fecha.",
        }

    def match_analysis(
        self,
        league: str,
        event_id: str,
        home_team_id: str | None = None,
        away_team_id: str | None = None,
    ) -> dict[str, Any]:
        if not event_id.isdigit() or len(event_id) > 20:
            raise ValueError("Identificador de partido ESPN no válido.")
        summary = self._get(league, "summary", {"event": event_id}, cache_seconds=120, optional=True)
        team_stats = normalize_team_stats(summary)
        leaders = normalize_leaders(summary)
        team_ids: dict[str, str] = {}
        for item in team_stats:
            if item.get("side") in ("home", "away"):
                team_ids[item["side"]] = item["team_id"]
        header = summary.get("header") or {}
        header_competitions = header.get("competitions") or []
        if header_competitions:
            for competitor in header_competitions[0].get("competitors") or []:
                side = competitor.get("homeAway")
                team = competitor.get("team") or {}
                team_id = str(team.get("id") or competitor.get("id") or "")
                if side in ("home", "away") and team_id:
                    team_ids.setdefault(side, team_id)
        team_ids.setdefault("home", str(home_team_id or ""))
        team_ids.setdefault("away", str(away_team_id or ""))

        rosters: dict[str, Any] = {}
        warnings = []
        for side in ("home", "away"):
            team_id = team_ids.get(side, "")
            if not team_id:
                rosters[side] = {"total_jugadores": 0, "jugadores": [], "error": "Identificador del equipo no disponible."}
                continue
            if not team_id.isdigit() or len(team_id) > 12:
                raise ValueError("Identificador de equipo ESPN no válido.")
            try:
                raw_roster = self._get(
                    league,
                    "teams/" + team_id + "/roster",
                    cache_seconds=21600,
                    optional=True,
                )
                rosters[side] = normalize_roster(raw_roster)
                rosters[side]["team_id"] = team_id
            except ESPNDataError as exc:
                rosters[side] = {"total_jugadores": 0, "jugadores": [], "error": str(exc)}
                warnings.append(side + ": " + str(exc))

        return {
            "fuente": "ESPN public JSON",
            "estado_fuente": "experimental",
            "partido_id": event_id,
            "estadisticas_equipo": team_stats,
            "lideres_del_partido": leaders,
            "plantillas": rosters,
            "advertencias": warnings,
            "nota": "Las plantillas son los registros actuales de cada club en ESPN; no equivalen a alineaciones confirmadas ni garantizan disponibilidad para este partido. Las estadísticas corresponden a la temporada publicada por la fuente.",
            "atribucion": "ESPN",
        }
