import unittest
from unittest.mock import patch

from research_storage import ResearchStorage


class ResearchStorageTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
