import unittest

from extractor_ganaplay import americana_a_decimal, convertir_a_utc6, extraer_cuotas


class ExtractorTests(unittest.TestCase):
    def test_cuotas_americanas_a_decimal(self):
        self.assertEqual(americana_a_decimal(-150), 1.667)
        self.assertEqual(americana_a_decimal(130), 2.3)
        self.assertIsNone(americana_a_decimal(None))
        self.assertIsNone(americana_a_decimal(0))

    def test_no_crea_cuotas_si_fuente_no_entrega_moneyline(self):
        cuotas, proveedor = extraer_cuotas([])
        self.assertEqual(cuotas, {"local": None, "empate": None, "visitante": None})
        self.assertIsNone(proveedor)

    def test_lee_moneyline_estructurado_de_esquema_espn(self):
        cuotas, proveedor = extraer_cuotas([{
            "provider": {"name": "Bookmaker"},
            "homeTeamOdds": {"moneyLine": -150},
            "awayTeamOdds": {"moneyLine": 130},
        }])
        self.assertEqual(proveedor, "Bookmaker")
        self.assertEqual(cuotas["local"], 1.667)
        self.assertEqual(cuotas["visitante"], 2.3)

    def test_convierte_utc_a_hora_de_el_salvador(self):
        momento, texto = convertir_a_utc6("2026-11-18T18:00:00Z")
        self.assertEqual(texto, "2026-11-18 12:00")
        self.assertEqual(momento.utcoffset().total_seconds(), -21600)


if __name__ == "__main__":
    unittest.main()
