import unittest

from altenar_feed import (
    FeedConfigurationError,
    FeedSettings,
    normalize_event,
    normalize_market,
    _normalize_selection,
)


class AltenarFeedNormalizationTests(unittest.TestCase):
    def test_normaliza_evento_con_campos_de_feed(self):
        event = normalize_event({
            "EventId": 7775524373,
            "EventDate": "2026-11-18T18:30:00Z",
            "EventName": "Alianza FC vs. Aguila",
            "SportName": "Soccer",
            "CatName": "El Salvador",
            "ChampName": "Primera División",
        })
        self.assertEqual(event["evento_id"], "7775524373")
        self.assertEqual(event["local"], "Alianza FC")
        self.assertEqual(event["visitante"], "Aguila")
        self.assertEqual(event["liga"], "Primera División")
        self.assertFalse(event["en_vivo"])

    def test_marca_evento_en_vivo(self):
        event = normalize_event({"EventId": 123, "EventName": "A vs. B"}, is_live=True)
        self.assertTrue(event["en_vivo"])
        self.assertEqual(event["estado_evento"], "En vivo")

    def test_normaliza_mercado_y_selecciones(self):
        market = normalize_market({
            "MarketId": 18,
            "MarketName": "Total Goals",
            "Spec": "2.5",
            "Selections": [
                {"SelectionName": "Over 2.5", "Price": 1.91, "SelectionId": 1001},
                {"SelectionName": "Under 2.5", "Price": 1.95, "SelectionId": 1002},
            ],
        })
        self.assertEqual(market["nombre"], "Total Goals")
        self.assertEqual(market["linea"], "2.5")
        self.assertEqual(len(market["selecciones"]), 2)
        self.assertEqual(market["selecciones"][0]["cuota"], 1.91)

    def test_no_convierte_precio_invalido_en_cuota(self):
        selection = _normalize_selection({"SelectionName": "Home", "Price": "Suspended"})
        self.assertIsNone(selection["cuota"])

    def test_requiere_configuracion_real_del_operador(self):
        with self.assertRaises(FeedConfigurationError):
            FeedSettings.from_env()


if __name__ == "__main__":
    unittest.main()
