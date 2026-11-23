import os
import unittest
from unittest.mock import patch
from datetime import date, timedelta

from fastapi import HTTPException

import api_servidor


class APIRouteTests(unittest.TestCase):
    def test_research_routes_are_registered(self):
        paths = {route.path for route in api_servidor.app.routes}
        expected = {
            "/api/v1/research/football/matches/{match_id}/analysis",
            "/api/v1/research/storage/status",
            "/api/v1/research/storage/history/{match_id}",
            "/api/v1/research/nba/scoreboard",
            "/api/v1/research/nba/games/{game_id}/shots",
            "/api/v1/research/nba/teams/{team_id}/roster",
            "/api/v1/research/nba/games/{game_id}/boxscore",
            "/api/v1/research/nba/games/{game_id}/play-by-play",
            "/api/v1/research/nba/season-stats",
            "/api/v1/research/nfl/schedule",
            "/api/v1/research/nfl/games/{game_id}/pbp",
            "/api/v1/research/nfl/statistics",
            "/api/v1/research/nfl/snap-counts",
            "/api/v1/research/nfl/nextgen-stats",
            "/api/v1/research/nfl/pfr-advanced",
            "/api/v1/research/mlb/statcast",
            "/api/v1/research/football/open-data/team-history",
        }
        self.assertTrue(expected.issubset(paths))

    def test_cartelera_accepts_tomorrow_as_an_exact_local_date(self):
        today = api_servidor.datetime.now(api_servidor.EL_SALVADOR_TZ).date()
        fecha = today + timedelta(days=1)
        mocked = {
            "eventos": [],
            "fuente": "SportsGameOdds",
            "ventana_consulta": {
                "fecha_inicio_local": fecha.isoformat(),
                "fecha_fin_local": fecha.isoformat(),
                "dias_incluidos": 1,
                "zona_horaria": "America/El_Salvador",
            },
            "ligas_consultadas": ["UEFA_CHAMPIONS_LEAGUE", "MLS"],
            "paginacion_completa": True,
            "paginas_consultadas": 1,
        }
        with patch.object(api_servidor, "_get_events_cached", return_value=mocked) as request:
            result = api_servidor.cartelera(api_servidor.SportEnum.futbol, fecha=fecha)

        self.assertEqual(request.call_args.kwargs["match_date"], fecha)
        self.assertEqual(result["fecha_solicitada"], fecha.isoformat())
        self.assertEqual(result["fecha_inicio_local"], fecha.isoformat())
        self.assertEqual(result["fecha_fin_local"], fecha.isoformat())
        self.assertEqual(result["dias_incluidos"], 1)

    def test_cartelera_rejects_dates_after_the_next_two_days(self):
        with self.assertRaises(HTTPException) as context:
            api_servidor.cartelera(
                api_servidor.SportEnum.futbol,
                fecha=api_servidor.datetime.now(api_servidor.EL_SALVADOR_TZ).date() + timedelta(days=3),
            )
        self.assertEqual(context.exception.status_code, 400)

    def test_admin_endpoint_is_disabled_without_secret(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": ""}, clear=False):
            with self.assertRaises(HTTPException) as context:
                api_servidor.update_historical_data()
        self.assertEqual(context.exception.status_code, 404)

    def test_admin_endpoint_rejects_wrong_secret(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": "private-test-secret"}, clear=False):
            with self.assertRaises(HTTPException) as context:
                api_servidor.update_historical_data("wrong")
        self.assertEqual(context.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
