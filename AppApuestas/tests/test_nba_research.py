import unittest

import pandas as pd

from nba_research import dataframe_records, game_shots, team_roster


class NBAResearchTests(unittest.TestCase):
    def test_dataframe_records_normalizes_nan_and_limits(self):
        frame = pd.DataFrame([
            {"PLAYER_NAME": "Player A", "LOC_X": 12.5, "SHOT_MADE_FLAG": 1},
            {"PLAYER_NAME": "Player B", "LOC_X": float("nan"), "SHOT_MADE_FLAG": 0},
        ])
        records = dataframe_records(frame, limit=1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["PLAYER_NAME"], "Player A")
        self.assertEqual(records[0]["LOC_X"], 12.5)

        all_records = dataframe_records(frame, limit=10)
        self.assertIsNone(all_records[1]["LOC_X"])

    def test_rejects_invalid_game_id_and_season(self):
        with self.assertRaises(ValueError):
            game_shots("not-a-game")
        with self.assertRaises(ValueError):
            game_shots("0022400001", season="2026")
        with self.assertRaises(ValueError):
            game_shots("0022400001", team_id=-10)

    def test_rejects_invalid_team_roster_parameters(self):
        with self.assertRaises(ValueError):
            team_roster(0)
        with self.assertRaises(ValueError):
            team_roster(1610612737, season="current")


if __name__ == "__main__":
    unittest.main()
