"""Read-only observer for the public GanaPlay sportsbook frontend.

No login, no form submission, no bet-slip interaction and no bet placement.
Only GET/HEAD/OPTIONS requests are allowed; every other HTTP method is blocked.
The observer captures JSON responses loaded by the public page and normalizes
fixtures/markets only when the response contains recognizable fields.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

try:
    from playwright.async_api import async_playwright, Error as PlaywrightError
except ImportError:  # Playwright is only needed by the dedicated scraper workflow.
    async_playwright = None

    class PlaywrightError(RuntimeError):
        pass

EL_SALVADOR = ZoneInfo("America/El_Salvador")
DEFAULT_URLS = ("https://ganaplay.sv/Home", "https://ganaplay.sv/")
ALLOWED_HOST_SUFFIXES = (
    "ganaplay.sv", "biahosted.com", "virtualsoft.tech", "api-gaming-engine.com",
)
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_CAPTURED_RESPONSES = 500
MAX_CAPTURED_EVENTS = 5000

ID_KEYS = ("eventId", "eventID", "fixtureId", "matchId", "event_id", "fixture_id", "id")
TITLE_KEYS = ("eventName", "matchName", "fixtureName", "name", "title", "description", "eventDescription")
DATE_KEYS = (
    "startDate", "startDateUtc", "startDateTime", "startTime", "eventDate",
    "scheduledAt", "startAt", "kickoff", "matchDate", "dateUtc", "date",
)
HOME_KEYS = ("homeTeam", "homeParticipant", "homeCompetitor", "teamHome", "participantHome", "home")
AWAY_KEYS = ("awayTeam", "awayParticipant", "awayCompetitor", "teamAway", "participantAway", "away")
MARKET_KEYS = ("markets", "eventMarkets", "marketGroups", "marketList", "availableMarkets", "betMarkets")
SELECTION_KEYS = ("selections", "outcomes", "options", "runners", "selectionsList", "marketSelections")
PRICE_KEYS = ("decimalOdds", "decimalOdd", "currentOdds", "currentOdd", "price", "odds", "odd", "value")
SPORT_KEYS = ("sportName", "sport", "discipline", "sportTitle")
LEAGUE_KEYS = ("competitionName", "leagueName", "tournamentName", "categoryName", "competition", "league")


def _first(obj: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = obj.get(key)
        if value not in (None, ""):
            return value
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return _text(_first(value, ("name", "displayName", "fullName", "participantName", "teamName", "label", "value")))
    if isinstance(value, (list, tuple)):
        return None
    result = str(value).strip()
    return result or None


def _team_name(value: Any) -> str | None:
    if isinstance(value, dict):
        return _text(_first(value, ("name", "displayName", "fullName", "participantName", "teamName", "shortName", "label")))
    return _text(value)


def _localize_datetime(value: Any) -> tuple[str | None, str | None]:
    """Return (UTC ISO string, El Salvador calendar date)."""
    if value is None:
        return None, None
    dt: datetime | None = None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000.0
        try:
            dt = datetime.fromtimestamp(number, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None, None
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None, None
        if raw.isdigit():
            return _localize_datetime(int(raw))
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(raw[:19], pattern)
                    break
                except ValueError:
                    continue
    if dt is None:
        return None, None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=EL_SALVADOR)
    local_dt = dt.astimezone(EL_SALVADOR)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), local_dt.date().isoformat()


def _participant_pair(obj: dict[str, Any]) -> tuple[str | None, str | None]:
    home = _team_name(_first(obj, HOME_KEYS))
    away = _team_name(_first(obj, AWAY_KEYS))
    if home and away:
        return home, away

    for key in ("participants", "competitors", "teams", "eventParticipants", "contestants"):
        values = obj.get(key)
        if not isinstance(values, list):
            continue
        home_candidate = None
        away_candidate = None
        unnamed: list[str] = []
        for item in values:
            if isinstance(item, dict):
                name = _team_name(item)
                role = str(_first(item, ("position", "side", "qualifier", "participantType", "type", "homeAway")) or "").casefold()
                if any(token in role for token in ("home", "local", "1")):
                    home_candidate = home_candidate or name
                elif any(token in role for token in ("away", "visit", "2")):
                    away_candidate = away_candidate or name
                elif name:
                    unnamed.append(name)
            else:
                name = _team_name(item)
                if name:
                    unnamed.append(name)
        home = home or home_candidate
        away = away or away_candidate
        if not home and not away and len(unnamed) >= 2:
            return unnamed[0], unnamed[1]
        if home and not away and unnamed:
            away = next((name for name in unnamed if name != home), None)
        if away and not home and unnamed:
            home = next((name for name in unnamed if name != away), None)
        if home and away:
            return home, away
    return home, away


def _split_title(title: str | None) -> tuple[str | None, str | None]:
    if not title:
        return None, None
    for separator in (" vs. ", " vs ", " v ", " @ "):
        if separator in title.casefold():
            parts = re.split(re.escape(separator), title, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) == 2 and all(part.strip() for part in parts):
                return parts[0].strip(), parts[1].strip()
    return None, None


def _decimal_price(value: Any) -> float | None:
    if isinstance(value, dict):
        value = _first(value, ("decimal", "decimalOdds", "odd", "price", "value", "odds"))
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if not 1.0 < number <= 1000:
        return None
    return round(number, 4)


def _normalize_market(market: Any) -> dict[str, Any] | None:
    if not isinstance(market, dict):
        return None
    market_name = _text(_first(market, ("marketName", "name", "displayName", "title", "description", "label")))
    selections: list[dict[str, Any]] = []
    for key in SELECTION_KEYS:
        values = market.get(key)
        if isinstance(values, list):
            for item in values:
                if not isinstance(item, dict):
                    continue
                name = _text(_first(item, ("selectionName", "outcomeName", "name", "displayName", "label", "participantName")))
                price = _decimal_price(_first(item, PRICE_KEYS))
                if name or price is not None:
                    selections.append({
                        "nombre": name or "Selección sin nombre",
                        "cuota_decimal": price,
                        "suspendida": bool(_first(item, ("suspended", "isSuspended", "closed", "isClosed")) or False),
                    })
            break
    if not market_name and not selections:
        return None
    return {
        "nombre": market_name or "Mercado sin nombre",
        "selecciones": selections,
        "suspendido": bool(_first(market, ("suspended", "isSuspended", "closed", "isClosed")) or False),
    }


def _normalize_markets(event: dict[str, Any]) -> list[dict[str, Any]]:
    for key in MARKET_KEYS:
        values = event.get(key)
        if isinstance(values, list):
            result = [item for value in values if (item := _normalize_market(value)) is not None]
            if result:
                return result
        if isinstance(values, dict):
            nested = values.get("items") or values.get("markets") or values.get("data")
            if isinstance(nested, list):
                result = [item for value in nested if (item := _normalize_market(value)) is not None]
                if result:
                    return result
    return []


def normalize_event(obj: dict[str, Any], response_url: str) -> dict[str, Any] | None:
    title = _text(_first(obj, TITLE_KEYS))
    home, away = _participant_pair(obj)
    if not home or not away:
        title_home, title_away = _split_title(title)
        home = home or title_home
        away = away or title_away
    if not home or not away or home.casefold() == away.casefold():
        return None

    event_id = _text(_first(obj, ID_KEYS))
    raw_date = _first(obj, DATE_KEYS)
    kickoff_utc, local_date = _localize_datetime(raw_date)
    if not event_id and not kickoff_utc:
        return None

    status = _text(_first(obj, ("statusName", "status", "eventStatus", "state", "matchStatus")))
    is_live = bool(_first(obj, ("isLive", "live", "inPlay", "isInPlay")) or False)
    if status and any(token in status.casefold() for token in ("live", "in play", "en vivo")):
        is_live = True

    markets = _normalize_markets(obj)
    event_id = event_id or f"{local_date or 'unknown'}|{home.casefold()}|{away.casefold()}"
    return {
        "evento_id": event_id,
        "deporte": _text(_first(obj, SPORT_KEYS)),
        "liga": _text(_first(obj, LEAGUE_KEYS)),
        "fecha_hora_utc": kickoff_utc,
        "fecha_local": local_date,
        "local": home,
        "visitante": away,
        "estado": status,
        "en_vivo": is_live,
        "mercados": markets,
        "total_mercados": len(markets),
        "total_selecciones_con_cuota": sum(
            1 for market in markets for selection in market["selecciones"]
            if selection["cuota_decimal"] is not None
        ),
        "fuente": "GanaPlay",
        "solo_lectura": True,
        "origen_respuesta": response_url,
    }


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _pagination_signals(payload: Any) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for item in _walk_dicts(payload):
        for key in ("hasMore", "hasNext", "hasNextPage", "nextCursor", "nextPage", "totalCount", "totalItems"):
            if key in item:
                value = item.get(key)
                if value not in (None, False, "", 0):
                    signals.append({"campo": key, "valor": value if isinstance(value, (str, int, float, bool)) else type(value).__name__})
    return signals[:50]


def _response_keys(payload: Any, depth: int = 2) -> list[str]:
    keys: set[str] = set()

    def visit(value: Any, level: int):
        if level > depth:
            return
        if isinstance(value, dict):
            keys.update(str(key) for key in value.keys())
            for child in value.values():
                visit(child, level + 1)
        elif isinstance(value, list):
            for child in value[:3]:
                visit(child, level + 1)

    visit(payload, 0)
    return sorted(keys)[:100]


def _allowed_data_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    return any(host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_HOST_SUFFIXES)


def _safe_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _date_window(days: int) -> tuple[date, date]:
    today = datetime.now(EL_SALVADOR).date()
    return today, today + timedelta(days=days)


async def collect_public_feed(urls: list[str], days: int, wait_seconds: float) -> dict[str, Any]:
    if async_playwright is None:
        raise RuntimeError(
            "Falta Playwright. Instálalo con: pip install -r requirements-scraper.txt "
            "y luego ejecuta: python -m playwright install chromium"
        )
    observed_responses: list[dict[str, Any]] = []
    request_counts: Counter[str] = Counter()
    blocked_methods: Counter[str] = Counter()
    page_results: list[dict[str, Any]] = []
    pending: set[asyncio.Task] = set()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="es-SV",
            timezone_id="America/El_Salvador",
            viewport={"width": 1440, "height": 1100},
            service_workers="block",
        )

        async def read_only_guard(route):
            method = route.request.method.upper()
            request_counts[method] += 1
            if method not in ("GET", "HEAD", "OPTIONS"):
                blocked_methods[method] += 1
                await route.abort("blockedbyclient")
                return
            await route.continue_()

        await context.route("**/*", read_only_guard)
        page = await context.new_page()

        async def capture_response(response):
            try:
                if response.request.method.upper() != "GET":
                    return
                if not _allowed_data_host(response.url):
                    return
                content_type = (response.headers.get("content-type") or "").casefold()
                if "json" not in content_type:
                    return
                content_length = int(response.headers.get("content-length") or "0")
                if content_length > MAX_RESPONSE_BYTES or len(observed_responses) >= MAX_CAPTURED_RESPONSES:
                    return
                payload = await response.json()
                if not isinstance(payload, (dict, list)):
                    return
                observed_responses.append({
                    "url": _safe_url(response.url),
                    "status": response.status,
                    "host": urlparse(response.url).hostname,
                    "keys": _response_keys(payload),
                    "pagination": _pagination_signals(payload),
                    "payload": payload,
                })
            except Exception:
                return

        def on_response(response):
            task = asyncio.create_task(capture_response(response))
            pending.add(task)
            task.add_done_callback(pending.discard)

        page.on("response", on_response)
        for url in urls:
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                await page.wait_for_timeout(int(wait_seconds * 1000))
                page_results.append({
                    "url": url,
                    "http_status": response.status if response else None,
                    "title": await page.title(),
                    "page_url": page.url,
                })
            except PlaywrightError as exc:
                page_results.append({"url": url, "error": str(exc)[:500]})

        if pending:
            await asyncio.gather(*list(pending), return_exceptions=True)
        await browser.close()

    today, last_day = _date_window(days)
    by_key: dict[str, dict[str, Any]] = {}
    unclassified_dates = 0
    for response in observed_responses:
        for obj in _walk_dicts(response["payload"]):
            event = normalize_event(obj, response["url"])
            if event is None:
                continue
            if event["fecha_local"] is None:
                unclassified_dates += 1
                continue
            if not today.isoformat() <= event["fecha_local"] <= last_day.isoformat():
                continue
            key = event["evento_id"]
            existing = by_key.get(key)
            if existing is None or event["total_selecciones_con_cuota"] > existing["total_selecciones_con_cuota"]:
                by_key[key] = event

    events = sorted(
        by_key.values(),
        key=lambda item: (item["fecha_hora_utc"] or "", item["liga"] or "", item["local"] or ""),
    )
    pagination = [signal for response in observed_responses for signal in response["pagination"]]
    has_more = any(
        (signal["campo"] in ("hasMore", "hasNext", "hasNextPage") and signal["valor"] is True)
        or (signal["campo"] in ("nextCursor", "nextPage") and signal["valor"] not in (None, "", False))
        for signal in pagination
    )
    completeness = (
        "incompleta: el proveedor indicó más páginas disponibles"
        if has_more else
        "no verificada: la captura anónima no demuestra que se hayan cargado todos los deportes, eventos y páginas"
    )
    diagnostics = {
        "paginas_visitadas": page_results,
        "solicitudes_por_metodo": dict(request_counts),
        "metodos_bloqueados_por_seguridad": dict(blocked_methods),
        "respuestas_json_capturadas": len(observed_responses),
        "respuestas": [
            {
                "url": item["url"], "status": item["status"], "host": item["host"],
                "keys": item["keys"], "paginacion": item["pagination"],
            }
            for item in observed_responses
        ],
        "eventos_con_fecha_no_clasificable": unclassified_dates,
    }
    return {
        "fuente": "GanaPlay",
        "url_publica": "https://ganaplay.sv/",
        "modo": "navegador anónimo, solicitudes GET de solo lectura",
        "solo_lectura": True,
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "zona_horaria": "America/El_Salvador",
        "fecha_desde": today.isoformat(),
        "fecha_hasta": last_day.isoformat(),
        "total_eventos": len(events[:MAX_CAPTURED_EVENTS]),
        "total_eventos_con_cuotas": sum(1 for event in events if event["total_selecciones_con_cuota"]),
        "estado_completitud": completeness,
        "eventos": events[:MAX_CAPTURED_EVENTS],
        "diagnostico": diagnostics,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Captura de solo lectura de la cartelera pública de GanaPlay.")
    parser.add_argument("--days", type=int, default=2, help="Días adicionales desde hoy en El Salvador (0 a 7).")
    parser.add_argument("--wait", type=float, default=12, help="Segundos para que cargue el sportsbook.")
    parser.add_argument("--output", default="ganaplay_public_feed.json", help="Archivo JSON de salida.")
    parser.add_argument(
        "--urls", default=os.getenv("GANAPLAY_PUBLIC_URLS", ",".join(DEFAULT_URLS)),
        help="URLs públicas separadas por coma; solo admite el dominio oficial ganaplay.sv.",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    if not 0 <= args.days <= 7:
        raise SystemExit("--days debe estar entre 0 y 7.")
    if not 1 <= args.wait <= 60:
        raise SystemExit("--wait debe estar entre 1 y 60 segundos.")
    urls = [value.strip() for value in args.urls.split(",") if value.strip()]
    if not urls or any(
        urlparse(url).scheme != "https"
        or (urlparse(url).hostname or "").casefold() not in ("ganaplay.sv", "www.ganaplay.sv")
        for url in urls
    ):
        raise SystemExit("Solo se admiten URLs HTTPS públicas de ganaplay.sv.")

    try:
        result = await collect_public_feed(urls, args.days, args.wait)
    except PlaywrightError as exc:
        raise SystemExit(f"No se pudo iniciar/usar Chromium: {exc}") from exc

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "archivo": str(output),
        "total_eventos": result["total_eventos"],
        "total_eventos_con_cuotas": result["total_eventos_con_cuotas"],
        "json_capturados": result["diagnostico"]["respuestas_json_capturadas"],
        "metodos_bloqueados": result["diagnostico"]["metodos_bloqueados_por_seguridad"],
        "estado_completitud": result["estado_completitud"],
    }, ensure_ascii=False, indent=2))
    # Zero events is a valid probe result; diagnostics show the real response
    # schema. No fixture or price is fabricated to make the run look successful.
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
