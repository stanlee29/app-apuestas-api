import unittest
from unittest.mock import Mock

from odds_collector import OddsCollectionError, _monthly_budget, collect_daily_odds


class OddsCollectorTests(unittest.TestCase):
    def test_reserves_monthly_objects(self):
        budget, summary = _monthly_budget({
            "tier": "amateur",
            "rate_limits": {
                "per-month": {
                    "maxEntitiesPerInterval": 2500,
                    "currentIntervalEntities": 1000,
                }
            },
        })
        self.assertEqual(budget, 20)
        self.assertEqual(summary["reserved_objects"], 500)

    def test_stops_when_only_reserved_objects_remain(self):
        budget, _ = _monthly_budget({
            "rate_limits": {
                "per-month": {
                    "maxEntitiesPerInterval": 2500,
                    "currentIntervalEntities": 2100,
                }
            }
        })
        self.assertEqual(budget, 0)

    def test_supports_unlimited_monthly_plan_with_hard_run_cap(self):
        budget, summary = _monthly_budget({
            "rate_limits": {"per-month": {"maxEntitiesPerInterval": "unlimited"}}
        })
        self.assertEqual(budget, 20)
        self.assertEqual(summary["objects_max"], "unlimited")

    def test_fails_closed_when_usage_is_missing(self):
        with self.assertRaises(OddsCollectionError):
            _monthly_budget({"rate_limits": {}})

    def test_collection_caps_requests_and_stores_unique_events(self):
        client = Mock()
        client.account_usage.return_value = {
            "is_active": True,
            "tier": "amateur",
            "rate_limits": {
                "per-month": {
                    "maxEntitiesPerInterval": 2500,
                    "currentIntervalEntities": 50,
                }
            },
        }
        client.get_events.side_effect = lambda sport, days, limit: {
            "generado_en": "2026-11-23T13:15:00Z",
            "eventos": [{"evento_id": f"{sport}-{i}", "mercados": []} for i in range(limit)],
        }
        storage = Mock()
        storage.configured = True
        storage.save_snapshot.return_value = {"guardado": True}

        result = collect_daily_odds(client, storage)

        self.assertEqual(result["estado"], "completado")
        self.assertEqual(result["eventos_recibidos"], 20)
        self.assertEqual(result["snapshots_guardados"], 20)
        self.assertEqual(client.get_events.call_count, 4)
        self.assertTrue(all(call.kwargs["limit"] == 5 for call in client.get_events.call_args_list))
        self.assertEqual(storage.save_snapshot.call_count, 20)

    def test_does_not_call_provider_when_supabase_is_not_configured(self):
        client = Mock()
        storage = Mock()
        storage.configured = False
        with self.assertRaises(OddsCollectionError):
            collect_daily_odds(client, storage)
        client.account_usage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
