import unittest

import pandas as pd

from motor_probabilidades import calcular_valor_ev, predecir_partido


class MotorProbabilidadesTests(unittest.TestCase):
    def test_ev_positivo_con_cuota_decimal(self):
        resultado = calcular_valor_ev(60, 2.10)
        self.assertAlmostEqual(resultado["valor_esperado"], 0.26, places=4)
        self.assertTrue(resultado["es_valor_positivo"])
        self.assertEqual(resultado["cuota_justa"], 1.67)

    def test_ev_rechaza_cuota_invalida(self):
        with self.assertRaises(ValueError):
            calcular_valor_ev(55, 1.0)

    def test_nombres_de_equipos_no_dependen_de_mayusculas(self):
        historicos = pd.DataFrame([
            ["2026-01-01", "Real Madrid", "Barcelona", 2, 1],
            ["2026-01-08", "Barcelona", "Real Madrid", 1, 1],
            ["2026-01-15", "Real Madrid", "Barcelona", 3, 0],
            ["2026-01-22", "Barcelona", "Real Madrid", 0, 2],
        ], columns=["fecha", "equipo_local", "equipo_visitante", "puntos_local", "puntos_visitante"])

        resultado = predecir_partido(
            "futbol",
            "real madrid",
            "BARCELONA",
            {"futbol": historicos},
        )

        self.assertNotIn("error", resultado)
        self.assertAlmostEqual(
            resultado["prob_victoria_local"] + resultado["prob_empate"] + resultado["prob_victoria_visitante"],
            1.0,
            places=3,
        )

    def test_equipo_inexistente_no_recibe_probabilidad_por_defecto(self):
        historicos = pd.DataFrame([
            ["2026-01-01", "Real Madrid", "Barcelona", 2, 1],
        ], columns=["fecha", "equipo_local", "equipo_visitante", "puntos_local", "puntos_visitante"])

        resultado = predecir_partido(
            "futbol",
            "Real Madrid",
            "Equipo inventado",
            {"futbol": historicos},
        )
        self.assertIn("error", resultado)


if __name__ == "__main__":
    unittest.main()
