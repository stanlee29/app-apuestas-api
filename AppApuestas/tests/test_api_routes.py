import os
import unittest
from unittest.mock import patch

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
            "/api/v1/research/nfl/schedule",
            "/api/v1/research/nfl/games/{game_id}/pbp",
            "/api/v1/research/mlb/statcast",
            "/api/v1/research/football/open-data/team-history",
        }
        self.assertTrue(expected.issubset(paths))

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
