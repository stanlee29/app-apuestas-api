import unittest
from unittest.mock import patch

from integraciones_pitchapi import PitchAPIClient, PitchAPIError


class PitchAPITests(unittest.TestCase):
    def test_requiere_clave_para_consultar(self):
        client = PitchAPIClient(api_key="")
        with self.assertRaises(PitchAPIError) as context:
            client.list_leagues()
        self.assertEqual(context.exception.code, "PITCHAPI_NOT_CONFIGURED")

    def test_valida_identificador_de_partido(self):
        with self.assertRaises(ValueError):
            PitchAPIClient._validate_match_id("12345")
        PitchAPIClient._validate_match_id("m_B8x2K9")

    def test_agrega_xg_remates_y_remates_a_puerta_por_equipo(self):
        client = PitchAPIClient(api_key="test-key")
        responses = {
            "/matches/m_B8x2K9": {
                "home_team": {"id": "t_home", "name": "Home FC"},
                "away_team": {"id": "t_away", "name": "Away FC"},
            },
            "/matches/m_B8x2K9/shots": {
                "periods": [
                    {"period": "FirstHalf", "shots": [
                        {"team_id": "t_home", "expected_goals": 0.3, "is_on_target": True, "event_type": "Goal"},
                        {"team_id": "t_away", "expected_goals": 0.1, "is_on_target": False, "event_type": "Miss"},
                    ]},
                    {"period": "SecondHalf", "shots": [
                        {"team_id": "t_home", "expected_goals": 0.2, "is_on_target": True, "event_type": "AttemptSaved"},
                    ]},
                ]
            },
            "/matches/m_B8x2K9/stats": {
                "periods": [{
                    "period": "All",
                    "groups": [{
                        "group_name": "Top stats",
                        "items": [{"key": "total_shots", "title": "Total shots", "home": "2", "away": "1"}],
                    }],
                }],
            },
            "/matches/m_B8x2K9/players": {"players": [{"id": "p_1", "name": "Player"}]},
            "/matches/m_B8x2K9/h2h": {"recent_matches": []},
            "/matches/m_B8x2K9/heatmaps": {"grid": {"length": 16, "width": 12}, "teams": [], "players": []},
            "/matches/m_B8x2K9/advanced": {"teams": []},
            "/matches/m_B8x2K9/events": {"events": []},
            "/matches/m_B8x2K9/momentum": {"points": []},
        }

        def fake_get(path, params=None, optional=False):
            return responses.get(path, {})

        with patch.object(client, "_get", side_effect=fake_get):
            result = client.match_analysis("m_B8x2K9")

        self.assertEqual(result["metricas_calculadas_desde_remates"]["local"]["remates"], 2)
        self.assertEqual(result["metricas_calculadas_desde_remates"]["local"]["remates_a_puerta"], 2)
        self.assertEqual(result["metricas_calculadas_desde_remates"]["local"]["xg"], 0.5)
        self.assertEqual(result["metricas_calculadas_desde_remates"]["visitante"]["remates"], 1)
        self.assertEqual(result["estadisticas_equipo"][0]["key"], "total_shots")
        self.assertTrue(result["disponibilidad"]["mapas_calor"])


if __name__ == "__main__":
    unittest.main()
