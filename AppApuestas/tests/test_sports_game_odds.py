import os
import unittest
from unittest.mock import patch

from sports_game_odds import (
    ProviderConfigurationError,
    ProviderSettings,
    SportsGameOddsClient,
    american_to_decimal,
    normalize_event,
)


class SportsGameOddsTests(unittest.TestCase):
    def test_convierte_cuotas_americanas(self):
        self.assertEqual(american_to_decimal("-110"), 1.9091)
        self.assertEqual(american_to_decimal("+100"), 2.0)
        self.assertEqual(american_to_decimal(150), 2.5)
        self.assertIsNone(american_to_decimal("suspendida"))
        self.assertIsNone(american_to_decimal(0))

    def test_normaliza_evento_y_cuotas_por_casa(self):
        raw = {
            "eventID": "event_123",
            "sportID": "SOCCER",
            "leagueID": "UEFA_CHAMPIONS_LEAGUE",
            "teams": {
                "home": {"names": {"long": "Equipo Local"}},
                "away": {"names": {"long": "Equipo Visitante"}},
            },
            "status": {
                "startsAt": "2026-11-18T20:00:00.000Z",
                "live": False,
                "displayLong": "Upcoming",
                "oddsAvailable": True,
            },
            "odds": {
                "points-home-game-ml-home": {
                    "oddID": "points-home-game-ml-home",
                    "marketName": "Moneyline",
                    "periodID": "game",
                    "statID": "points",
                    "statEntityID": "home",
                    "sideID": "home",
                    "bookOdds": "-110",
                    "bookOddsAvailable": True,
                    "byBookmaker": {
                        "book_a": {
                            "odds": "-110",
                            "available": True,
                            "lastUpdatedAt": "2026-11-18T19:50:00Z",
                        }
                    },
                },
                "points-away-game-ml-away": {
                    "oddID": "points-away-game-ml-away",
                    "marketName": "Moneyline",
                    "periodID": "game",
                    "statID": "points",
                    "statEntityID": "away",
                    "sideID": "away",
                    "bookOdds": "+100",
                    "bookOddsAvailable": True,
                    "byBookmaker": {
                        "book_a": {"odds": "+100", "available": True}
                    },
                },
            },
        }
        event = normalize_event(raw)
        self.assertEqual(event["evento_id"], "event_123")
        self.assertEqual(event["local"], "Equipo Local")
        self.assertEqual(event["visitante"], "Equipo Visitante")
        self.assertEqual(event["liga"], "Champions League")
        self.assertEqual(event["mercados_disponibles"], 1)
        selections = event["mercados"][0]["selecciones"]
        self.assertEqual(len(selections), 2)
        self.assertEqual(selections[0]["casas"][0]["cuota_decimal"], 1.9091)

    def test_clave_obligatoria(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProviderConfigurationError):
                ProviderSettings.from_env()

    def test_consulta_configura_ligas_y_filtros(self):
        settings = ProviderSettings(
            api_key="test-key",
            leagues={"nba": ("NBA",)},
        )
        client = SportsGameOddsClient(settings)
        with patch.object(client, "_get_events", return_value=[]) as request:
            result = client.get_events("nba", days=2, live=True)
        self.assertEqual(result["total_eventos"], 0)
        params = request.call_args.args[0]
        self.assertEqual(params["leagueID"], "NBA")
        self.assertEqual(params["live"], "true")
        self.assertEqual(params["limit"], 100)


if __name__ == "__main__":
    unittest.main()
