import unittest

from modelos_mercados_statsbomb import (
    build_count_pmf,
    extract_match_counts,
    predict_match_markets,
)
from statsbomb_open_data import StatsBombOpenData


class FakeStatsBomb:
    matches_before_date = staticmethod(StatsBombOpenData.matches_before_date)

    def __init__(self, event_map):
        self.event_map = event_map

    def _json(self, path, ttl=0):
        match_id = int(path.split("/")[1].split(".")[0])
        return self.event_map[match_id]


def make_events(home, away, home_shots=10, away_shots=8, home_corners=5, away_corners=3):
    events = []
    for team, shots in ((home, home_shots), (away, away_shots)):
        for index in range(shots):
            outcome = "Saved" if index % 3 == 0 else "Off T"
            events.append({
                "type": {"name": "Shot"},
                "team": {"name": team},
                "shot": {"outcome": {"name": outcome}},
            })
    for team, corners in ((home, home_corners), (away, away_corners)):
        for _ in range(corners):
            events.append({
                "type": {"name": "Pass"},
                "team": {"name": team},
                "pass": {"type": {"name": "Corner"}},
            })
    for team in (home, away):
        events.append({
            "type": {"name": "Foul Committed"},
            "team": {"name": team},
            "foul_committed": {"card": {"name": "Yellow Card"}},
        })
    return events


class FootballMarketModelTests(unittest.TestCase):
    def test_extracts_shots_corners_fouls_and_cards(self):
        events = make_events("Home FC", "Away FC", home_shots=9, away_shots=7, home_corners=4, away_corners=2)
        result = extract_match_counts(events, "Home FC", "Away FC")
        self.assertEqual(result["Home FC"]["shots"], 9)
        self.assertEqual(result["Home FC"]["shots_on_target"], 3)
        self.assertEqual(result["Away FC"]["shots"], 7)
        self.assertEqual(result["Home FC"]["corners"], 4)
        self.assertEqual(result["Away FC"]["corners"], 2)
        self.assertEqual(result["Home FC"]["fouls"], 1)
        self.assertEqual(result["Home FC"]["yellow_cards"], 1)
        self.assertEqual(result["Home FC"]["total_cards"], 1)

    def test_count_distribution_is_normalized(self):
        poisson, poisson_type = build_count_pmf(8.0, 7.5)
        negative_binomial, nb_type = build_count_pmf(8.0, 15.0)
        self.assertEqual(poisson_type, "Poisson")
        self.assertEqual(nb_type, "Binomial negativa")
        self.assertAlmostEqual(sum(poisson), 1.0, places=9)
        self.assertAlmostEqual(sum(negative_binomial), 1.0, places=9)

    def test_market_prediction_excludes_target_day_and_future(self):
        event_map = {}
        matches = []
        match_id = 100
        for index in range(4):
            home_opponent = f"Opponent Home {index}"
            matches.append({
                "match_id": match_id,
                "match_status": "available",
                "match_date": f"2025-05-{1 + index:02d}",
                "home_team": {"home_team_name": "Home FC"},
                "away_team": {"away_team_name": home_opponent},
                "home_score": 2,
                "away_score": 1,
            })
            event_map[match_id] = make_events("Home FC", home_opponent, home_shots=10 + index)
            match_id += 1

        for index in range(4):
            away_opponent = f"Opponent Away {index}"
            matches.append({
                "match_id": match_id,
                "match_status": "available",
                "match_date": f"2025-05-{10 + index:02d}",
                "home_team": {"home_team_name": away_opponent},
                "away_team": {"away_team_name": "Away FC"},
                "home_score": 1,
                "away_score": 1,
            })
            event_map[match_id] = make_events(away_opponent, "Away FC", away_shots=8 + index)
            match_id += 1

        # Estos partidos no deben entrar en el entrenamiento del objetivo.
        for match_date in ("2025-05-20", "2025-05-21"):
            matches.append({
                "match_id": match_id,
                "match_status": "available",
                "match_date": match_date,
                "home_team": {"home_team_name": "Home FC"},
                "away_team": {"away_team_name": "Away FC"},
                "home_score": 8,
                "away_score": 0,
            })
            event_map[match_id] = make_events("Home FC", "Away FC", home_shots=40, away_shots=1)
            match_id += 1

        client = FakeStatsBomb(event_map)
        result = predict_match_markets(
            client, matches, "2025-05-20", "Home FC", "Away FC", limit=4
        )
        self.assertEqual(result["muestra"]["local_en_casa"], 4)
        self.assertEqual(result["muestra"]["visitante_fuera"], 4)
        self.assertEqual(result["fecha_objetivo"], "2025-05-20")
        self.assertLess(result["mercados"]["remates"]["local"]["media_esperada"], 20)
        self.assertIn("corners", result["mercados"])
        self.assertIn("tarjetas_totales", result["mercados"])
        self.assertTrue(any("mismo día" in warning for warning in result["advertencias"]))

    def test_rejects_insufficient_history(self):
        client = FakeStatsBomb({})
        with self.assertRaises(ValueError):
            predict_match_markets(client, [], "2025-05-20", "Home FC", "Away FC")


if __name__ == "__main__":
    unittest.main()
