"""
Conector oficial configurable para Altenar Data Feed (GanaPlay).

No incluye URLs de staging, importer IDs de terceros ni credenciales de ejemplo.
El operador debe proporcionar el endpoint asignado por Altenar y autorizar la IP
del servidor. El feed se consulta solo para lectura: no coloca ni acepta apuestas.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests


class FeedConfigurationError(RuntimeError):
    pass


class FeedAccessError(RuntimeError):
    pass


class FeedResponseError(RuntimeError):
    pass


SPORT_ALIASES = {
    "futbol": {"soccer", "futbol"},
    "nba": {"basketball", "baloncesto", "nba"},
    "nfl": {"americanfootball", "americanfootballnfl", "nfl", "gridiron"},
    "mlb": {"baseball", "beisbol", "mlb"},
}


@dataclass(frozen=True)
class FeedSettings:
    base_url: str
    importer_id: str
    api_token: str | None
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "FeedSettings":
        base_url = os.getenv("ALTENAR_DATAFEED_BASE_URL", "").strip().rstrip("/")
        importer_id = os.getenv("ALTENAR_IMPORTER_ID", "").strip()
        token = os.getenv("ALTENAR_DATAFEED_TOKEN", "").strip() or None
        timeout = float(os.getenv("ALTENAR_TIMEOUT_SECONDS", "20"))

        if not base_url or not importer_id:
            raise FeedConfigurationError(
                "Falta ALTENAR_DATAFEED_BASE_URL o ALTENAR_IMPORTER_ID. "
                "Solicita a GanaPlay/Altenar el feed autorizado para su operador."
            )

        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise FeedConfigurationError(
                "ALTENAR_DATAFEED_BASE_URL debe ser una URL HTTPS asignada por Altenar, "
                "sin query string ni fragmento."
            )

        if timeout <= 0 or timeout > 120:
            raise FeedConfigurationError("ALTENAR_TIMEOUT_SECONDS debe estar entre 0 y 120.")

        return cls(base_url=base_url, importer_id=importer_id, api_token=token, timeout_seconds=timeout)


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def _first(obj: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    lowered = {str(key).casefold(): value for key, value in obj.items()}
    for key in keys:
        value = lowered.get(key.casefold())
        if value is not None and value != "":
            return value
    return default


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "y", "live"}
    return False


def _xml_to_value(element: ET.Element) -> Any:
    children = list(element)
    if not children:
        return element.text or ""
    result: dict[str, Any] = {}
    for child in children:
        value = _xml_to_value(child)
        if child.tag in result:
            current = result[child.tag]
            if not isinstance(current, list):
                result[child.tag] = [current]
            result[child.tag].append(value)
        else:
            result[child.tag] = value
    if element.attrib:
        result["@attributes"] = dict(element.attrib)
    return result


def _extract_list(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    lowered = {str(key).casefold(): value for key, value in payload.items()}
    for key in keys:
        value = lowered.get(key.casefold())
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _extract_list(value, keys)
            if nested:
                return nested

    # Algunas respuestas pueden encapsular la lista dentro de result/data/response.
    for key in ("result", "data", "response", "items", "payload"):
        value = lowered.get(key)
        if isinstance(value, (dict, list)):
            nested = _extract_list(value, keys)
            if nested:
                return nested

    return []


def _looks_like_event(item: dict[str, Any]) -> bool:
    keys = {str(key).casefold() for key in item}
    return bool(
        keys.intersection({"eventid", "event_id", "eventname", "event_name", "eventdesc", "eventdate"})
    )


def _event_list(payload: Any) -> list[dict[str, Any]]:
    items = _extract_list(
        payload,
        ("events", "event", "eventlist", "eventdata", "items", "result", "data", "response"),
    )
    if items:
        return items
    if isinstance(payload, dict) and _looks_like_event(payload):
        return [payload]
    return []


def _split_event_name(name: str) -> tuple[str, str]:
    for separator in (" vs. ", " vs ", " v ", " - "):
        if separator in name:
            parts = name.split(separator, 1)
            return parts[0].strip(), parts[1].strip()
    return name.strip(), ""


def normalize_event(item: dict[str, Any], is_live: bool = False) -> dict[str, Any]:
    event_id = _first(item, ("EventId", "eventId", "event_id", "Id", "id"))
    event_name = _first(item, ("EventName", "eventName", "event_name", "EventDesc", "Name", "name"), "")
    event_name = str(event_name).strip()
    home = _first(item, ("HomeTeam", "homeTeam", "Home", "home", "Competitor1", "Team1"))
    away = _first(item, ("AwayTeam", "awayTeam", "Away", "away", "Competitor2", "Team2"))
    if not home or not away:
        split_home, split_away = _split_event_name(event_name)
        home = home or split_home
        away = away or split_away

    event_date = _first(
        item,
        ("EventDate", "eventDate", "event_date", "StartDate", "startTime", "Date", "date"),
    )
    sport_name = _first(item, ("SportName", "sportName", "Sport", "sport"), "")
    category = _first(item, ("CatName", "CategoryName", "categoryName", "Category", "category"), "")
    league = _first(item, ("ChampName", "ChampDesc", "ChampionshipName", "LeagueName", "league"), "")
    status = _first(item, ("StatusName", "EventStatus", "status", "Status"), "")
    return {
        "evento_id": str(event_id) if event_id is not None else None,
        "nombre_evento": event_name or f"{home} vs {away}".strip(),
        "local": str(home or "").strip(),
        "visitante": str(away or "").strip(),
        "fecha_hora": str(event_date or ""),
        "deporte_fuente": str(sport_name or ""),
        "categoria": str(category or ""),
        "liga": str(league or ""),
        "estado_evento": "En vivo" if is_live else (str(status) or "Programado"),
        "en_vivo": bool(is_live),
        "fuente_eventos": "GanaPlay / Altenar",
        "raw": item,
    }


def _market_items(payload: Any) -> list[dict[str, Any]]:
    items = _extract_list(
        payload,
        ("markets", "market", "marketlist", "eventmarkets", "marketdata", "items", "result", "data", "response"),
    )
    if items:
        return items
    if isinstance(payload, dict):
        if _first(payload, ("MarketName", "marketName", "BetTypeName", "Name")) is not None:
            return [payload]
    return []


def _selection_items(market: dict[str, Any]) -> list[dict[str, Any]]:
    return _extract_list(
        market,
        ("selections", "selection", "outcomes", "outcome", "odds", "items", "betoffers", "marketselections", "runners"),
    )


def _normalize_selection(item: dict[str, Any]) -> dict[str, Any]:
    name = _first(
        item,
        ("SelectionName", "selectionName", "OutcomeName", "outcomeName", "Name", "name", "Label", "label"),
        "",
    )
    price = _first(
        item,
        ("Price", "price", "Odds", "odds", "Odd", "odd", "DecimalOdds", "decimalOdds", "Coefficient"),
    )
    try:
        numeric_price = float(str(price).replace(",", ".")) if price is not None else None
    except (ValueError, TypeError):
        numeric_price = None

    return {
        "nombre": str(name),
        "cuota": numeric_price if numeric_price and numeric_price > 1 else None,
        "seleccion_id": _first(item, ("SelectionId", "selectionId", "OddId", "Id", "id")),
        "estado": _first(item, ("Status", "status", "SelectionStatus")),
        "raw": item,
    }


def normalize_market(item: dict[str, Any]) -> dict[str, Any]:
    selections = [_normalize_selection(selection) for selection in _selection_items(item)]
    return {
        "mercado_id": _first(item, ("MarketId", "marketId", "FeedMarketId", "Id", "id")),
        "nombre": str(_first(item, ("MarketName", "marketName", "BetTypeName", "Name", "name"), "Mercado sin nombre")),
        "tipo_id": _first(item, ("MarketType", "MarketTypeId", "TypeId", "marketType")),
        "linea": _first(item, ("Spec", "spec", "Line", "line", "Handicap", "handicap")),
        "estado": _first(item, ("MarketStatus", "Status", "status")),
        "en_vivo": _to_bool(_first(item, ("IsLive", "isLive", "Live"), False)),
        "selecciones": selections,
        "raw": item,
    }


class AltenarFeedClient:
    """Cliente de solo lectura para el Data Feed que Altenar habilite al operador."""

    def __init__(self, settings: FeedSettings | None = None):
        self.settings = settings or FeedSettings.from_env()
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "EdgeBet-Research/0.1",
        })
        if self.settings.api_token:
            self.session.headers["Authorization"] = f"Bearer {self.settings.api_token}"

    def _get(self, method: str, params: dict[str, Any] | None = None) -> Any:
        query = {"importerId": self.settings.importer_id}
        if params:
            query.update({key: value for key, value in params.items() if value is not None})
        url = f"{self.settings.base_url}/{method}"
        try:
            response = self.session.get(url, params=query, timeout=self.settings.timeout_seconds)
        except requests.RequestException as exc:
            raise FeedAccessError(f"No fue posible conectar con el feed Altenar: {exc}") from exc

        if response.status_code in (401, 403, 404):
            raise FeedAccessError(
                f"Altenar respondió HTTP {response.status_code}. Verifica el endpoint asignado, "
                "el importer ID y la whitelist de IP del servidor."
            )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise FeedAccessError(f"Altenar respondió HTTP {response.status_code}.") from exc

        content_type = response.headers.get("Content-Type", "").casefold()
        try:
            if "xml" in content_type or response.text.lstrip().startswith("<"):
                root = ET.fromstring(response.text)
                return _xml_to_value(root)
            return response.json()
        except (ValueError, ET.ParseError) as exc:
            raise FeedResponseError(f"Respuesta no reconocida de Altenar en {method}.") from exc

    def get_sports(self) -> Any:
        # El manual del Data Feed define GetSports como catálogo general de deportes.
        url = f"{self.settings.base_url}/GetSports"
        try:
            response = self.session.get(url, timeout=self.settings.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise FeedAccessError(f"No fue posible consultar GetSports: {exc}") from exc

        try:
            if "xml" in response.headers.get("Content-Type", "").casefold() or response.text.lstrip().startswith("<"):
                return _xml_to_value(ET.fromstring(response.text))
            return response.json()
        except (ValueError, ET.ParseError) as exc:
            raise FeedResponseError("La respuesta GetSports no es JSON/XML válido.") from exc

    def resolve_sport_id(self, sport: str, sports_payload: Any | None = None) -> str:
        sport = sport.casefold().strip()
        override = os.getenv(f"ALTENAR_SPORT_ID_{sport.upper()}", "").strip()
        if override:
            return override

        payload = sports_payload if sports_payload is not None else self.get_sports()
        items = _extract_list(payload, ("sports", "sportlist", "items", "result", "data", "response"))
        if not items and isinstance(payload, dict):
            items = [payload] if _first(payload, ("SportId", "sportId", "Id", "id")) is not None else []

        aliases = SPORT_ALIASES.get(sport)
        if not aliases:
            raise FeedConfigurationError(f"Deporte no admitido por la app: {sport}")

        for item in items:
            name = _first(item, ("SportName", "Name", "Sport", "name", "sportName"), "")
            if _norm(name) in {_norm(alias) for alias in aliases}:
                identifier = _first(item, ("SportId", "sportId", "Id", "id"))
                if identifier is not None:
                    return str(identifier)

        names = [
            str(_first(item, ("SportName", "Name", "Sport", "name"), ""))
            for item in items
        ]
        raise FeedConfigurationError(
            f"No se identificó el ID de Altenar para '{sport}'. "
            f"Catálogo recibido: {names[:40]}. Configura ALTENAR_SPORT_ID_{sport.upper()} "
            "cuando GanaPlay/Altenar confirme el identificador correcto."
        )

    def get_events(self, sport: str) -> dict[str, Any]:
        sports_payload = self.get_sports()
        sport_id = self.resolve_sport_id(sport, sports_payload)
        prematch_payload = self._get("GetEvents", {"sportid": sport_id})
        live_payload = self._get("GetLiveEvents", {"sportid": sport_id})

        prematch = _event_list(prematch_payload)
        live = _event_list(live_payload)
        combined: dict[str, dict[str, Any]] = {}

        for item in prematch:
            event = normalize_event(item, is_live=False)
            key = event["evento_id"] or f'{event["nombre_evento"]}|{event["fecha_hora"]}'
            combined[key] = event

        for item in live:
            event = normalize_event(item, is_live=True)
            key = event["evento_id"] or f'{event["nombre_evento"]}|{event["fecha_hora"]}'
            combined[key] = event

        events = list(combined.values())
        events.sort(key=lambda event: (event.get("fecha_hora") or "", event.get("nombre_evento") or ""))
        return {
            "fuente": "GanaPlay / Altenar",
            "deporte": sport,
            "sport_id": sport_id,
            "generado_en": datetime.now(timezone.utc).isoformat(),
            "total_eventos": len(events),
            "eventos_programados": len(prematch),
            "eventos_en_vivo": len(live),
            "eventos": events,
            "raw_sports": sports_payload,
        }

    def get_markets(self, event_id: str) -> dict[str, Any]:
        payload = self._get("GetMarkets", {"eventId": event_id})
        markets = _market_items(payload)
        normalized = [normalize_market(market) for market in markets]
        return {
            "fuente": "GanaPlay / Altenar",
            "evento_id": str(event_id),
            "total_mercados": len(normalized),
            "mercados": normalized,
            "estructura_reconocida": bool(normalized),
            "raw": payload,
        }


def feed_configuration_status() -> dict[str, Any]:
    try:
        settings = FeedSettings.from_env()
        return {
            "configurado": True,
            "fuente": "GanaPlay / Altenar",
            "endpoint_configurado": True,
            "importer_id_configurado": bool(settings.importer_id),
            "token_configurado": bool(settings.api_token),
            "nota": "El acceso efectivo depende de la habilitación y whitelist de IP de Altenar.",
        }
    except (FeedConfigurationError, ValueError) as exc:
        return {
            "configurado": False,
            "fuente": "GanaPlay / Altenar",
            "nota": str(exc),
        }
