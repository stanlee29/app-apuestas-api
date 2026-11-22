import unittest

from espn_public_data import normalize_event, normalize_roster, normalize_team_stats


class ESPNNormalizationTests(unittest.TestCase):
    def test_normalize_event_current_players_and_score(self):
        raw = {
            "id": "401234567",
            "date": "2026-11-22T14:00Z",
            "season": {"year": 2026},
            "competitions": [{
                "status": {"type": {"state": "post", "completed": True, "shortDetail": "FT"}},
                "venue": {"fullName": "Stadium"},
                "competitors": [
                    {"homeAway": "home", "score": "2", "team": {"id": "10", "displayName": "Home FC"}},
                    {"homeAway": "away", "score": "1", "team": {"id": "11", "displayName": "Away FC"}},
                ],
            }],
        }
        item = normalize_event(raw, "eng.1")
        self.assertEqual(item["status"], "finished")
        self.assertEqual(item["score_home"], 2)
        self.assertEqual(item["home_team"]["name"], "Home FC")
        self.assertEqual(item["away_team"]["id"], "11")

    def test_normalize_live_event(self):
        raw = {"id": "22", "competitions": [{
            "status": {"type": {"state": "in", "shortDetail": "67'"}},
            "competitors": [],
        }]}
        self.assertEqual(normalize_event(raw, "esp.1")["status"], "live")

    def test_normalize_team_stats(self):
        payload = {"boxscore": {"teams": [{
            "team": {"id": "10", "displayName": "Home FC"},
            "homeAway": "home",
            "statistics": [{"name": "totalShots", "label": "Shots", "displayValue": "12"}],
        }]}}
        rows = normalize_team_stats(payload)
        self.assertEqual(rows[0]["team"], "Home FC")
        self.assertEqual(rows[0]["statistics"][0]["value"], "12")

    def test_normalize_current_roster_and_season_stats(self):
        payload = {
            "season": {"displayName": "2026-27"},
            "timestamp": "2026-11-22T00:00:00Z",
            "athletes": [{
                "id": "50",
                "displayName": "Current Player",
                "jersey": "9",
                "age": 24,
                "citizenship": "Spain",
                "position": {"abbreviation": "F"},
                "status": {"name": "Active"},
                "injuries": [],
                "statistics": {"splits": {"categories": [{
                    "stats": [
                        {"name": "appearances", "displayValue": "9"},
                        {"name": "totalGoals", "displayValue": "4"},
                        {"name": "goalAssists", "displayValue": "2"},
                    ]
                }]}},
            }],
        }
        result = normalize_roster(payload)
        player = result["jugadores"][0]
        self.assertEqual(result["season"], "2026-27")
        self.assertEqual(player["stats"]["appearances"], "9")
        self.assertEqual(player["stats"]["goals"], "4")
        self.assertEqual(player["nationality"], "Spain")


if __name__ == "__main__":
    unittest.main()
