import unittest

from nfl_research import play_by_play, schedules, weekly_rosters


class NFLResearchTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
