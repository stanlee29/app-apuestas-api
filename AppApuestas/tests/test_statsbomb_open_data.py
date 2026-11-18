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

    def test_builds_recent_home_and_away_xg_rates(self):
        matches = []
        for index in range(3):
            matches.append({
                "match_id": 200 + index,
                "match_status": "available",
                "match_date": f"2025-06-0{index + 1}",
                "home_team": {"id": 1, "name": "Arsenal"},
                "away_team": {"id": 10 + index, "name": f"Opponent {index}"},
                "home_score": 2,
                "away_score": 1,
            })
            matches.append({
                "match_id": 210 + index,
                "match_status": "available",
                "match_date": f"2025-06-1{index + 1}",
                "home_team": {"id": 20 + index, "name": f"Opponent Away {index}"},
                "away_team": {"id": 2, "name": "Chelsea"},
                "home_score": 1,
                "away_score": 1,
            })

        client = StatsBombOpenData()
        def fake_json(path, ttl=0):
            match_id = int(path.split("/")[1].split(".")[0])
            match = next(item for item in matches if item["match_id"] == match_id)
            home, away = match["home_team"]["name"], match["away_team"]["name"]
            return [
                {"type": {"name": "Shot"}, "team": {"name": home}, "shot": {"statsbomb_xg": 0.6}},
                {"type": {"name": "Shot"}, "team": {"name": away}, "shot": {"statsbomb_xg": 0.3}},
            ]

        with patch.object(client, "_json", side_effect=fake_json):
            rates = client.recent_team_xg(matches, "Arsenal", "Chelsea")

        self.assertIsNotNone(rates)
        self.assertEqual(rates["home_matches_with_xg"], 3)
        self.assertEqual(rates["away_matches_with_xg"], 3)
        self.assertAlmostEqual(rates["lambda_home"], 0.6, places=4)
        self.assertAlmostEqual(rates["lambda_away"], 0.3, places=4)

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
