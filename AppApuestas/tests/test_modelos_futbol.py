import unittest
from datetime import date, timedelta

from modelos_futbol import dixon_coles_tau, predict_from_matches, poisson_pmf


def make_matches():
    rows = []
    teams = ["City FC", "United FC", "Rovers", "Athletic"]
    start = date(2026, 1, 1)
    for index in range(32):
        home = teams[index % 4]
        away = teams[(index + 1 + (index // 4)) % 4]
        if home == away:
            away = teams[(teams.index(home) + 1) % 4]
        rows.append({
            "match_status": "available",
            "match_date": (start + timedelta(days=index * 3)).isoformat(),
            "home_team": {"id": index + 1, "name": home},
            "away_team": {"id": index + 10, "name": away},
            "home_score": (index % 4) + 1,
            "away_score": index % 3,
        })
    return rows


class FootballModelTests(unittest.TestCase):
    def test_poisson_pmf(self):
        self.assertAlmostEqual(poisson_pmf(0, 1.0), 0.36787944117, places=8)

    def test_dixon_coles_adjustment_low_score(self):
        self.assertGreater(dixon_coles_tau(0, 0, 1.4, 1.1, -0.08), 1.0)
        self.assertGreater(dixon_coles_tau(1, 1, 1.4, 1.1, -0.08), 1.0)
        self.assertEqual(dixon_coles_tau(2, 1, 1.4, 1.1, -0.08), 1.0)

    def test_prediction_has_normalized_probabilities_and_derived_markets(self):
        result = predict_from_matches(make_matches(), "City FC", "United FC")
        probs = result["probabilidades_1x2_pct"]
        self.assertAlmostEqual(sum(probs.values()), 100.0, places=1)
        self.assertIn("2.5", result["totales_goles_pct"])
        self.assertIn("si", result["ambos_marcan_pct"])
        self.assertGreater(len(result["marcadores_mas_probables"]), 0)
        self.assertEqual(result["fuente_historica"], "StatsBomb Open Data")
        self.assertTrue(result["advertencias"])

    def test_rejects_same_team(self):
        with self.assertRaises(ValueError):
            predict_from_matches(make_matches(), "City FC", "City FC")

    def test_rejects_small_sample(self):
        with self.assertRaises(ValueError):
            predict_from_matches(make_matches()[:10], "City FC", "United FC")


if __name__ == "__main__":
    unittest.main()
