import unittest
from datetime import date, timedelta

from modelos_futbol import dixon_coles_tau, evaluate_walk_forward, predict_from_matches, poisson_pmf


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

    def test_blends_recent_xg_when_sample_is_sufficient(self):
        xg_rates = {
            "lambda_home": 1.8,
            "lambda_away": 0.9,
            "home_matches_with_xg": 5,
            "away_matches_with_xg": 4,
        }
        result = predict_from_matches(make_matches(), "City FC", "United FC", xg_rates=xg_rates)
        self.assertEqual(result["metodo_tasas_goles"], "xG reciente + goles reales")
        self.assertEqual(result["xg_reciente"]["lambda_home"], 1.8)
        self.assertGreater(result["goles_esperados"]["local"], 0.0)

    def test_walk_forward_reports_out_of_sample_metrics(self):
        result = evaluate_walk_forward(make_matches(), min_train=20)
        self.assertGreater(result["partidos_evaluados"], 0)
        self.assertIn("brier_multiclase", result["metricas"])
        self.assertIn("log_loss", result["metricas"])
        self.assertIn("accuracy", result["metricas"])
        self.assertEqual(result["metodo"], "walk-forward cronológico sin datos del día objetivo")
        self.assertTrue(all("fecha" in row for row in result["predicciones"]))

    def test_accepts_statsbomb_home_team_name_fields(self):
        rows = make_matches()
        rows = [{
            **row,
            "home_team": {"home_team_name": row["home_team"]["name"]},
            "away_team": {"away_team_name": row["away_team"]["name"]},
        } for row in rows]
        result = predict_from_matches(rows, "City FC", "United FC")
        self.assertEqual(result["partido"]["local"], "City FC")
        self.assertEqual(result["partido"]["visitante"], "United FC")

    def test_rejects_same_team(self):
        with self.assertRaises(ValueError):
            predict_from_matches(make_matches(), "City FC", "City FC")

    def test_rejects_small_sample(self):
        with self.assertRaises(ValueError):
            predict_from_matches(make_matches()[:10], "City FC", "United FC")


if __name__ == "__main__":
    unittest.main()
