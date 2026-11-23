"""Recolección diaria y limitada de cuotas para el archivo privado de AppApuestas."""
from __future__ import annotations

from typing import Any


SPORTS = ("futbol", "nba", "nfl", "mlb")
MAX_EVENTS_PER_SPORT = 5
MAX_EVENTS_PER_RUN = 20
MONTHLY_RESERVE = 500


class OddsCollectionError(RuntimeError):
    """Error seguro de la recolección programada de cuotas."""


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _monthly_budget(usage: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    limits = usage.get("rate_limits")
    monthly = limits.get("per-month") if isinstance(limits, dict) else None
    if not isinstance(monthly, dict):
        raise OddsCollectionError("SportsGameOdds no informó el límite mensual; recolección detenida por seguridad.")

    maximum_raw = monthly.get("maxEntitiesPerInterval", monthly.get("max-entities"))
    current_raw = monthly.get("currentIntervalEntities", monthly.get("current-entities"))

    if isinstance(maximum_raw, str) and maximum_raw.casefold() == "unlimited":
        return MAX_EVENTS_PER_RUN, {
            "tier": usage.get("tier"),
            "objects_used": None,
            "objects_max": "unlimited",
            "reserved_objects": 0,
            "budget": MAX_EVENTS_PER_RUN,
        }

    maximum = _number(maximum_raw)
    current = _number(current_raw)
    if maximum is None or current is None:
        raise OddsCollectionError("No se pudo interpretar el consumo mensual; recolección detenida por seguridad.")

    budget = max(0, min(MAX_EVENTS_PER_RUN, maximum - current - MONTHLY_RESERVE))
    return budget, {
        "tier": usage.get("tier"),
        "objects_used": current,
        "objects_max": maximum,
        "reserved_objects": MONTHLY_RESERVE,
        "budget": budget,
    }


def collect_daily_odds(client: Any, storage: Any) -> dict[str, Any]:
    """Consulta el consumo antes de descargar y guarda como máximo 20 eventos por día."""
    if not storage.configured:
        raise OddsCollectionError("Supabase no está configurado; no se inició la recolección.")

    usage = client.account_usage()
    if usage.get("is_active") is False:
        raise OddsCollectionError("La cuenta de SportsGameOdds está inactiva.")

    budget, usage_summary = _monthly_budget(usage)
    if budget <= 0:
        return {
            "estado": "omitido_por_limite_mensual",
            "motivo": "Se reservó el saldo restante para consultas manuales.",
            "uso": usage_summary,
            "eventos_recibidos": 0,
            "snapshots_guardados": 0,
            "deportes": {},
        }

    received = 0
    saved = 0
    sports_result: dict[str, Any] = {}
    seen: set[str] = set()

    for sport in SPORTS:
        if budget <= 0:
            break
        request_limit = min(MAX_EVENTS_PER_SPORT, budget)
        result = client.get_events(sport, days=2, limit=request_limit)
        events = result.get("eventos", []) if isinstance(result, dict) else []
        if not isinstance(events, list):
            raise OddsCollectionError(f"SportsGameOdds devolvió una lista inválida para {sport}.")

        # Cada objeto devuelto consume cuota aunque el identificador no sea utilizable.
        request_cost = max(1, len(events))
        received += len(events)
        budget = max(0, budget - request_cost)
        sport_saved = 0

        for event in events:
            if not isinstance(event, dict):
                continue
            event_id = str(event.get("evento_id") or "").strip()
            if not event_id or event_id in seen:
                continue
            seen.add(event_id)
            result_saved = storage.save_snapshot(
                provider="sportsgameodds",
                match_id=event_id,
                snapshot_type="daily_markets",
                payload=event,
                source_timestamp=result.get("generado_en"),
            )
            if isinstance(result_saved, dict) and result_saved.get("guardado") is True:
                saved += 1
                sport_saved += 1

        sports_result[sport] = {
            "eventos_recibidos": len(events),
            "snapshots_guardados": sport_saved,
            "fuente": "SportsGameOdds",
        }

    return {
        "estado": "completado",
        "uso_antes_de_consultar": usage_summary,
        "eventos_recibidos": received,
        "snapshots_guardados": saved,
        "deportes": sports_result,
        "limite_por_ejecucion": MAX_EVENTS_PER_RUN,
        "reserva_mensual": MONTHLY_RESERVE,
        "ventana": "Hoy y los próximos dos días calendario de El Salvador",
    }
