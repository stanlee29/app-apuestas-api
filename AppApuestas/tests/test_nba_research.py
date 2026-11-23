import unittest

import pandas as pd

from nba_research import dataframe_records, game_shots, game_boxscore, game_play_by_play, season_stats, team_roster, normalize_scoreboard_rows


class NBAResearchTests(unittest.TestCase):
    def test_scoreboard_combines_header_and_line_scores_into_home_away(self):
        headers = [{
            "gameId": "0022600011",
            "gameCode": "20261122/NYKBOS",
            "gameStatusText": "Final",
        }]
        lines = [
            {"gameId": "0022600011", "teamId": 2, "teamName": "Celtics",
             "teamCity": "Boston", "teamTricode": "BOS", "score": 110},
            {"gameId": "0022600011", "teamId": 1, "teamName": "Knicks",
             "teamCity": "New York", "teamTricode": "NYK", "score": 102},
        ]
        games = normalize_scoreboard_rows(headers, lines)
        self.assertEqual(games[0]["homeTeam"]["teamName"], "Celtics")
        self.assertEqual(games[0]["awayTeam"]["teamName"], "Knicks")
        self.assertEqual(games[0]["homeTeam"]["score"], 110)
        self.assertEqual(games[0]["awayTeam"]["score"], 102)

    def test_scoreboard_does_not_invent_sides_without_valid_game_code(self):
        headers = [{"gameId": "0022600012", "gameCode": "no-team-code"}]
        lines = [
            {"gameId": "0022600012", "teamTricode": "AAA", "teamName": "A"},
            {"gameId": "0022600012", "teamTricode": "BBB", "teamName": "B"},
        ]
        games = normalize_scoreboard_rows(headers, lines)
        self.assertNotIn("homeTeam", games[0])
        self.assertNotIn("awayTeam", games[0])

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

    def test_rejects_invalid_game_id_for_boxscore_and_play_by_play(self):
        with self.assertRaises(ValueError):
            game_boxscore("bad-id")
        with self.assertRaises(ValueError):
            game_play_by_play("bad-id")

    def test_rejects_invalid_season_stats_filters(self):
        with self.assertRaises(ValueError):
            season_stats(season="2026", entity="player")
        with self.assertRaises(ValueError):
            season_stats(entity="coach")
        with self.assertRaises(ValueError):
            season_stats(per_mode="PerPossession")
        with self.assertRaises(ValueError):
            season_stats(measure_type="Fake")


if __name__ == "__main__":
    unittest.main()
