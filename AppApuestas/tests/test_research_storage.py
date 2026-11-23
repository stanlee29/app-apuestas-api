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

    def test_new_secret_key_uses_apikey_without_bearer(self):
        with patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SECRET_KEY": "sb_secret_example",
                "SUPABASE_SERVICE_ROLE_KEY": "legacy_should_not_win",
            },
            clear=False,
        ):
            headers = ResearchStorage()._headers()
        self.assertEqual(headers["apikey"], "sb_secret_example")
        self.assertNotIn("Authorization", headers)

    def test_legacy_service_role_key_keeps_bearer_compatibility(self):
        with patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SECRET_KEY": "",
                "SUPABASE_SERVICE_ROLE_KEY": "legacy-jwt",
            },
            clear=False,
        ):
            headers = ResearchStorage()._headers()
        self.assertEqual(headers["apikey"], "legacy-jwt")
        self.assertEqual(headers["Authorization"], "Bearer legacy-jwt")

    def test_team_filter_quotes_team_name_and_rejects_filter_injection(self):
        self.assertEqual(
            ResearchStorage._team_or_filter("  Real Madrid  "),
            '(home_team.eq."Real Madrid",away_team.eq."Real Madrid")',
        )
        with self.assertRaises(ValueError):
            ResearchStorage._team_or_filter('Real Madrid),source.eq.MLB')

    def test_team_archive_resolves_alias_and_preserves_home_away_orientation(self):
        storage = self._storage()
        identities = [{
            "provider": "FotMob",
            "provider_team_id": "123",
            "canonical_team_name": "Atlas FC",
            "provider_team_name": "Atlético Atlas",
            "confidence": 0.95,
        }]
        results = [{
            "source": "Football-Data.co.uk",
            "competition_name": "E0",
            "season": "2025/26",
            "match_date": "2026-05-10",
            "home_team": "Chelsea",
            "away_team": "Atlético Atlas",
            "home_goals": 0,
            "away_goals": 2,
            "stats": {"hs": 7, "as": 19, "hst": 2, "ast": 8, "hc": 2, "ac": 9, "hy": 2, "ay": 1},
        }]
        advanced = [{
            "source": "american_soccer_analysis",
            "source_license": "CC BY-SA 4.0",
            "competition_name": "MLS",
            "season_name": "2025",
            "match_date": "2025-09-01",
            "home_team": "Atlético Atlas",
            "away_team": "Rival",
            "home_score": 1,
            "away_score": 0,
            "home_xg": 1.7,
            "away_xg": 0.6,
            "home_shots": None,
            "away_shots": None,
            "home_shots_on_target": 6,
            "away_shots_on_target": 2,
            "home_corners": 5,
            "away_corners": 3,
            "home_yellow_cards": 1,
            "away_yellow_cards": 0,
            "home_red_cards": None,
            "away_red_cards": None,
        }]
        with patch.object(storage, "_get_rows", side_effect=[identities, results, advanced]) as get_rows:
            data = storage.team_archive("Atlas FC", before_date="2026-06-01", limit=5)

        self.assertEqual(data["nombres_alternativos"], ["Atlético Atlas"])
        self.assertEqual(data["resumen"]["ganados"], 1)
        self.assertEqual(data["partidos"][0]["condicion"], "visitante")
        self.assertEqual(data["partidos"][0]["marcador"], "2-0")
        self.assertEqual(data["partidos"][0]["remates_favor"], 19)
        self.assertEqual(data["partidos"][0]["nombre_en_fuente"], "Atlético Atlas")
        self.assertEqual(data["metricas_avanzadas"][0]["xg_favor"], 1.7)
        self.assertIsNone(data["metricas_avanzadas"][0]["remates_favor"])
        self.assertEqual(get_rows.call_count, 3)

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
