"""Consulta opcional del dataset abierto schoChastics/football-data.

El parquet (aprox. 16 MB comprimido, 1.2M+ registros según el repositorio) no se
incluye en Git. Se consulta con DuckDB directamente sobre archivo local para evitar
cargar todas las filas en memoria. No contiene xG, eventos ni tracking.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any


DEFAULT_PATH = Path(__file__).resolve().parent / "datos" / "open_football" / "games.parquet"
SOURCE = "schochastics/football-data"
LICENSE = "Open Data Commons Attribution License (ODC-BY)"


class OpenFootballHistoryError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502, code: str = "OPEN_FOOTBALL_ERROR"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _path() -> Path:
    configured = os.getenv("FOOTBALL_OPEN_DATA_PATH", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_PATH


def open_football_status() -> dict[str, Any]:
    path = _path()
    present = path.is_file()
    return {
        "proveedor": SOURCE,
        "archivo_configurado": present,
        "ruta": str(path) if present else None,
        "licencia": LICENSE,
        "cobertura_publicada": "1888-2023",
        "tipo_datos": ["marcadores finales", "competición", "equipos", "fecha", "identificadores de equipo"],
        "no_incluye": ["xG", "remates", "alineaciones", "eventos", "tracking", "marcador en vivo"],
        "nota": "Dataset descargable manualmente; no se descarga automáticamente en el servidor.",
    }


def team_history(
    team_name: str,
    team_ident: str | None = None,
    before: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    clean_name = str(team_name or "").strip()
    if not clean_name or len(clean_name) > 120:
        raise ValueError("team_name es obligatorio y no debe superar 120 caracteres.")
    if team_ident is not None and (not str(team_ident).strip() or len(str(team_ident)) > 100):
        raise ValueError("team_ident no válido.")
    cutoff = date.fromisoformat(before) if before else date.today()
    safe_limit = max(1, min(50, int(limit)))
    path = _path()
    if not path.is_file():
        raise OpenFootballHistoryError(
            "El dataset parquet no está instalado. Descarga games.parquet y configura FOOTBALL_OPEN_DATA_PATH.",
            503,
            "OPEN_FOOTBALL_DATA_NOT_INSTALLED",
        )
    try:
        import duckdb
    except ImportError as exc:
        raise OpenFootballHistoryError(
            "DuckDB es opcional. Instala duckdb desde requirements-optional.txt en el entorno de investigación.",
            503,
            "DUCKDB_NOT_INSTALLED",
        ) from exc

    # La ruta, el equipo y la identidad se envían como parámetros a DuckDB.
    try:
        with duckdb.connect(database=":memory:") as connection:
            where_ident = ""
            params: list[Any] = [str(path), clean_name.casefold(), clean_name.casefold(), cutoff.isoformat()]
            if team_ident is not None:
                where_ident = " AND (CAST(home_ident AS VARCHAR) = ? OR CAST(away_ident AS VARCHAR) = ?)"
                params.extend([str(team_ident), str(team_ident)])
            params.append(safe_limit)
            query = f"""
                SELECT date, competition, home, away, gh, ga,
                       CAST(home_ident AS VARCHAR) AS home_ident,
                       CAST(away_ident AS VARCHAR) AS away_ident,
                       home_country, away_country, level
                FROM read_parquet(?)
                WHERE (lower(home) = ? OR lower(away) = ?)
                  AND TRY_CAST(date AS DATE) < CAST(? AS DATE)
                  AND gh IS NOT NULL AND ga IS NOT NULL
                  {where_ident}
                ORDER BY TRY_CAST(date AS DATE) DESC
                LIMIT ?
            """
            rows = connection.execute(query, params).fetchdf().to_dict(orient="records")
            variants = connection.execute(
                """SELECT DISTINCT team_name, team_ident, country
                   FROM (
                     SELECT home AS team_name, CAST(home_ident AS VARCHAR) AS team_ident,
                            home_country AS country
                     FROM read_parquet(?) WHERE lower(home) = ?
                     UNION ALL
                     SELECT away AS team_name, CAST(away_ident AS VARCHAR) AS team_ident,
                            away_country AS country
                     FROM read_parquet(?) WHERE lower(away) = ?
                   ) ORDER BY team_name, team_ident""",
                [str(path), clean_name.casefold(), str(path), clean_name.casefold()],
            ).fetchall()
    except Exception as exc:
        raise OpenFootballHistoryError("No se pudo leer el parquet histórico: " + str(exc)[:400]) from exc

    history = []
    wins = draws = losses = goals_for = goals_against = 0
    for row in rows:
        is_home = (
            str(row.get("home_ident") or "") == str(team_ident)
            if team_ident is not None
            else str(row.get("home") or "").casefold() == clean_name.casefold()
        )
        own = int(row["gh"] if is_home else row["ga"])
        opponent_goals = int(row["ga"] if is_home else row["gh"])
        result = "D"
        if own > opponent_goals:
            wins += 1
            result = "W"
        elif own < opponent_goals:
            losses += 1
            result = "L"
        else:
            draws += 1
        goals_for += own
        goals_against += opponent_goals
        history.append({
            "fecha": str(row.get("date")),
            "competicion": row.get("competition"),
            "equipo": row.get("home") if is_home else row.get("away"),
            "rival": row.get("away") if is_home else row.get("home"),
            "localia": "local" if is_home else "visitante",
            "goles": own,
            "goles_rival": opponent_goals,
            "resultado": result,
            "team_ident": row.get("home_ident") if is_home else row.get("away_ident"),
            "pais": row.get("home_country") if is_home else row.get("away_country"),
        })
    total = len(history)
    return {
        "fuente": SOURCE,
        "licencia": LICENSE,
        "equipo_buscado": clean_name,
        "team_ident": team_ident,
        "fecha_corte_exclusiva": cutoff.isoformat(),
        "total_partidos": total,
        "balance": {"victorias": wins, "empates": draws, "derrotas": losses},
        "goles_a_favor": goals_for,
        "goles_en_contra": goals_against,
        "goles_a_favor_por_partido": round(goals_for / total, 3) if total else None,
        "goles_en_contra_por_partido": round(goals_against / total, 3) if total else None,
        "identidades_posibles": [
            {"equipo": row[0], "team_ident": row[1], "pais": row[2]} for row in variants
        ],
        "advertencia_identidad": (
            "Los nombres de equipo no son únicos entre países y épocas. Filtra por team_ident "
            "si la lista contiene varias identidades."
        ),
        "historial": history,
        "atribucion": "Data: " + SOURCE + " · " + LICENSE,
    }
