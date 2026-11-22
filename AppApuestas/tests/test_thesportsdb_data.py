import unittest

from thesportsdb_data import normalize_event, normalize_lineup, normalize_roster, normalize_stats


class TheSportsDBNormalizationTests(unittest.TestCase):
    def test_normalize_current_event(self):
        raw = {
            "idEvent": "2398541",
            "strLeague": "Brazilian Serie A",
            "strTimestamp": "2026-11-22T19:00:00",
            "strStatus": "2H",
            "idHomeTeam": "134297",
            "strHomeTeam": "Athletico Paranaense",
            "idAwayTeam": "137818",
            "strAwayTeam": "Remo",
            "intHomeScore": "4",
            "intAwayScore": "2",
            "strVenue": "Arena da Baixada",
        }
        event = normalize_event(raw)
        self.assertEqual(event["status"], "live")
        self.assertEqual(event["score_home"], 4)
        self.assertEqual(event["home_team"]["name"], "Athletico Paranaense")
        self.assertEqual(event["away_team"]["id"], "137818")

    def test_normalize_lineup_separates_starters(self):
        rows = normalize_lineup([
            {"strPlayer": "Home Starter", "strHome": "Yes", "strSubstitute": "No", "strPosition": "Goalkeeper"},
            {"strPlayer": "Away Sub", "strHome": "No", "strSubstitute": "Yes"},
        ])
        self.assertTrue(rows[0]["starter"])
        self.assertEqual(rows[0]["side"], "home")
        self.assertFalse(rows[1]["starter"])
        self.assertEqual(rows[1]["side"], "away")

    def test_normalize_stats(self):
        rows = normalize_stats([{"strStat": "Total Shots", "intHome": "18", "intAway": "14"}])
        self.assertEqual(rows[0], {"name": "Total Shots", "home": "18", "away": "14"})

    def test_roster_filters_staff_and_limits_free_sample(self):
        rows = [
            {"idPlayer": str(i), "strPlayer": "P" + str(i), "strStatus": "Active", "strPosition": "Forward"}
            for i in range(12)
        ]
        rows.append({"idPlayer": "coach", "strPlayer": "Coach", "strStatus": "Coaching"})
        roster = normalize_roster(rows)
        self.assertEqual(len(roster), 10)
        self.assertTrue(all(player["name"] != "Coach" for player in roster))


if __name__ == "__main__":
    unittest.main()
