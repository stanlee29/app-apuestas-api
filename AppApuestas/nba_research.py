"""Research NBA con nba_api (NBA.com Stats).

Se importa de forma diferida desde los endpoints; no se consulta la NBA al importar
el módulo. Los endpoints pueden bloquear tráfico automatizado o cambiar de formato,
por lo que cada respuesta se cachea y se informa el error sin tumbar la API general.
"""
from __future__ import annotations

import math
import re
import threading
import time
from datetime import date
from typing import Any

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 300
_CACHE_MAX = 300
_TIMEOUT = 20


class NBAResearchError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502, code: str = "NBA_UPSTREAM_ERROR"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _clean_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def dataframe_records(frame: Any, limit: int = 500) -> list[dict[str, Any]]:
    """Convierte DataFrame a registros JSON, eliminando NaN/NaT y limitando tamaño."""
    if frame is None:
        return []
    try:
        if bool(frame.empty):
            return []
        rows = frame.head(limit).to_dict(orient="records")
    except Exception as exc:
        raise NBAResearchError("NBA.com devolvió una tabla con estructura inesperada.") from exc
    return [
        {str(key): _clean_value(value) for key, value in row.items()}
        for row in rows if isinstance(row, dict)
    ]


def _cached(key: str, loader):
    now = time.monotonic()
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry and now - entry[0] < _CACHE_TTL:
            return entry[1]
        if entry:
            _CACHE.pop(key, None)
    try:
        value = loader()
    except NBAResearchError:
        raise
    except Exception as exc:
        message = str(exc).replace("\n", " ")[:500]
        raise NBAResearchError(
            "NBA.com no permitió completar la consulta. Puede ser un bloqueo temporal, "
            "límite de peticiones o cambio en el endpoint. Detalle: " + message,
            status_code=502,
            code="NBA_UPSTREAM_ERROR",
        ) from exc
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), value)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)), None)
    return value


def current_nba_season(reference_date: date | None = None) -> str:
    today = reference_date or date.today()
    start_year = today.year if today.month >= 10 else today.year - 1
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def nba_status() -> dict[str, Any]:
    try:
        import nba_api  # noqa: F401
        installed = True
        message = "nba_api instalado. Consultas a NBA.com disponibles según acceso del proveedor."
    except ImportError:
        installed = False
        message = "nba_api no está instalado en el entorno."
    return {
        "proveedor": "NBA.com Stats mediante nba_api",
        "instalado": installed,
        "requiere_api_key": False,
        "tipo_datos": [
            "cartelera y marcadores por fecha",
            "historial de partidos por equipo/jugador",
            "rosters de temporada",
            "tiros con coordenadas, distancia, periodo y resultado",
            "leaders por partido",
        ],
        "advertencia": (
            "La librería es un cliente comunitario, no una API oficial con SLA. "
            "NBA.com puede limitar, bloquear o cambiar las respuestas. Respeta sus condiciones de uso."
        ),
        "mensaje": message,
    }


def scoreboard(game_date: str) -> dict[str, Any]:
    parsed = date.fromisoformat(game_date)
    day = parsed.isoformat()

    def load():
        try:
            from nba_api.stats.endpoints import scoreboardv3
            board = scoreboardv3.ScoreboardV3(game_date=day, league_id="00", timeout=_TIMEOUT)
            headers = dataframe_records(board.game_header.get_data_frame(), 100)
            lines = dataframe_records(board.line_score.get_data_frame(), 200)
            leaders = dataframe_records(board.game_leaders.get_data_frame(), 100)
            return {
                "fuente": "NBA.com Stats",
                "fecha": day,
                "total_partidos": len(headers),
                "partidos": headers,
                "marcadores_por_equipo": lines,
                "lideres_por_partido": leaders,
                "cache_segundos": _CACHE_TTL,
            }
        except ImportError as exc:
            raise NBAResearchError("Instala nba_api para consultar la cartelera NBA.", 503, "NBA_NOT_INSTALLED") from exc

    return _cached("scoreboard:" + day, load)


def game_shots(
    game_id: str,
    team_id: int = 0,
    player_id: int = 0,
    season: str | None = None,
    season_type: str = "Regular Season",
) -> dict[str, Any]:
    if not re.fullmatch(r"\d{8,12}", game_id):
        raise ValueError("game_id NBA debe ser un identificador numérico válido.")
    if team_id < 0 or player_id < 0:
        raise ValueError("team_id y player_id deben ser cero o positivos.")
    season = season or current_nba_season()
    if not re.fullmatch(r"\d{4}-\d{2}", season):
        raise ValueError("season debe tener formato YYYY-YY.")
    if season_type not in {"Regular Season", "Playoffs", "Pre Season", "All Star"}:
        raise ValueError("season_type no válido.")
    key = f"shots:{game_id}:{team_id}:{player_id}:{season}:{season_type}"

    def load():
        try:
            from nba_api.stats.endpoints import shotchartdetail
            endpoint = shotchartdetail.ShotChartDetail(
                team_id=team_id,
                player_id=player_id,
                game_id_nullable=game_id,
                season_nullable=season,
                season_type_all_star=season_type,
                context_measure_simple="FGA",
                timeout=_TIMEOUT,
            )
            rows = dataframe_records(endpoint.shot_chart_detail.get_data_frame(), 2500)
            return {
                "fuente": "NBA.com Stats",
                "game_id": game_id,
                "season": season,
                "season_type": season_type,
                "team_id": team_id or None,
                "player_id": player_id or None,
                "total_tiros": len(rows),
                "tiros": rows,
                "coordenadas": {
                    "campos": ["LOC_X", "LOC_Y"],
                    "unidad": "décimas de pulgada respecto al aro/cancha NBA, según NBA.com",
                    "nota": "No son coordenadas de fútbol ni se deben mapear sobre un campo 105x68.",
                },
                "cache_segundos": _CACHE_TTL,
            }
        except ImportError as exc:
            raise NBAResearchError("Instala nba_api para consultar tiros NBA.", 503, "NBA_NOT_INSTALLED") from exc

    return _cached(key, load)


def game_logs(
    season: str | None = None,
    entity: str = "T",
    season_type: str = "Regular Season",
    limit: int = 200,
) -> dict[str, Any]:
    season = season or current_nba_season()
    if not re.fullmatch(r"\d{4}-\d{2}", season):
        raise ValueError("season debe tener formato YYYY-YY.")
    if entity not in {"T", "P"}:
        raise ValueError("entity debe ser T (equipo) o P (jugador).")
    if season_type not in {"Regular Season", "Playoffs", "Pre Season", "All Star"}:
        raise ValueError("season_type no válido.")
    limit = max(1, min(1000, int(limit)))
    key = f"logs:{season}:{entity}:{season_type}:{limit}"

    def load():
        try:
            from nba_api.stats.endpoints import leaguegamelog
            endpoint = leaguegamelog.LeagueGameLog(
                player_or_team_abbreviation=entity,
                season=season,
                season_type_all_star=season_type,
                timeout=_TIMEOUT,
            )
            rows = dataframe_records(endpoint.league_game_log.get_data_frame(), limit)
            return {
                "fuente": "NBA.com Stats",
                "season": season,
                "entity": "team" if entity == "T" else "player",
                "season_type": season_type,
                "total_registros": len(rows),
                "registros": rows,
                "cache_segundos": _CACHE_TTL,
            }
        except ImportError as exc:
            raise NBAResearchError("Instala nba_api para consultar el historial NBA.", 503, "NBA_NOT_INSTALLED") from exc

    return _cached(key, load)


def game_boxscore(game_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"\d{8,12}", game_id):
        raise ValueError("game_id NBA debe ser un identificador numérico válido.")
    key = "boxscore:" + game_id

    def load():
        try:
            from nba_api.stats.endpoints import boxscoretraditionalv3
            endpoint = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id, timeout=_TIMEOUT)
            players = dataframe_records(endpoint.player_stats.get_data_frame(), 80)
            teams_data = dataframe_records(endpoint.team_stats.get_data_frame(), 10)
        except ImportError as exc:
            raise NBAResearchError("Instala nba_api para consultar box scores NBA.", 503, "NBA_NOT_INSTALLED") from exc
        warnings: list[str] = []
        advanced_players: list[dict[str, Any]] = []
        advanced_teams: list[dict[str, Any]] = []
        tracking_players: list[dict[str, Any]] = []
        try:
            from nba_api.stats.endpoints import boxscoreadvancedv3
            advanced = boxscoreadvancedv3.BoxScoreAdvancedV3(game_id=game_id, timeout=_TIMEOUT)
            advanced_players = dataframe_records(advanced.player_stats.get_data_frame(), 80)
            advanced_teams = dataframe_records(advanced.team_stats.get_data_frame(), 10)
        except Exception as exc:
            warnings.append("Box score avanzado no disponible: " + str(exc)[:250])
        try:
            from nba_api.stats.endpoints import boxscoreplayertrackv3
            tracking = boxscoreplayertrackv3.BoxScorePlayerTrackV3(game_id=game_id, timeout=_TIMEOUT)
            tracking_players = dataframe_records(tracking.player_stats.get_data_frame(), 80)
        except Exception as exc:
            warnings.append("Player tracking no disponible: " + str(exc)[:250])
        return {
            "fuente": "NBA.com Stats",
            "game_id": game_id,
            "jugadores": players,
            "equipos": teams_data,
            "jugadores_avanzado": advanced_players,
            "equipos_avanzado": advanced_teams,
            "tracking_jugadores": tracking_players,
            "advertencias": warnings,
            "cache_segundos": _CACHE_TTL,
        }
    return _cached(key, load)


def game_play_by_play(game_id: str, limit: int = 1000) -> dict[str, Any]:
    if not re.fullmatch(r"\\d{8,12}", game_id):
        raise ValueError("game_id NBA debe ser un identificador numérico válido.")
    limit = max(1, min(2500, int(limit)))
    key = f"pbp:{game_id}:{limit}"

    def load():
        try:
            from nba_api.stats.endpoints import playbyplayv3
            endpoint = playbyplayv3.PlayByPlayV3(game_id=game_id, timeout=_TIMEOUT)
            rows = dataframe_records(endpoint.play_by_play.get_data_frame(), limit)
            return {
                "fuente": "NBA.com Stats",
                "game_id": game_id,
                "total_jugadas": len(rows),
                "jugadas": rows,
                "cache_segundos": _CACHE_TTL,
            }
        except ImportError as exc:
            raise NBAResearchError("Instala nba_api para consultar el play-by-play NBA.", 503, "NBA_NOT_INSTALLED") from exc
    return _cached(key, load)


def season_stats(
    season: str | None = None,
    entity: str = "player",
    season_type: str = "Regular Season",
    per_mode: str = "PerGame",
    measure_type: str = "Base",
    limit: int = 500,
) -> dict[str, Any]:
    season = season or current_nba_season()
    if not re.fullmatch(r"\d{4}-\d{2}", season):
        raise ValueError("season debe tener formato YYYY-YY.")
    if entity not in {"player", "team"}:
        raise ValueError("entity debe ser player o team.")
    if season_type not in {"Regular Season", "Playoffs", "Pre Season", "All Star"}:
        raise ValueError("season_type no válido.")
    if per_mode not in {"PerGame", "Totals", "Per36", "Per100Possessions"}:
        raise ValueError("per_mode no válido.")
    if measure_type not in {"Base", "Advanced", "Misc", "Four Factors", "Scoring", "Opponent"}:
        raise ValueError("measure_type no válido.")
    limit = max(1, min(2000, int(limit)))
    key = f"season-stats:{season}:{entity}:{season_type}:{per_mode}:{measure_type}:{limit}"

    def load():
        try:
            if entity == "player":
                from nba_api.stats.endpoints import leaguedashplayerstats
                endpoint = leaguedashplayerstats.LeagueDashPlayerStats(
                    season=season,
                    season_type_all_star=season_type,
                    per_mode_detailed=per_mode,
                    measure_type_detailed_defense=measure_type,
                    timeout=_TIMEOUT,
                )
                frame = endpoint.league_dash_player_stats.get_data_frame()
            else:
                from nba_api.stats.endpoints import leaguedashteamstats
                endpoint = leaguedashteamstats.LeagueDashTeamStats(
                    season=season,
                    season_type_all_star=season_type,
                    per_mode_detailed=per_mode,
                    measure_type_detailed_defense=measure_type,
                    timeout=_TIMEOUT,
                )
                frame = endpoint.league_dash_team_stats.get_data_frame()
            rows = dataframe_records(frame, limit)
            return {
                "fuente": "NBA.com Stats",
                "season": season,
                "entity": entity,
                "season_type": season_type,
                "per_mode": per_mode,
                "measure_type": measure_type,
                "total_registros": len(rows),
                "estadisticas": rows,
                "cache_segundos": _CACHE_TTL,
            }
        except ImportError as exc:
            raise NBAResearchError("Instala nba_api para consultar estadísticas de temporada NBA.", 503, "NBA_NOT_INSTALLED") from exc
    return _cached(key, load)


def teams() -> dict[str, Any]:
    def load():
        try:
            from nba_api.stats.static import teams as static_teams
            rows = static_teams.get_teams()
            normalized = [{
                "id": _clean_value(row.get("id")),
                "nombre": row.get("full_name"),
                "abreviatura": row.get("abbreviation"),
                "ciudad": row.get("city"),
                "conferencia": row.get("conference"),
                "division": row.get("division"),
            } for row in rows]
            return {"fuente": "nba_api static dataset", "total": len(normalized), "equipos": normalized}
        except ImportError as exc:
            raise NBAResearchError("Instala nba_api para consultar equipos NBA.", 503, "NBA_NOT_INSTALLED") from exc
    return _cached("teams:all", load)


def team_roster(team_id: int, season: str | None = None) -> dict[str, Any]:
    season = season or current_nba_season()
    if team_id <= 0:
        raise ValueError("team_id debe ser positivo.")
    if not re.fullmatch(r"\d{4}-\d{2}", season):
        raise ValueError("season debe tener formato YYYY-YY.")
    key = f"roster:{team_id}:{season}"

    def load():
        try:
            from nba_api.stats.endpoints import commonteamroster
            endpoint = commonteamroster.CommonTeamRoster(team_id=team_id, season=season, timeout=_TIMEOUT)
            players = dataframe_records(endpoint.common_team_roster.get_data_frame(), 60)
            coaches = dataframe_records(endpoint.coaches.get_data_frame(), 20)
            return {
                "fuente": "NBA.com Stats",
                "team_id": team_id,
                "season": season,
                "total_jugadores": len(players),
                "jugadores": players,
                "cuerpo_tecnico": coaches,
                "cache_segundos": _CACHE_TTL,
            }
        except ImportError as exc:
            raise NBAResearchError("Instala nba_api para consultar rosters NBA.", 503, "NBA_NOT_INSTALLED") from exc
    return _cached(key, load)
