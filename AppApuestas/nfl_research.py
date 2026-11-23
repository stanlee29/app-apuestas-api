"""Research NFL opcional basado en nflreadpy/nflverse.

No carga nflreadpy hasta que se solicita un endpoint. Los archivos PBP pueden ser
grandes: los endpoints de juego requieren game_id y limitan registros devueltos.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 900
_CACHE_MAX = 120


class NFLResearchError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502, code: str = "NFL_UPSTREAM_ERROR"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _frame_records(frame: Any, limit: int) -> list[dict[str, Any]]:
    if frame is None:
        return []
    try:
        if hasattr(frame, "head"):
            frame = frame.head(limit)
        if hasattr(frame, "to_dicts"):
            rows = frame.to_dicts()
        else:
            rows = frame.to_dict(orient="records")
    except Exception as exc:
        raise NFLResearchError("nflreadpy devolvió una tabla con formato inesperado.") from exc
    return rows if isinstance(rows, list) else []


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
    except NFLResearchError:
        raise
    except ImportError as exc:
        raise NFLResearchError(
            "El módulo NFL es opcional. Instala AppApuestas/requirements-optional.txt (nflreadpy).",
            503,
            "NFL_NOT_INSTALLED",
        ) from exc
    except Exception as exc:
        message = str(exc).replace("\n", " ")[:500]
        raise NFLResearchError(
            "No se pudo consultar nflverse. Puede faltar una publicación de la temporada o haber un error temporal: " + message,
            502,
            "NFL_UPSTREAM_ERROR",
        ) from exc
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), value)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)), None)
    return value


def nfl_status() -> dict[str, Any]:
    try:
        import nflreadpy as nfl
        installed = True
        try:
            season = int(nfl.get_current_season())
        except Exception:
            season = None
        version = getattr(nfl, "__version__", None)
        message = "nflreadpy instalado; datos descargados desde los conjuntos publicados por nflverse."
    except ImportError:
        installed, season, version = False, None, None
        message = "nflreadpy no está instalado. Es una dependencia opcional."
    return {
        "proveedor": "nflverse mediante nflreadpy",
        "instalado": installed,
        "version": version,
        "temporada_actual": season,
        "tipo_datos": [
            "calendario y resultados",
            "play-by-play por partido",
            "estadísticas por jugador y equipo",
            "rosters por semana",
            "lesiones y depth charts",
            "snap counts y Next Gen Stats",
        ],
        "licencia_datos": "La mayoría de nflverse CC BY 4.0; FTN charting CC BY-SA 4.0.",
        "advertencia": "nflreadpy se declara experimental; revisar frescura y licencia por dataset.",
        "mensaje": message,
    }


def _validate_season(season: int) -> None:
    if season < 1999 or season > 2100:
        raise ValueError("season debe estar entre 1999 y 2100.")


def schedules(season: int, week: int | None = None, limit: int = 300) -> dict[str, Any]:
    _validate_season(season)
    if week is not None and not 1 <= week <= 25:
        raise ValueError("week debe estar entre 1 y 25.")
    limit = max(1, min(1000, int(limit)))

    def load():
        import nflreadpy as nfl
        import polars as pl
        frame = nfl.load_schedules(seasons=season)
        if week is not None and "week" in frame.columns:
            frame = frame.filter(pl.col("week") == week)
        rows = _frame_records(frame, limit)
        return {
            "fuente": "nflverse",
            "season": season,
            "week": week,
            "total_registros": len(rows),
            "partidos": rows,
            "cache_segundos": _CACHE_TTL,
        }
    return _cached(f"schedule:{season}:{week}:{limit}", load)


def play_by_play(game_id: str, season: int, limit: int = 1500) -> dict[str, Any]:
    _validate_season(season)
    if not re.fullmatch(r"[A-Za-z0-9_]{6,60}", game_id):
        raise ValueError("game_id NFL no tiene un formato válido.")
    limit = max(1, min(5000, int(limit)))

    def load():
        import nflreadpy as nfl
        import polars as pl
        frame = nfl.load_pbp(seasons=season)
        if "game_id" not in frame.columns:
            raise NFLResearchError("El PBP publicado no contiene game_id.", 502, "NFL_SCHEMA_CHANGED")
        frame = frame.filter(pl.col("game_id") == game_id)
        rows = _frame_records(frame, limit)
        return {
            "fuente": "nflverse",
            "season": season,
            "game_id": game_id,
            "total_jugadas": len(rows),
            "jugadas": rows,
            "limite_respuesta": limit,
            "cache_segundos": _CACHE_TTL,
        }
    return _cached(f"pbp:{season}:{game_id}:{limit}", load)


def weekly_rosters(season: int, week: int | None = None, limit: int = 1500) -> dict[str, Any]:
    if not 2002 <= season <= 2100:
        raise ValueError("season debe estar entre 2002 y 2100 para rosters semanales.")
    if week is not None and not 1 <= week <= 25:
        raise ValueError("week debe estar entre 1 y 25.")
    limit = max(1, min(5000, int(limit)))

    def load():
        import nflreadpy as nfl
        import polars as pl
        frame = nfl.load_rosters_weekly(seasons=season)
        if week is not None and "week" in frame.columns:
            frame = frame.filter(pl.col("week") == week)
        rows = _frame_records(frame, limit)
        return {
            "fuente": "nflverse",
            "season": season,
            "week": week,
            "total_jugadores": len(rows),
            "roster": rows,
            "cache_segundos": _CACHE_TTL,
        }
    return _cached(f"rosters:{season}:{week}:{limit}", load)


def injuries(season: int, limit: int = 1000) -> dict[str, Any]:
    if not 2009 <= season <= 2100:
        raise ValueError("season debe estar entre 2009 y 2100 para lesiones.")
    limit = max(1, min(5000, int(limit)))
    def load():
        import nflreadpy as nfl
        import polars as pl
        frame = nfl.load_injuries(seasons=season)
        rows = _frame_records(frame, limit)
        return {"fuente": "nflverse", "season": season, "total_registros": len(rows), "lesiones": rows}
    return _cached(f"injuries:{season}:{limit}", load)


def depth_charts(season: int, limit: int = 1000) -> dict[str, Any]:
    if not 2001 <= season <= 2100:
        raise ValueError("season debe estar entre 2001 y 2100 para depth charts.")
    limit = max(1, min(5000, int(limit)))
    def load():
        import nflreadpy as nfl
        frame = nfl.load_depth_charts(seasons=season)
        rows = _frame_records(frame, limit)
        return {"fuente": "nflverse", "season": season, "total_registros": len(rows), "depth_charts": rows}
    return _cached(f"depth:{season}:{limit}", load)
