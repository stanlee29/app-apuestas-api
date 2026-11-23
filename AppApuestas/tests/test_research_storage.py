import unittest
from unittest.mock import patch

from research_storage import ResearchStorage


class ResearchStorageTests(unittest.TestCase):
    def _storage(self):
        with patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "server-secret",
                "SUPABASE_RESEARCH_TABLE": "research_snapshots",
            },
            clear=False,
        ):
            return ResearchStorage()

    def test_storage_is_disabled_without_credentials(self):
        with patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""}, clear=False):
            storage = ResearchStorage()
            self.assertFalse(storage.configured)
            result = storage.save_snapshot("pitchapi", "m_123456", "match", {"a": 1})
            self.assertFalse(result["guardado"])
            self.assertEqual(result["motivo"], "SUPABASE_NOT_CONFIGURED")

    def test_storage_rejects_non_https_url(self):
        with patch.dict("os.environ", {"SUPABASE_URL": "http://example.com", "SUPABASE_SERVICE_ROLE_KEY": "secret"}, clear=False):
            self.assertFalse(ResearchStorage().configured)

    def test_team_filter_quotes_team_name_and_rejects_filter_injection(self):
        self.assertEqual(
            ResearchStorage._team_or_filter("  Real Madrid  "),
            '(home_team.eq."Real Madrid",away_team.eq."Real Madrid")',
        )
        with self.assertRaises(ValueError):
            ResearchStorage._team_or_filter('Real Madrid),source.eq.MLB')

    def test_team_archive_maps_results_and_advanced_xg_without_filling_missing_values(self):
        storage = self._storage()
        results = [{
            "source": "Football-Data.co.uk",
            "competition_name": "E0",
            "season": "2025/26",
            "match_date": "2026-05-10",
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "home_goals": 2,
            "away_goals": 1,
            "stats": {"hs": 18, "as": 9, "hst": 7, "ast": 3, "hc": 6, "ac": 2, "hy": 1, "ay": 2},
        }]
        advanced = [{
            "source": "american_soccer_analysis",
            "source_license": "CC BY-SA 4.0",
            "competition_name": "MLS",
            "season_name": "2025",
            "match_date": "2025-09-01",
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "home_score": 1,
            "away_score": 0,
            "home_xg": 1.7,
            "away_xg": 0.6,
            "home_shots": 14,
            "away_shots": 8,
            "home_shots_on_target": 6,
            "away_shots_on_target": 2,
            "home_corners": 5,
            "away_corners": 3,
            "home_yellow_cards": 1,
            "away_yellow_cards": 0,
            "home_red_cards": None,
            "away_red_cards": None,
        }]
        with patch.object(storage, "_get_rows", side_effect=[results, advanced]) as get_rows:
            data = storage.team_archive("Arsenal", before_date="2026-06-01", limit=5)

        self.assertEqual(data["resumen"]["ganados"], 1)
        self.assertEqual(data["partidos"][0]["remates_favor"], 18)
        self.assertEqual(data["metricas_avanzadas"][0]["xg_favor"], 1.7)
        self.assertIsNone(data["metricas_avanzadas"][0]["rojas_favor"])
        self.assertEqual(get_rows.call_count, 2)

    def test_market_archive_follows_canonical_event_alias(self):
        storage = self._storage()
        with patch.object(
            storage,
            "_get_rows",
            side_effect=[
                [{"canonical_event_id": "af:12345"}],
                [{"event_id": "af:12345", "opening_odds": 2.1, "closing_odds": 1.95}],
            ],
        ):
            data = storage.market_archive("gp:999")

        self.assertEqual(data["event_ids_consultados"], ["gp:999", "af:12345"])
        self.assertEqual(data["mercados"][0]["closing_odds"], 1.95)


if __name__ == "__main__":
    unittest.main()
