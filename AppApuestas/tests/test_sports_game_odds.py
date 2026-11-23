import os
import unittest
from unittest.mock import patch

from datetime import date, datetime, timezone

from sports_game_odds import (
    ProviderConfigurationError,
    ProviderSettings,
    SportsGameOddsClient,
    american_to_decimal,
    calendar_window,
    calendar_day_window,
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

    def test_ventana_dos_dias_incluye_hoy_manana_y_pasado_manana(self):
        now = datetime(2026, 11, 18, 22, 6, tzinfo=timezone.utc)
        window = calendar_window(2, now)
        self.assertEqual(window["fecha_inicio_local"], "2026-11-18")
        self.assertEqual(window["fecha_fin_local"], "2026-11-20")
        self.assertEqual(window["dias_incluidos"], 3)
        self.assertEqual(window["zona_horaria"], "America/El_Salvador")
        self.assertEqual(window["starts_before"], "2026-11-21T06:00:00Z")

    def test_fecha_exacta_separa_hoy_manana_y_pasado_manana(self):
        now = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
        expected = [
            ("2026-11-23", "2026-11-23T06:00:00Z", "2026-11-24T06:00:00Z"),
            ("2026-11-24", "2026-11-24T06:00:00Z", "2026-11-25T06:00:00Z"),
            ("2026-11-25", "2026-11-25T06:00:00Z", "2026-11-26T06:00:00Z"),
        ]
        for iso_date, start, end in expected:
            with self.subTest(fecha=iso_date):
                window = calendar_day_window(date.fromisoformat(iso_date), now)
                self.assertEqual(window["fecha_inicio_local"], iso_date)
                self.assertEqual(window["fecha_fin_local"], iso_date)
                self.assertEqual(window["dias_incluidos"], 1)
                self.assertEqual(window["starts_after"], start)
                self.assertEqual(window["starts_before"], end)

    def test_hoy_usa_el_dia_local_y_no_la_fecha_utc(self):
        # 02:00 del 18 de noviembre en El Salvador corresponde a 08:00 UTC.
        now = datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)
        window = calendar_window(0, now)
        self.assertEqual(window["fecha_inicio_local"], "2026-11-18")
        self.assertEqual(window["fecha_fin_local"], "2026-11-18")
        self.assertEqual(window["starts_after"], "2026-11-18T06:00:00Z")
        self.assertEqual(window["starts_before"], "2026-11-19T06:00:00Z")

    def test_account_usage_sanitizes_identifiers(self):
        settings = ProviderSettings(api_key="test-key")
        client = SportsGameOddsClient(settings)

        class Response:
            status_code = 200
            def raise_for_status(self):
                return None
            def json(self):
                return {
                    "success": True,
                    "data": {
                        "keyID": "must-not-escape",
                        "customerID": "must-not-escape",
                        "email": "must-not-escape",
                        "tier": "amateur",
                        "isActive": True,
                        "rateLimits": {
                            "per-month": {
                                "maxEntitiesPerInterval": 2500,
                                "currentIntervalEntities": 120,
                            }
                        },
                    },
                }

        with patch.object(client.session, "get", return_value=Response()) as request:
            usage = client.account_usage()
        self.assertEqual(usage["tier"], "amateur")
        self.assertTrue(usage["is_active"])
        self.assertEqual(usage["rate_limits"]["per-month"]["currentIntervalEntities"], 120)
        self.assertNotIn("keyID", usage)
        self.assertEqual(request.call_args.args[0], f"{settings.base_url}/account/usage")

    def test_get_events_accepts_safe_custom_limit(self):
        client = SportsGameOddsClient(ProviderSettings(api_key="test-key", leagues={"nba": ("NBA",)}))
        with patch.object(client, "_get_events", return_value=[]) as request:
            client.get_events("nba", days=0, limit=4)
        self.assertEqual(request.call_args.args[0]["limit"], 4)

    def test_get_events_follows_next_cursor_until_last_page(self):
        client = SportsGameOddsClient(ProviderSettings(api_key="test-key"))
        class Response:
            status_code = 200
            headers = {}
            def __init__(self, payload):
                self.payload = payload
            def raise_for_status(self):
                return None
            def json(self):
                return self.payload

        responses = [
            Response({"success": True, "data": [{"eventID": "event-1"}], "nextCursor": "cursor-next"}),
            Response({"success": True, "data": [{"eventID": "event-2"}], "nextCursor": None}),
        ]
        with patch.object(client.session, "get", side_effect=responses) as request:
            events = client._get_events({"leagueID": "NBA", "limit": 100})

        self.assertEqual([item["eventID"] for item in events], ["event-1", "event-2"])
        self.assertEqual(request.call_count, 2)
        self.assertNotIn("cursor", request.call_args_list[0].kwargs["params"])
        self.assertEqual(request.call_args_list[1].kwargs["params"]["cursor"], "cursor-next")
        self.assertEqual(client.last_page_count, 2)
        self.assertTrue(client.pagination_complete)

    def test_get_events_marks_page_cap_incomplete_instead_of_claiming_complete(self):
        client = SportsGameOddsClient(ProviderSettings(api_key="test-key"))
        class Response:
            status_code = 200
            headers = {}
            def raise_for_status(self):
                return None
            def json(self):
                return {"success": True, "data": [{"eventID": "event-1"}], "nextCursor": "cursor-next"}

        with patch.dict(os.environ, {"SPORTSGAMEODDS_MAX_EVENT_PAGES": "1"}, clear=False):
            with patch.object(client.session, "get", return_value=Response()):
                events = client._get_events({"leagueID": "NBA", "limit": 100})

        self.assertEqual(len(events), 1)
        self.assertFalse(client.pagination_complete)
        self.assertEqual(client.next_cursor, "cursor-next")
        self.assertEqual(client.last_page_count, 1)

    def test_get_events_rejects_limit_out_of_range(self):
        client = SportsGameOddsClient(ProviderSettings(api_key="test-key", leagues={"nba": ("NBA",)}))
        with self.assertRaises(ProviderConfigurationError):
            client.get_events("nba", limit=101)

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
        self.assertNotIn("oddsAvailable", params)
        self.assertEqual(result["ventana_consulta"]["dias_incluidos"], 3)


if __name__ == "__main__":
    unittest.main()
