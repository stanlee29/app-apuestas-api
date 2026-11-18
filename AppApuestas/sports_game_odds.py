"""Cliente de lectura para SportsGameOdds API v2.

Los precios conservan la casa de apuestas y la hora de actualización.
Las cuotas se convierten de formato americano a decimal sin inventar valores.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


BASE_URL = "https://api.sportsgameodds.com/v2"
SPORT_LEAGUES = {
    "futbol": ("UEFA_CHAMPIONS_LEAGUE", "MLS"),
    "nba": ("NBA",),
    "nfl": ("NFL",),
    "mlb": ("MLB",),
}
LEAGUE_NAMES = {
    "UEFA_CHAMPIONS_LEAGUE": "Champions League",
    "MLS": "MLS",
    "NBA": "NBA",
    "NFL": "NFL",
    "MLB": "MLB",
}


class ProviderError(RuntimeError):
    """Error base del proveedor deportivo."""


class ProviderConfigurationError(ProviderError):
    """Falta la configuración necesaria para consultar datos."""


class ProviderAccessError(ProviderError):
    """El proveedor rechazó la solicitud o no está disponible."""


class ProviderResponseError(ProviderError):
    """La respuesta del proveedor no tiene el formato esperado."""


@dataclass(frozen=True)
class ProviderSettings:
    api_key: str
    base_url: str = BASE_URL
    timeout_seconds: float = 20.0
    leagues: dict[str, tuple[str, ...]] | None = None

    @classmethod
    def from_env(cls) -> "ProviderSettings":
        api_key = os.getenv("SPORTSGAMEODDS_API_KEY", "").strip()
        if not api_key:
            raise ProviderConfigurationError(
                "Falta SPORTSGAMEODDS_API_KEY. Registra la cuenta gratuita "
                "de SportsGameOdds y agrega la clave como variable privada del servicio."
            )

        base_url = os.getenv("SPORTSGAMEODDS_BASE_URL", BASE_URL).strip().rstrip("/")
        if not base_url.startswith("https://"):
            raise ProviderConfigurationError("SPORTSGAMEODDS_BASE_URL debe usar HTTPS.")

        timeout = float(os.getenv("SPORTSGAMEODDS_TIMEOUT_SECONDS", "20"))
        if not 1 <= timeout <= 120:
            raise ProviderConfigurationError("El timeout debe estar entre 1 y 120 segundos.")

        leagues = {}
        for sport, defaults in SPORT_LEAGUES.items():
            raw = os.getenv(f"SPORTSGAMEODDS_LEAGUES_{sport.upper()}", "").strip()
            leagues[sport] = tuple(
                item.strip().upper() for item in raw.split(",") if item.strip()
            ) if raw else defaults

        return cls(api_key=api_key, base_url=base_url, timeout_seconds=timeout, leagues=leagues)


def american_to_decimal(value: Any) -> float | None:
    """Convierte una cuota americana (+130/-110) a decimal."""
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        number = float(text.replace("+", ""))
    except (TypeError, ValueError):
        return None

    if number == 0:
        return None
    if number > 0:
        return round(1.0 + (number / 100.0), 4)
    return round(1.0 + (100.0 / abs(number)), 4)


def _name(team: Any) -> str:
    if not isinstance(team, dict):
        return str(team or "")
    names = team.get("names") or {}
    if isinstance(names, dict):
        return str(names.get("long") or names.get("medium") or names.get("short") or "")
    return str(team.get("name") or "")


def _selection_label(side: Any) -> str:
    labels = {
        "home": "Local",
        "away": "Visitante",
        "draw": "Empate",
        "over": "Más de",
        "under": "Menos de",
        "yes": "Sí",
        "no": "No",
        "home+draw": "Local o empate",
        "away+draw": "Visitante o empate",
        "home+away": "Local o visitante",
    }
    value = str(side or "").strip()
    return labels.get(value.casefold(), value.replace("_", " ").title())


def _bookmaker_prices(odd: dict[str, Any]) -> list[dict[str, Any]]:
    by_bookmaker = odd.get("byBookmaker")
    prices = []
    if isinstance(by_bookmaker, dict):
        for bookmaker_id, item in by_bookmaker.items():
            if not isinstance(item, dict) or item.get("available") is False:
                continue
            american = item.get("odds")
            decimal = american_to_decimal(american)
            if decimal is None:
                continue
            prices.append({
                "casa_id": str(bookmaker_id),
                "casa": str(bookmaker_id).replace("_", " ").title(),
                "cuota_americana": str(american),
                "cuota_decimal": decimal,
                "linea": item.get("overUnder"),
                "actualizado_en": item.get("lastUpdatedAt"),
                "enlace": item.get("deeplink"),
            })
    prices.sort(key=lambda item: item["cuota_decimal"], reverse=True)
    return prices


def normalize_markets(raw_event: dict[str, Any]) -> list[dict[str, Any]]:
    """Agrupa las selecciones que pertenecen al mismo mercado real."""
    raw_odds = raw_event.get("odds") or {}
    if not isinstance(raw_odds, dict):
        return []

    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    for odd in raw_odds.values():
        if not isinstance(odd, dict):
            continue

        market_name = str(odd.get("marketName") or odd.get("betTypeID") or "Mercado")
        period = str(odd.get("periodID") or "game")
        stat = str(odd.get("statID") or "")
        entity = str(odd.get("playerID") or odd.get("statEntityID") or "game")
        if entity.casefold() in {"home", "away", "draw", "game", ""}:
            entity = "game"
        line = odd.get("bookOverUnder")
        if line is None:
            line = odd.get("fairOverUnder")
        key = (market_name, period, stat, entity, str(line or ""))

        market = grouped.setdefault(key, {
            "mercado_id": "|".join(key),
            "nombre": market_name,
            "periodo": period,
            "stat_id": stat,
            "entidad_id": entity,
            "linea": line,
            "selecciones": [],
        })

        prices = _bookmaker_prices(odd)
        market["selecciones"].append({
            "seleccion_id": odd.get("oddID"),
            "lado": odd.get("sideID"),
            "nombre": _selection_label(odd.get("sideID")),
            "jugador_id": odd.get("playerID"),
            "cuota_referencia_americana": odd.get("bookOdds"),
            "cuota_justa_americana": odd.get("fairOdds"),
            "linea": odd.get("bookOverUnder") or odd.get("fairOverUnder"),
            "disponible": bool(odd.get("bookOddsAvailable") or prices),
            "casas": prices,
            "mejor_cuota": prices[0] if prices else None,
            "suspendida": bool(odd.get("ended") or odd.get("cancelled")),
        })

    markets = list(grouped.values())
    markets.sort(key=lambda item: (item["nombre"].casefold(), item["periodo"], item["entidad_id"]))
    for market in markets:
        market["selecciones"].sort(key=lambda item: item["nombre"].casefold())
        market["total_selecciones"] = len(market["selecciones"])
    return markets


def normalize_event(raw: dict[str, Any]) -> dict[str, Any]:
    teams = raw.get("teams") or {}
    status = raw.get("status") or {}
    league_id = str(raw.get("leagueID") or "")
    markets = normalize_markets(raw)
    return {
        "evento_id": str(raw.get("eventID") or ""),
        "deporte_fuente": str(raw.get("sportID") or ""),
        "liga_id": league_id,
        "liga": LEAGUE_NAMES.get(league_id, league_id.replace("_", " ").title()),
        "local": _name(teams.get("home")),
        "visitante": _name(teams.get("away")),
        "fecha_hora": status.get("startsAt"),
        "estado_evento": status.get("displayLong") or (
            "En vivo" if status.get("live") else "Programado"
        ),
        "en_vivo": bool(status.get("live")),
        "finalizado": bool(status.get("finalized") or status.get("completed")),
        "cancelado": bool(status.get("cancelled")),
        "cuotas_disponibles": bool(status.get("oddsAvailable") or markets),
        "mercados_disponibles": len(markets),
        "fuente_eventos": "SportsGameOdds",
        "fuente_cuotas": "SportsGameOdds",
        "mercados": markets,
        "enlaces_casas": (raw.get("links") or {}).get("bookmakers", {}),
    }


class SportsGameOddsClient:
    def __init__(self, settings: ProviderSettings | None = None):
        self.settings = settings or ProviderSettings.from_env()
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "X-Api-Key": self.settings.api_key,
            "User-Agent": "AppApuestas/1.0",
        })
        self.last_usage: dict[str, str | None] = {
            "remaining": None, "used": None, "last": None,
        }

    def _get_events(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            response = self.session.get(
                f"{self.settings.base_url}/events",
                params=params,
                timeout=self.settings.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise ProviderAccessError(f"No fue posible conectar con SportsGameOdds: {exc}") from exc

        self.last_usage = {
            "remaining": response.headers.get("x-requests-remaining"),
            "used": response.headers.get("x-requests-used"),
            "last": response.headers.get("x-requests-last"),
        }
        if response.status_code == 429:
            raise ProviderAccessError(
                "SportsGameOdds respondió HTTP 429: se alcanzó el límite de consultas o de objetos del plan."
            )
        if response.status_code in (401, 403):
            raise ProviderAccessError(
                f"SportsGameOdds rechazó la clave (HTTP {response.status_code}). Verifica la variable privada."
            )
        try:
            response.raise_for_status()
            payload = response.json()
        except (requests.HTTPError, ValueError) as exc:
            raise ProviderResponseError(
                f"Respuesta no válida de SportsGameOdds (HTTP {response.status_code})."
            ) from exc

        if not isinstance(payload, dict) or payload.get("success") is False:
            raise ProviderResponseError("SportsGameOdds devolvió una respuesta sin éxito.")
        data = payload.get("data")
        if not isinstance(data, list):
            raise ProviderResponseError("La respuesta de SportsGameOdds no contiene una lista 'data'.")
        return [item for item in data if isinstance(item, dict)]

    def get_events(
        self,
        sport: str,
        days: int = 2,
        live: bool | None = None,
    ) -> dict[str, Any]:
        sport = sport.casefold().strip()
        if sport not in SPORT_LEAGUES:
            raise ProviderConfigurationError(f"Deporte no admitido: {sport}")
        league_ids = (self.settings.leagues or SPORT_LEAGUES)[sport]
        now = datetime.now(timezone.utc)
        params: dict[str, Any] = {
            "leagueID": ",".join(league_ids),
            "startsAfter": (now - timedelta(hours=6)).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "startsBefore": (now + timedelta(days=max(1, min(days, 7)))).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "oddsAvailable": "true",
            "finalized": "false",
            "cancelled": "false",
            "limit": 100,
        }
        if live is not None:
            params["live"] = str(live).lower()

        raw_events = self._get_events(params)
        events = [normalize_event(item) for item in raw_events]
        events = [item for item in events if item["evento_id"] and not item["cancelado"]]
        events.sort(key=lambda item: (item.get("fecha_hora") or "", item.get("liga") or ""))
        return {
            "fuente": "SportsGameOdds",
            "deporte": sport,
            "ligas_consultadas": list(league_ids),
            "generado_en": datetime.now(timezone.utc).isoformat(),
            "total_eventos": len(events),
            "eventos_en_vivo": sum(1 for item in events if item["en_vivo"]),
            "eventos_programados": sum(1 for item in events if not item["en_vivo"]),
            "eventos": events,
            "uso": dict(self.last_usage),
        }

    def get_event(self, event_id: str) -> dict[str, Any]:
        raw_events = self._get_events({"eventID": event_id, "limit": 1})
        if not raw_events:
            raise ProviderAccessError("El proveedor no devolvió el evento solicitado.")
        event = normalize_event(raw_events[0])
        if not event["evento_id"]:
            raise ProviderResponseError("El evento recibido no contiene eventID.")
        return {
            "fuente": "SportsGameOdds",
            "evento_id": event["evento_id"],
            "total_mercados": event["mercados_disponibles"],
            "mercados": event["mercados"],
            "uso": dict(self.last_usage),
        }


def provider_status() -> dict[str, Any]:
    leagues = {}
    for sport, defaults in SPORT_LEAGUES.items():
        raw = os.getenv(f"SPORTSGAMEODDS_LEAGUES_{sport.upper()}", "").strip()
        leagues[sport] = [item.strip().upper() for item in raw.split(",") if item.strip()] if raw else list(defaults)
    return {
        "proveedor": "SportsGameOdds",
        "configurado": bool(os.getenv("SPORTSGAMEODDS_API_KEY", "").strip()),
        "endpoint": os.getenv("SPORTSGAMEODDS_BASE_URL", BASE_URL).strip(),
        "ligas": leagues,
        "frecuencia_publicada_plan_gratuito": "10 minutos",
        "limite_publicado_plan_gratuito": "2.500 objetos al mes y 10 consultas por minuto",
        "nota": "La clave se configura en el backend. El plan Amateur requiere tarjeta al registrarse, pero el proveedor indica que no se cobra mientras no se actualice el plan.",
    }
