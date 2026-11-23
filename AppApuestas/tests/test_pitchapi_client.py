import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import integraciones_pitchapi
from integraciones_pitchapi import PitchAPIClient, PitchAPIError


class PitchAPITests(unittest.TestCase):
    def setUp(self):
        integraciones_pitchapi._CACHE.clear()

    def test_requiere_clave_para_consultar(self):
        client = PitchAPIClient(api_key="")
        with self.assertRaises(PitchAPIError) as context:
            client.list_leagues()
        self.assertEqual(context.exception.code, "PITCHAPI_NOT_CONFIGURED")

    def test_valida_identificador_de_partido(self):
        with self.assertRaises(ValueError):
            PitchAPIClient._validate_match_id("12345")
        PitchAPIClient._validate_match_id("m_B8x2K9")

    def test_agrega_xg_remates_mapas_redes_y_eventos_por_partido(self):
        client = PitchAPIClient(api_key="test-key")
        responses = {
            "/matches/m_B8x2K9": {
                "home_team": {"id": "t_home", "name": "Home FC"},
                "away_team": {"id": "t_away", "name": "Away FC"},
            },
            "/matches/m_B8x2K9/shots": {
                "periods": [
                    {"period": "FirstHalf", "shots": [
                        {"team_id": "t_home", "expected_goals": 0.3, "is_on_target": True,
                         "event_type": "Goal", "x": 100, "y": 30},
                        {"team_id": "t_away", "expected_goals": 0.1, "is_on_target": False,
                         "event_type": "Miss", "x": 9, "y": 40},
                    ]},
                    {"period": "SecondHalf", "shots": [
                        {"team_id": "t_home", "expected_goals": 0.2, "is_on_target": True,
                         "event_type": "AttemptSaved", "x": 130, "y": 30},
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
            "/matches/m_B8x2K9/players": [
                {"player": {"id": "p_1", "name": "Player"}, "team_id": "t_home", "stats": []}
            ],
            "/matches/m_B8x2K9/h2h": {"recent_matches": [{"finished": True}]},
            "/matches/m_B8x2K9/heatmaps": {
                "grid": {"length": 16, "width": 12},
                "teams": [{"team": {"id": "t_home"}, "cells": [[1, 2, 4]], "actions": 4}],
                "players": [{"player": {"id": "p_1"}, "cells": [[1, 2, 2]], "actions": 2}],
            },
            "/matches/m_B8x2K9/advanced": {"teams": [{"team": {"id": "t_home"}, "passing": {}}]},
            "/matches/m_B8x2K9/advanced/players": [
                {"player": {"id": "p_1", "name": "Player"}, "team_id": "t_home"}
            ],
            "/matches/m_B8x2K9/advanced/network": {
                "networks": [{"team": {"id": "t_home"}, "nodes": [], "edges": []}]
            },
            "/matches/m_B8x2K9/lineups": {"home": {"starters": []}, "away": {"starters": []}},
            "/matches/m_B8x2K9/events": {"events": [{"event_type": "goal"}]},
            "/matches/m_B8x2K9/momentum": {"points": [{"minute": 10, "value": 2}]},
        }

        def fake_get(path, params=None, optional=False, cache_seconds=None):
            return responses.get(path, {})

        with patch.object(client, "_get", side_effect=fake_get):
            result = client.match_analysis("m_B8x2K9")

        local = result["metricas_calculadas_desde_remates"]["local"]
        away = result["metricas_calculadas_desde_remates"]["visitante"]
        self.assertEqual(local["remates"], 2)
        self.assertEqual(local["remates_a_puerta"], 2)
        self.assertEqual(local["xg"], 0.5)
        self.assertEqual(away["remates"], 1)
        self.assertEqual(result["remates"][0]["x"], 100.0)
        self.assertIsNone(result["remates"][2]["x"])
        self.assertEqual(result["estadisticas_equipo"][0]["key"], "total_shots")
        self.assertTrue(result["disponibilidad"]["mapas_calor"])
        self.assertTrue(result["disponibilidad"]["red_pases"])
        self.assertTrue(result["disponibilidad"]["momentum"])
        self.assertEqual(result["estadisticas_jugadores"][0]["player"]["name"], "Player")
        self.assertEqual(result["analitica_avanzada_jugadores"][0]["player"]["name"], "Player")

    def test_periodos_sin_all_no_se_presentan_como_estadistica_completa(self):
        client = PitchAPIClient(api_key="test-key")
        def fake_get(path, params=None, optional=False, cache_seconds=None):
            if path == "/matches/m_B8x2K9":
                return {"home_team": {"id": "h"}, "away_team": {"id": "a"}}
            if path == "/matches/m_B8x2K9/stats":
                return {"periods": [{"period": "FirstHalf", "groups": [{"items": [
                    {"key": "total_shots", "title": "Shots", "home": 3, "away": 1}
                ]}]}]}
            if path == "/matches/m_B8x2K9/heatmaps":
                return {"teams": [], "players": []}
            return {}

        with patch.object(client, "_get", side_effect=fake_get):
            result = client.match_analysis("m_B8x2K9")
        self.assertEqual(result["estadisticas_equipo"], [])
        self.assertFalse(result["disponibilidad"]["mapas_calor"])
        self.assertIn("estadisticas_equipo", result["bloques_sin_cobertura"])

    def test_bloque_opcional_fallido_no_rompe_el_informe(self):
        client = PitchAPIClient(api_key="test-key")
        calls = []
        def fake_get(path, params=None, optional=False, cache_seconds=None):
            calls.append(path)
            if path == "/matches/m_B8x2K9":
                return {"home_team": {"id": "h"}, "away_team": {"id": "a"}}
            if path == "/matches/m_B8x2K9/shots":
                raise PitchAPIError("No se pudo consultar remates", 502, "PITCHAPI_UPSTREAM_ERROR")
            return {}

        with patch.object(client, "_get", side_effect=fake_get):
            result = client.match_analysis("m_B8x2K9")
        self.assertEqual(result["partido"]["home_team"]["id"], "h")
        self.assertEqual(len(result["advertencias"]), 1)
        self.assertFalse(result["disponibilidad"]["remates_xg"])
        self.assertEqual(len(calls), 12)

    def test_429_abre_circuit_breaker_y_evitar_multiplicar_consultas(self):
        client = PitchAPIClient(api_key="test-key")
        calls = []
        def fake_get(path, params=None, optional=False, cache_seconds=None):
            calls.append(path)
            if path == "/matches/m_B8x2K9":
                return {"home_team": {"id": "h"}, "away_team": {"id": "a"}}
            raise PitchAPIError("Límite", 503, "PITCHAPI_RATE_LIMIT")

        with patch.object(client, "_get", side_effect=fake_get):
            result = client.match_analysis("m_B8x2K9")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(result["advertencias"]), 1)

    def test_404_opcional_se_cachea(self):
        client = PitchAPIClient(api_key="test-key")
        response = SimpleNamespace(status_code=404, headers={}, reason="Not Found")
        with patch.object(client.session, "get", return_value=response) as mocked:
            self.assertIsNone(client._get("/matches/m_B8x2K9/advanced", optional=True))
            self.assertIsNone(client._get("/matches/m_B8x2K9/advanced", optional=True))
        mocked.assert_called_once()

    def test_429_se_convierte_en_pausa_local(self):
        client = PitchAPIClient(api_key="test-key")
        response = SimpleNamespace(status_code=429, headers={"Retry-After": "30"}, reason="Too Many Requests")
        with patch.object(integraciones_pitchapi, "_RATE_LIMIT_UNTIL", 0.0):
            with patch.object(client.session, "get", return_value=response) as mocked:
                with self.assertRaises(PitchAPIError) as first:
                    client._get("/leagues", cache_seconds=0)
                self.assertEqual(first.exception.code, "PITCHAPI_RATE_LIMIT")
                with self.assertRaises(PitchAPIError) as second:
                    client._get("/leagues", cache_seconds=0)
                self.assertEqual(second.exception.code, "PITCHAPI_RATE_LIMIT")
                mocked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
