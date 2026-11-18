"""Acceso a StatsBomb Open Data público para investigación histórica.

La fuente publica datos curados en JSON para determinadas competiciones y temporadas.
No es un feed en vivo. Citar a StatsBomb cuando se publiquen análisis derivados.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any

import requests


BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
CACHE_SECONDS = 6 * 60 * 60
_CACHE: dict[str, tuple[float, Any]] = {}
_LOCK = threading.Lock()


class StatsBombDataError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class StatsBombOpenData:
    def __init__(self, timeout: float = 25.0):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "AppApuestas-Research/1.0 (StatsBomb Open Data attribution)",
        })

    def _json(self, path: str, ttl: int = CACHE_SECONDS) -> Any:
        if path.startswith("/") or ".." in path:
            raise ValueError("Ruta de recurso no válida.")
        key = path
        now = time.monotonic()
        with _LOCK:
            cached = _CACHE.get(key)
            if cached and now - cached[0] < ttl:
                return cached[1]
        try:
            response = self.session.get(f"{BASE_URL}/{path}", timeout=self.timeout)
        except requests.RequestException as exc:
            raise StatsBombDataError(f"No fue posible consultar StatsBomb Open Data: {exc}") from exc
        if response.status_code == 404:
            raise StatsBombDataError(
                "StatsBomb Open Data no publica el recurso solicitado para esa competición y temporada.",
                status_code=404,
            )
        if response.status_code >= 400:
            raise StatsBombDataError(f"StatsBomb Open Data respondió HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise StatsBombDataError("StatsBomb Open Data devolvió JSON no válido.") from exc
        with _LOCK:
            _CACHE[key] = (now, payload)
        return payload

    @staticmethod
    def _validate_ids(competition_id: int, season_id: int) -> None:
        if competition_id < 1 or season_id < 1:
            raise ValueError("Los identificadores de competición y temporada deben ser positivos.")

    def competitions(self) -> list[dict[str, Any]]:
        raw = self._json("competitions.json", ttl=24 * 60 * 60)
        if not isinstance(raw, list):
            raise StatsBombDataError("El catálogo público de StatsBomb no tiene el formato esperado.")
        grouped: dict[int, dict[str, Any]] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                competition_id = int(item["competition_id"])
                season_id = int(item["season_id"])
            except (KeyError, TypeError, ValueError):
                continue
            record = grouped.setdefault(competition_id, {
                "competition_id": competition_id,
                "competition_name": item.get("competition_name"),
                "country_name": item.get("country_name"),
                "competition_gender": item.get("competition_gender"),
                "competition_youth": item.get("competition_youth"),
                "competition_international": item.get("competition_international"),
                "seasons": [],
            })
            record["seasons"].append({
                "season_id": season_id,
                "season_name": item.get("season_name"),
                "matches_updated": item.get("match_updated"),
                "match_available_360": bool(item.get("match_available_360")),
            })
        result = list(grouped.values())
        for competition in result:
            competition["seasons"].sort(
                key=lambda season: str(season.get("season_name") or ""),
                reverse=True,
            )
            competition["total_temporadas"] = len(competition["seasons"])
        result.sort(key=lambda item: (
            str(item.get("country_name") or ""),
            str(item.get("competition_name") or ""),
        ))
        return result

    def matches(self, competition_id: int, season_id: int) -> list[dict[str, Any]]:
        self._validate_ids(competition_id, season_id)
        raw = self._json(f"matches/{competition_id}/{season_id}.json", ttl=12 * 60 * 60)
        if not isinstance(raw, list):
            raise StatsBombDataError("El listado de partidos no tiene el formato esperado.")
        return [item for item in raw if isinstance(item, dict)]

    def match_xg_summary(self, match_id: int, match: dict[str, Any]) -> dict[str, Any]:
        """Resume xG de los remates para un partido histórico publicado."""
        if match_id < 1:
            raise ValueError("El identificador de partido debe ser positivo.")
        events = self._json(f"events/{match_id}.json", ttl=24 * 60 * 60)
        if not isinstance(events, list):
            raise StatsBombDataError("El feed de eventos no tiene el formato esperado.")
        home_name = self._team_name(match.get("home_team"))
        away_name = self._team_name(match.get("away_team"))
        xg = {home_name: 0.0, away_name: 0.0}
        shots = {home_name: 0, away_name: 0}
        for event in events:
            if not isinstance(event, dict) or self._team_name(event.get("type")) != "Shot":
                continue
            team = self._team_name(event.get("team"))
            shot = event.get("shot") or {}
            if team not in xg or not isinstance(shot, dict):
                continue
            raw_xg = shot.get("statsbomb_xg")
            if not isinstance(raw_xg, (int, float)):
                continue
            xg[team] += float(raw_xg)
            shots[team] += 1
        return {
            "match_id": match_id,
            "home_team": home_name,
            "away_team": away_name,
            "xg_home": round(xg.get(home_name, 0.0), 4),
            "xg_away": round(xg.get(away_name, 0.0), 4),
            "shots_home_with_xg": shots.get(home_name, 0),
            "shots_away_with_xg": shots.get(away_name, 0),
            "has_xg": bool(sum(shots.values())),
        }

    def recent_team_xg(
        self,
        matches: list[dict[str, Any]],
        home_team_name: str,
        away_team_name: str,
        limit: int = 8,
    ) -> dict[str, Any] | None:
        """Obtiene tasas xG recientes: local en casa y visitante fuera."""
        if not 3 <= limit <= 12:
            raise ValueError("El límite de partidos xG debe estar entre 3 y 12.")
        home_key = self._team_name({"name": home_team_name}).casefold()
        away_key = self._team_name({"name": away_team_name}).casefold()

        def name_for(row: dict[str, Any], side: str) -> str:
            return self._team_name(row.get(side))

        completed = [
            item for item in matches
            if isinstance(item, dict)
            and item.get("match_status") == "available"
            and item.get("home_score") is not None
            and item.get("away_score") is not None
        ]
        home_games = [
            item for item in completed
            if name_for(item, "home_team").casefold() == home_key
        ]
        away_games = [
            item for item in completed
            if name_for(item, "away_team").casefold() == away_key
        ]
        home_games.sort(key=lambda item: str(item.get("match_date") or ""), reverse=True)
        away_games.sort(key=lambda item: str(item.get("match_date") or ""), reverse=True)

        summaries: dict[int, dict[str, Any]] = {}
        def summary_for(match: dict[str, Any]) -> dict[str, Any] | None:
            try:
                match_id = int(match.get("match_id"))
                if match_id not in summaries:
                    summaries[match_id] = self.match_xg_summary(match_id, match)
                return summaries[match_id] if summaries[match_id].get("has_xg") else None
            except (TypeError, ValueError, StatsBombDataError):
                return None

        home_for: list[float] = []
        home_against: list[float] = []
        for match in home_games[:limit]:
            summary = summary_for(match)
            if summary is not None:
                home_for.append(float(summary["xg_home"]))
                home_against.append(float(summary["xg_away"]))

        away_for: list[float] = []
        away_against: list[float] = []
        for match in away_games[:limit]:
            summary = summary_for(match)
            if summary is not None:
                away_for.append(float(summary["xg_away"]))
                away_against.append(float(summary["xg_home"]))

        if len(home_for) < 3 or len(away_for) < 3:
            return None

        avg_home_for = sum(home_for) / len(home_for)
        avg_home_against = sum(home_against) / len(home_against)
        avg_away_for = sum(away_for) / len(away_for)
        avg_away_against = sum(away_against) / len(away_against)
        return {
            "lambda_home": round(max(0.05, (avg_home_for + avg_away_against) / 2), 4),
            "lambda_away": round(max(0.05, (avg_away_for + avg_home_against) / 2), 4),
            "home_xg_for_avg": round(avg_home_for, 4),
            "home_xg_against_avg": round(avg_home_against, 4),
            "away_xg_for_avg": round(avg_away_for, 4),
            "away_xg_against_avg": round(avg_away_against, 4),
            "home_matches_with_xg": len(home_for),
            "away_matches_with_xg": len(away_for),
            "xg_source": "StatsBomb Open Data · statsbomb_xg por remate",
        }

    @staticmethod
    def _team_name(value: Any) -> str:
        if isinstance(value, dict):
            return str(
                value.get("name")
                or value.get("home_team_name")
                or value.get("away_team_name")
                or ""
            )
        return str(value or "")

    @staticmethod
    def _event_location(event: dict[str, Any]) -> tuple[float, float] | None:
        raw = event.get("location")
        if not isinstance(raw, list) or len(raw) < 2:
            return None
        try:
            x, y = float(raw[0]), float(raw[1])
        except (TypeError, ValueError):
            return None
        if not (0 <= x <= 120 and 0 <= y <= 80):
            return None
        return x, y

    def match_analysis(
        self,
        match_id: int,
        competition_id: int,
        season_id: int,
    ) -> dict[str, Any]:
        self._validate_ids(competition_id, season_id)
        if match_id < 1:
            raise ValueError("El identificador de partido debe ser positivo.")
        matches = self.matches(competition_id, season_id)
        match = next((item for item in matches if int(item.get("match_id", 0)) == match_id), None)
        if match is None:
            raise StatsBombDataError("El partido no pertenece a la competición/temporada indicada.", 404)

        events = self._json(f"events/{match_id}.json", ttl=24 * 60 * 60)
        try:
            lineups = self._json(f"lineups/{match_id}.json", ttl=24 * 60 * 60)
        except StatsBombDataError:
            lineups = []

        if not isinstance(events, list):
            raise StatsBombDataError("El feed de eventos del partido no tiene el formato esperado.")
        if not isinstance(lineups, list):
            lineups = []

        home_team = self._team_name(match.get("home_team"))
        away_team = self._team_name(match.get("away_team"))
        team_names = {home_team, away_team}
        shots: list[dict[str, Any]] = []
        team_counts = {
            home_team: {"remates": 0, "remates_a_puerta": 0, "xg": 0.0, "goles_en_remates": 0},
            away_team: {"remates": 0, "remates_a_puerta": 0, "xg": 0.0, "goles_en_remates": 0},
        }
        team_activity: dict[str, dict[tuple[int, int], int]] = {name: {} for name in team_names}
        player_activity: dict[tuple[str, str], dict[tuple[int, int], int]] = {}
        corners = {home_team: 0, away_team: 0}
        fouls = {home_team: 0, away_team: 0}
        cards = {home_team: {"yellow": 0, "red": 0}, away_team: {"yellow": 0, "red": 0}}

        for event in events:
            if not isinstance(event, dict):
                continue
            event_type = self._team_name(event.get("type"))
            team = self._team_name(event.get("team"))
            player = self._team_name(event.get("player"))
            location = self._event_location(event)

            if team in team_activity and location is not None:
                cell = (
                    min(11, int(location[0] / 120 * 12)),
                    min(7, int(location[1] / 80 * 8)),
                )
                team_activity[team][cell] = team_activity[team].get(cell, 0) + 1
                if player:
                    key = (team, player)
                    player_activity.setdefault(key, {})
                    player_activity[key][cell] = player_activity[key].get(cell, 0) + 1

            if team not in team_names:
                continue

            if event_type == "Shot":
                shot = event.get("shot") or {}
                if not isinstance(shot, dict):
                    shot = {}
                outcome = self._team_name(shot.get("outcome"))
                xg = shot.get("statsbomb_xg")
                try:
                    xg_value = float(xg) if xg is not None else None
                except (TypeError, ValueError):
                    xg_value = None
                team_counts[team]["remates"] += 1
                if outcome.casefold() == "goal" or "saved" in outcome.casefold():
                    team_counts[team]["remates_a_puerta"] += 1
                if outcome.casefold() == "goal":
                    team_counts[team]["goles_en_remates"] += 1
                if xg_value is not None:
                    team_counts[team]["xg"] += xg_value
                coordinate = self._event_location(event)
                shots.append({
                    "team": team,
                    "player": player or None,
                    "minute": event.get("minute"),
                    "second": event.get("second"),
                    "period": (event.get("period") or {}).get("name") if isinstance(event.get("period"), dict) else event.get("period"),
                    "x": coordinate[0] if coordinate else None,
                    "y": coordinate[1] if coordinate else None,
                    "xg": xg_value,
                    "outcome": outcome or None,
                    "body_part": self._team_name(shot.get("body_part")) or None,
                    "technique": self._team_name(shot.get("technique")) or None,
                })

            if event_type == "Pass":
                pass_info = event.get("pass") or {}
                if isinstance(pass_info, dict) and self._team_name(pass_info.get("type")).casefold() == "corner":
                    corners[team] += 1
            if event_type == "Foul Committed":
                fouls[team] += 1
                foul = event.get("foul_committed") or {}
                card = self._team_name(foul.get("card")) if isinstance(foul, dict) else ""
                if "yellow" in card.casefold():
                    cards[team]["yellow"] += 1
                elif "red" in card.casefold():
                    cards[team]["red"] += 1

        def heatmap(cells: dict[tuple[int, int], int]) -> list[list[int]]:
            return [[x, y, count] for (x, y), count in sorted(cells.items())]

        home_score = match.get("home_score")
        away_score = match.get("away_score")
        for name, score in ((home_team, home_score), (away_team, away_score)):
            team_counts[name]["goles"] = score
            team_counts[name]["xg"] = round(team_counts[name]["xg"], 4)
            team_counts[name]["xg_por_remate"] = (
                round(team_counts[name]["xg"] / team_counts[name]["remates"], 4)
                if team_counts[name]["remates"] else None
            )

        h2h = []
        for item in matches:
            item_home = self._team_name(item.get("home_team"))
            item_away = self._team_name(item.get("away_team"))
            has_result = item.get("home_score") is not None and item.get("away_score") is not None
            if {item_home, item_away} == team_names and has_result:
                h2h.append({
                    "match_id": item.get("match_id"),
                    "date": item.get("match_date"),
                    "home": item_home,
                    "away": item_away,
                    "score_home": item.get("home_score"),
                    "score_away": item.get("away_score"),
                })
        h2h.sort(key=lambda item: str(item.get("date") or ""), reverse=True)

        players = [
            {
                "team": team,
                "player": player,
                "cells": heatmap(cells),
                "actions": sum(cells.values()),
            }
            for (team, player), cells in player_activity.items()
        ]
        players.sort(key=lambda item: item["actions"], reverse=True)

        return {
            "fuente": "StatsBomb Open Data",
            "atribucion_requerida": "StatsBomb",
            "competicion": {
                "competition_id": competition_id,
                "season_id": season_id,
                "name": (match.get("competition") or {}).get("competition_name") if isinstance(match.get("competition"), dict) else None,
                "season": (match.get("season") or {}).get("season_name") if isinstance(match.get("season"), dict) else None,
            },
            "partido": match,
            "metricas": {
                "local": team_counts.get(home_team, {}),
                "visitante": team_counts.get(away_team, {}),
                "corners": corners,
                "faltas": fouls,
                "tarjetas": cards,
            },
            "remates": shots,
            "mapas_calor": {
                "coordinate_system": "StatsBomb 120x80; coordenadas originales, sin normalización de dirección",
                "teams": [
                    {"team": name, "cells": heatmap(cells), "actions": sum(cells.values())}
                    for name, cells in team_activity.items()
                ],
                "players": players[:12],
            },
            "h2h_misma_competicion_temporada": h2h,
            "alineaciones": lineups,
            "total_eventos": len(events),
            "total_remates": len(shots),
            "nota": (
                "Datos históricos de competiciones seleccionadas, no resultados ni cuotas en vivo. "
                "El mapa de actividad cuenta eventos con coordenadas; no es tracking continuo de jugadores. "
                "Atribuir a StatsBomb cualquier análisis publicado basado en estos datos."
            ),
        }


def statsbomb_status() -> dict[str, Any]:
    return {
        "proveedor": "StatsBomb Open Data",
        "configurado": True,
        "autenticacion": "No requiere clave",
        "tipo_datos": [
            "catálogo de competiciones y temporadas publicadas",
            "partidos históricos",
            "eventos y remates con xG cuando están disponibles",
            "coordenadas de eventos y mapas de actividad",
            "alineaciones",
            "H2H dentro de la competición y temporada cargadas",
            "córners, faltas y tarjetas cuando constan en el feed",
        ],
        "restricciones": [
            "no es una fuente de fixtures ni resultados en vivo",
            "solo incluye las competiciones y temporadas abiertas en el repositorio",
            "no todas las temporadas tienen datos StatsBomb 360",
            "requiere atribución a StatsBomb en análisis publicados",
        ],
        "catalogo": "https://github.com/statsbomb/open-data",
        "documentacion": "https://github.com/statsbomb/open-data/blob/master/README.md",
    }
