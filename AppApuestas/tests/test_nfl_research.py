import unittest
import pandas as pd

from nfl_research import play_by_play, schedules, weekly_rosters, statistics, nextgen_stats, pfr_advanced_stats, _frame_records


class NFLResearchTests(unittest.TestCase):
    def test_frame_records_cleans_nan_and_dates_for_json(self):
        frame = pd.DataFrame([
            {"player_name": "Player A", "epa": float("nan"), "week": 1},
        ])
        rows = _frame_records(frame, 10)
        self.assertIsNone(rows[0]["epa"])
        self.assertEqual(rows[0]["player_name"], "Player A")

    def test_rejects_invalid_season(self):
        with self.assertRaises(ValueError):
            schedules(1990)

    def test_rejects_invalid_week(self):
        with self.assertRaises(ValueError):
            schedules(2026, week=0)

    def test_play_by_play_requires_game_id(self):
        with self.assertRaises(ValueError):
            play_by_play("../bad", 2026)

    def test_roster_requires_supported_season(self):
        with self.assertRaises(ValueError):
            weekly_rosters(2001)
    def test_rejects_invalid_stat_dimensions(self):
        with self.assertRaises(ValueError):
            statistics(2026, entity="coach")
        with self.assertRaises(ValueError):
            statistics(2026, summary_level="daily")
        with self.assertRaises(ValueError):
            nextgen_stats(2026, stat_type="kicking")
        with self.assertRaises(ValueError):
            pfr_advanced_stats(2026, stat_type="special")



if __name__ == "__main__":
    unittest.main()
