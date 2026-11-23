import unittest

from mlb_research import statcast


class MLBResearchTests(unittest.TestCase):
    def test_rejects_inverted_date_range(self):
        with self.assertRaises(ValueError):
            statcast("2026-10-10", "2026-10-09")

    def test_limits_date_window(self):
        with self.assertRaises(ValueError):
            statcast("2026-10-01", "2026-10-05")

    def test_requires_one_player_filter(self):
        with self.assertRaises(ValueError):
            statcast("2026-10-01", "2026-10-02", batter_id=123, pitcher_id=456)


if __name__ == "__main__":
    unittest.main()
