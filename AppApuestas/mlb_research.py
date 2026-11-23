"""Research MLB opcional mediante pybaseball / Statcast.

La consulta queda acotada a ventanas de hasta 3 días. pybaseball obtiene información
de sitios externos; el código del paquete y los términos de los datos no son lo mismo.
"""
from __future__ import annotations

import threading
import time
from datetime import date
from typing import Any

_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 900
_CACHE_MAX = 120
MAX_WINDOW_DAYS = 3

STATCAST_COLUMNS = [
    "game_date", "game_pk", "at_bat_number", "pitch_number", "pitch_type",
    "pitch_name", "release_speed", "release_spin_rate", "spin_axis",
    "release_extension", "release_pos_x", "release_pos_z", "player_name",
    "batter", "pitcher", "stand", "p_throws", "events", "description",
    "zone", "balls", "strikes", "inning", "inning_topbot",
    "launch_speed", "launch_angle", "hit_distance_sc",
    "estimated_ba_using_speedangle", "estimated_woba_using_speedangle",
    "woba_value", "home_score", "away_score", "home_team", "away_team",
]


class MLBResearchError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502, code: str = "MLB_UPSTREAM_ERROR"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _frame_records(frame: Any, limit: int) -> list[dict[str, Any]]:
    if frame is None:
        return []
    try:
        if bool(frame.empty):
            return []
        rows = frame.head(limit).to_dict(orient="records")
    except Exception as exc:
        raise MLBResearchError("pybaseball devolvió una tabla con formato inesperado.") from exc
    clean = []
    for row in rows:
        item = {}
        for key, value in row.items():
            if hasattr(value, "item"):
                try:
                    value = value.item()
                except (ValueError, AttributeError):
                    pass
            if value is None or (isinstance(value, float) and (value != value or value in (float("inf"), float("-inf")))):
                value = None
            elif not isinstance(value, (str, int, float, bool)):
                value = str(value)
            item[str(key)] = value
        clean.append(item)
    return clean


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
    except MLBResearchError:
        raise
    except ImportError as exc:
        raise MLBResearchError(
            "pybaseball no está instalado. Instala AppApuestas/requirements-optional.txt en el entorno MLB.",
            503,
            "MLB_NOT_INSTALLED",
        ) from exc
    except Exception as exc:
        message = str(exc).replace("\n", " ")[:500]
        raise MLBResearchError(
            "No se pudo consultar Statcast. Puede haber límites, cambios en el proveedor o falta de datos: " + message,
            502,
            "MLB_UPSTREAM_ERROR",
        ) from exc
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), value)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)), None)
    return value


def mlb_status() -> dict[str, Any]:
    try:
        import pybaseball  # noqa: F401
        installed = True
        message = "pybaseball instalado; las consultas Statcast dependen de la disponibilidad de sus fuentes."
    except ImportError:
        installed = False
        message = "pybaseball no está instalado. Es una dependencia opcional."
    return {
        "proveedor": "MLB Statcast vía pybaseball",
        "instalado": installed,
        "requiere_api_key": False,
        "tipo_datos": [
            "lanzamientos individuales",
            "velocidad y spin del pitcheo",
            "velocidad de salida y ángulo de bateo",
            "datos de bateadores y lanzadores",
            "valor esperado y resultados del contacto cuando están publicados",
        ],
        "ventana_maxima_dias": MAX_WINDOW_DAYS,
        "advertencia": (
            "pybaseball extrae datos de terceros. Revisar términos de Baseball Savant, FanGraphs "
            "y Baseball Reference antes de automatizar o redistribuir resultados."
        ),
        "mensaje": message,
    }


def statcast(
    start_date: str,
    end_date: str,
    batter_id: int | None = None,
    pitcher_id: int | None = None,
    limit: int = 2000,
) -> dict[str, Any]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end_date no puede ser anterior a start_date.")
    days = (end - start).days + 1
    if days > MAX_WINDOW_DAYS:
        raise ValueError("La consulta Statcast está limitada a un máximo de 3 días por solicitud.")
    if batter_id is not None and batter_id <= 0:
        raise ValueError("batter_id debe ser positivo.")
    if pitcher_id is not None and pitcher_id <= 0:
        raise ValueError("pitcher_id debe ser positivo.")
    if batter_id is not None and pitcher_id is not None:
        raise ValueError("Consulta un bateador o un lanzador por solicitud, no ambos.")
    limit = max(1, min(5000, int(limit)))
    key = f"statcast:{start.isoformat()}:{end.isoformat()}:{batter_id}:{pitcher_id}:{limit}"

    def load():
        from pybaseball import statcast as fetch_statcast
        from pybaseball import statcast_batter, statcast_pitcher
        if batter_id is not None:
            frame = statcast_batter(start.isoformat(), end.isoformat(), batter_id)
        elif pitcher_id is not None:
            frame = statcast_pitcher(start.isoformat(), end.isoformat(), pitcher_id)
        else:
            frame = fetch_statcast(start.isoformat(), end.isoformat(), verbose=False)
        available = [column for column in STATCAST_COLUMNS if column in frame.columns]
        if available:
            frame = frame[available]
        rows = _frame_records(frame, limit)
        return {
            "fuente": "Baseball Savant Statcast vía pybaseball",
            "fecha_inicio": start.isoformat(),
            "fecha_fin": end.isoformat(),
            "batter_id": batter_id,
            "pitcher_id": pitcher_id,
            "total_registros_devuelto": len(rows),
            "limite_respuesta": limit,
            "columnas": list(rows[0].keys()) if rows else available,
            "lanzamientos": rows,
            "cache_segundos": _CACHE_TTL,
            "nota": "La muestra se limita tras descargar la ventana indicada; usa filtros por jugador y rangos cortos.",
        }
    return _cached(key, load)
