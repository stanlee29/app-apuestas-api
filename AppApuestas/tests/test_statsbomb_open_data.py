import unittest
from unittest.mock import patch

from statsbomb_open_data import StatsBombOpenData


class StatsBombOpenDataTests(unittest.TestCase):
    def test_team_name_from_match_spec_object(self):
        self.assertEqual(StatsBombOpenData._team_name({"id": 1, "name": "Arsenal"}), "Arsenal")
        self.assertEqual(StatsBombOpenData._team_name({"home_team_name": "Liverpool"}), "Liverpool")

    def test_event_locations_are_validated(self):
        self.assertEqual(StatsBombOpenData._event_location({"location": [110, 40]}), (110.0, 40.0))
        self.assertIsNone(StatsBombOpenData._event_location({"location": [121, 40]}))
        self.assertIsNone(StatsBombOpenData._event_location({"location": "invalid"}))

    def test_extracts_shots_xg_h2h_and_heatmaps(self):
        match = {
            "match_id": 100,
            "match_status": "available",
            "match_date": "2025-05-01",
            "kick_off": "16:00:00.000",
            "competition": {"id": 9, "name": "Premier League"},
            "season": {"id": 281, "name": "2024/2025"},
            "home_team": {"id": 1, "name": "Arsenal"},
            "away_team": {"id": 2, "name": "Chelsea"},
            "home_score": 1,
            "away_score": 0,
        }
        events = [
            {
                "type": {"name": "Shot"},
                "team": {"name": "Arsenal"},
                "player": {"name": "Forward A"},
                "location": [110, 40],
                "shot": {
                    "statsbomb_xg": 0.43,
                    "outcome": {"name": "Goal"},
                    "body_part": {"name": "Right Foot"},
                    "technique": {"name": "Normal"},
                },
            },
            {
                "type": {"name": "Pass"},
                "team": {"name": "Arsenal"},
                "player": {"name": "Midfielder B"},
                "location": [60, 35],
                "pass": {"type": {"name": "Corner"}},
            },
            {
                "type": {"name": "Foul Committed"},
                "team": {"name": "Chelsea"},
                "player": {"name": "Defender C"},
                "location": [50, 30],
                "foul_committed": {"card": {"name": "Yellow Card"}},
            },
        ]
        client = StatsBombOpenData()

        def fake_json(path, ttl=0):
            if path == "matches/9/281.json":
                return [match]
            if path == "events/100.json":
                return events
            if path == "lineups/100.json":
                return [{"team_id": 1, "lineup": []}]
            raise AssertionError(path)

        with patch.object(client, "_json", side_effect=fake_json):
            result = client.match_analysis(100, 9, 281)

        self.assertEqual(result["metricas"]["local"]["xg"], 0.43)
        self.assertEqual(result["metricas"]["local"]["remates"], 1)
        self.assertEqual(result["metricas"]["local"]["remates_a_puerta"], 1)
        self.assertEqual(result["metricas"]["corners"]["Arsenal"], 1)
        self.assertEqual(result["metricas"]["tarjetas"]["Chelsea"]["yellow"], 1)
        self.assertEqual(result["total_remates"], 1)
        self.assertEqual(result["h2h_misma_competicion_temporada"][0]["home"], "Arsenal")
        self.assertTrue(result["mapas_calor"]["teams"][0]["cells"])
        self.assertEqual(result["atribucion_requerida"], "StatsBomb")


if __name__ == "__main__":
    unittest.main()
