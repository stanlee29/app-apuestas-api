import unittest

from ganaplay_public_feed import normalize_event, _decimal_price, _localize_datetime


class GanaPlayPublicFeedTests(unittest.TestCase):
    def test_normalizes_event_with_teams_and_markets(self):
        payload = {
            "eventId": "gp-123",
            "eventName": "Alianza FC vs CD Aguila",
            "sportName": "Fútbol",
            "competitionName": "Primera División",
            "startDate": "2026-11-24T20:00:00Z",
            "homeTeam": {"name": "Alianza FC"},
            "awayTeam": {"name": "CD Aguila"},
            "markets": [{
                "marketName": "1X2",
                "selections": [
                    {"name": "Alianza FC", "price": 1.95},
                    {"name": "Empate", "price": 3.2},
                    {"name": "CD Aguila", "price": 3.8},
                ],
            }],
        }
        result = normalize_event(payload, "https://sb2frontend-altenar2.biahosted.com/api/Widget/GetEvents")
        self.assertIsNotNone(result)
        self.assertEqual(result["evento_id"], "gp-123")
        self.assertEqual(result["local"], "Alianza FC")
        self.assertEqual(result["visitante"], "CD Aguila")
        self.assertEqual(result["liga"], "Primera División")
        self.assertEqual(result["total_mercados"], 1)
        self.assertEqual(result["total_selecciones_con_cuota"], 3)
        self.assertEqual(result["mercados"][0]["selecciones"][0]["cuota_decimal"], 1.95)
        self.assertTrue(result["solo_lectura"])

    def test_normalizes_participants_array_and_title(self):
        payload = {
            "id": 42,
            "name": "Team A vs Team B",
            "startTime": 1795550400,
            "participants": [{"name": "Team A"}, {"name": "Team B"}],
        }
        result = normalize_event(payload, "https://ganaplay.sv/api/events")
        self.assertIsNotNone(result)
        self.assertEqual(result["local"], "Team A")
        self.assertEqual(result["visitante"], "Team B")

    def test_rejects_non_fixture_objects(self):
        self.assertIsNone(normalize_event({"id": 1, "name": "Premier League"}, "https://ganaplay.sv/api/leagues"))

    def test_decimal_prices_only_accept_decimal_odds(self):
        self.assertEqual(_decimal_price("1.85"), 1.85)
        self.assertIsNone(_decimal_price("0.64"))
        self.assertIsNone(_decimal_price("suspended"))

    def test_naive_datetime_is_assumed_el_salvador(self):
        utc_value, local_date = _localize_datetime("2026-11-24 01:00:00")
        self.assertEqual(local_date, "2026-11-24")
        self.assertTrue(utc_value.endswith("Z"))


if __name__ == "__main__":
    unittest.main()
