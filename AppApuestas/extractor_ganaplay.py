"""
Cartelera deportiva basada en el scoreboard público de ESPN.
No inventa cuotas: calcula EV únicamente cuando ESPN entrega moneyline verificable.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from motor_probabilidades import cargar_datos, predecir_partido, calcular_valor_ev

BASE_DIR = Path(__file__).resolve().parent
DIRECTORIO_SALIDA = BASE_DIR / "datos"
ARCHIVO_CUOTAS = DIRECTORIO_SALIDA / "cuotas_ganaplay.json"
TZ_SV = timezone(timedelta(hours=-6))

LEAGUES_MAP = {
    "nba": [("basketball", "nba")],
    "nfl": [("football", "nfl")],
    "mlb": [("baseball", "mlb")],
    "futbol": [
        ("soccer", "esp.1"),
        ("soccer", "eng.1"),
        ("soccer", "ita.1"),
        ("soccer", "ger.1"),
        ("soccer", "uefa.champions"),
        ("soccer", "mex.1"),
        ("soccer", "fifa.worldq.concacaf"),
    ],
}

LEAGUE_NAMES = {
    "nba": "NBA",
    "nfl": "NFL",
    "mlb": "MLB",
    "esp.1": "LaLiga",
    "eng.1": "Premier League",
    "ita.1": "Serie A",
    "ger.1": "Bundesliga",
    "uefa.champions": "Champions League",
    "mex.1": "Liga MX",
    "fifa.worldq.concacaf": "Eliminatorias CONCACAF",
}

HEADERS_ESPN = {
    "User-Agent": "EdgeBet research app/0.1 (public ESPN scoreboard client)",
    "Accept": "application/json",
}


def asegurar_directorio() -> None:
    DIRECTORIO_SALIDA.mkdir(parents=True, exist_ok=True)


def obtener_rango_fechas(dias: int) -> str:
    hoy = datetime.now(TZ_SV)
    fin = hoy + timedelta(days=dias)
    if dias == 0:
        return hoy.strftime("%Y%m%d")
    return f"{hoy.strftime('%Y%m%d')}-{fin.strftime('%Y%m%d')}"


def convertir_a_utc6(fecha_iso: str) -> tuple[datetime, str]:
    try:
        dt = datetime.fromisoformat(fecha_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_sv = dt.astimezone(TZ_SV)
        return dt_sv, dt_sv.strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"Fecha ESPN inválida: {fecha_iso!r}")


def americana_a_decimal(valor: Any) -> float | None:
    """Convierte moneyline americano a cuota decimal. Devuelve None si falta/no es válido."""
    if valor is None:
        return None
    try:
        numero = float(str(valor).replace("−", "-").strip())
    except (TypeError, ValueError):
        return None

    if numero == 0:
        return None
    if numero < 0:
        decimal = 1.0 + (100.0 / abs(numero))
    else:
        decimal = 1.0 + (numero / 100.0)

    return round(decimal, 3) if decimal > 1 else None


def extraer_cuotas(odds_list: Any) -> tuple[dict[str, float | None], str | None]:
    """
    Lee solo campos moneyline estructurados de ESPN.
    No interpreta el texto details ni deriva una cuota faltante.
    """
    resultado = {"local": None, "empate": None, "visitante": None}
    if not isinstance(odds_list, list):
        return resultado, None

    for item in odds_list:
        if not isinstance(item, dict):
            continue
        home = item.get("homeTeamOdds") or {}
        away = item.get("awayTeamOdds") or {}
        if not isinstance(home, dict):
            home = {}
        if not isinstance(away, dict):
            away = {}
        draw = item.get("drawOdds") or item.get("tieOdds") or {}
        if isinstance(draw, dict):
            draw_moneyline = draw.get("moneyLine", draw.get("moneyline"))
        else:
            draw_moneyline = draw

        resultado = {
            "local": americana_a_decimal(home.get("moneyLine", home.get("moneyline"))),
            "empate": americana_a_decimal(draw_moneyline),
            "visitante": americana_a_decimal(away.get("moneyLine", away.get("moneyline"))),
        }
        provider = item.get("provider") or {}
        nombre_provider = provider.get("name") if isinstance(provider, dict) else None

        if any(valor is not None for valor in resultado.values()):
            return resultado, nombre_provider or "ESPN"
    return resultado, None


def _porcentaje(probabilidad: float | None) -> str | None:
    if probabilidad is None:
        return None
    return f"{probabilidad * 100:.1f}%"


def obtener_cartelera_con_valor(deporte: str, dias: int = 2) -> dict[str, Any]:
    deporte = deporte.lower().strip()
    if deporte not in LEAGUES_MAP:
        return {
            "deporte": deporte,
            "mensaje": "Deporte no soportado.",
            "cartelera": [],
            "rango_fechas": "",
        }

    rango_fechas = obtener_rango_fechas(dias)
    ahora = datetime.now(TZ_SV)
    limite = ahora + timedelta(days=dias, hours=23, minutes=59)
    datos_historicos = cargar_datos(str(DIRECTORIO_SALIDA))
    partidos_reales: list[dict[str, Any]] = []
    errores_fuente: list[str] = []

    for categoria, league_id in LEAGUES_MAP[deporte]:
        url = f"https://site.api.espn.com/apis/site/v2/sports/{categoria}/{league_id}/scoreboard"
        try:
            response = requests.get(
                url,
                headers=HEADERS_ESPN,
                params={"dates": rango_fechas, "limit": 100},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            errores_fuente.append(f"{league_id}: {type(exc).__name__}")
            continue

        for event in data.get("events", []):
            status_info = event.get("status") or {}
            status_type = status_info.get("type") or {}
            status_name = status_type.get("name", "")
            status_state = status_type.get("state", "")

            if status_name == "STATUS_FINAL":
                continue

            competitions = event.get("competitions") or []
            if not competitions:
                continue

            competition = competitions[0]
            competitors = competition.get("competitors") or []
            if len(competitors) < 2:
                continue

            equipo_local = None
            equipo_visitante = None
            for competitor in competitors:
                equipo = (competitor.get("team") or {}).get("displayName")
                if competitor.get("homeAway") == "home":
                    equipo_local = equipo
                elif competitor.get("homeAway") == "away":
                    equipo_visitante = equipo

            if not equipo_local or not equipo_visitante:
                continue

            try:
                dt_sv, fecha_hora = convertir_a_utc6(event.get("date"))
            except ValueError:
                continue

            en_vivo = status_state == "in"
            if not en_vivo and not (ahora <= dt_sv <= limite):
                continue

            cuotas, proveedor = extraer_cuotas(
                competition.get("odds") or event.get("odds") or []
            )

            partidos_reales.append({
                "evento_id": str(event.get("id", "")),
                "fecha_dt": dt_sv,
                "fecha_hora": fecha_hora,
                "local": equipo_local,
                "visitante": equipo_visitante,
                "liga": LEAGUE_NAMES.get(league_id, league_id),
                "league_id": league_id,
                "estado_evento": "En vivo" if en_vivo else "Programado",
                "cuotas": cuotas,
                "fuente_cuotas": proveedor,
            })

    partidos_reales.sort(key=lambda partido: partido["fecha_dt"])
    cartelera_final: list[dict[str, Any]] = []

    for partido in partidos_reales:
        prediccion = predecir_partido(
            deporte,
            partido["local"],
            partido["visitante"],
            datos_historicos,
        )
        error_modelo = prediccion.get("error")
        modelo_disponible = error_modelo is None

        prob_local = prediccion.get("prob_victoria_local") if modelo_disponible else None
        prob_visitante = prediccion.get("prob_victoria_visitante") if modelo_disponible else None
        prob_empate = prediccion.get("prob_empate") if modelo_disponible else None

        analisis_ev: dict[str, Any] = {}
        cuotas_comparables = (
            partido["cuotas"]["local"] is not None
            and partido["cuotas"]["visitante"] is not None
            and (deporte != "futbol" or partido["cuotas"]["empate"] is not None)
        )
        if modelo_disponible and cuotas_comparables:
            analisis_ev["local"] = calcular_valor_ev(prob_local * 100, partido["cuotas"]["local"])
            analisis_ev["visitante"] = calcular_valor_ev(
                prob_visitante * 100,
                partido["cuotas"]["visitante"],
            )
            if deporte == "futbol":
                analisis_ev["empate"] = calcular_valor_ev(
                    prob_empate * 100,
                    partido["cuotas"]["empate"],
                )

        cartelera_final.append({
            "evento_id": partido["evento_id"],
            "deporte": deporte,
            "liga": partido["liga"],
            "league_id": partido["league_id"],
            "fecha_hora": partido["fecha_hora"],
            "zona_horaria": "America/El_Salvador",
            "estado_evento": partido["estado_evento"],
            "local": partido["local"],
            "visitante": partido["visitante"],
            "fuente_eventos": "ESPN",
            "fuente_cuotas": partido["fuente_cuotas"],
            "cuotas": partido["cuotas"],
            "probabilidades_modelo": {
                "local": _porcentaje(prob_local),
                "empate": _porcentaje(prob_empate),
                "visitante": _porcentaje(prob_visitante),
            },
            "modelo_disponible": modelo_disponible,
            "detalle_modelo": prediccion.get("modelo") if modelo_disponible else None,
            "error_modelo": error_modelo,
            "analisis_ev": analisis_ev,
            "tiene_valor_positivo": any(
                resultado.get("es_valor_positivo", False)
                for resultado in analisis_ev.values()
            ),
        })

    positivos = sum(1 for partido in cartelera_final if partido["tiene_valor_positivo"])
    con_modelo = sum(1 for partido in cartelera_final if partido["modelo_disponible"])
    con_cuotas = sum(1 for partido in cartelera_final if partido["fuente_cuotas"])

    if cartelera_final:
        mensaje = (
            f"{len(cartelera_final)} eventos encontrados; "
            f"{con_modelo} con predicción disponible y {con_cuotas} con cuotas publicadas."
        )
    elif errores_fuente:
        mensaje = "No se pudo consultar una o más ligas de ESPN. Revisa el estado de la fuente."
    else:
        mensaje = f"No se encontraron eventos para {deporte.upper()} en el rango solicitado."

    asegurar_directorio()
    with ARCHIVO_CUOTAS.open("w", encoding="utf-8") as archivo:
        json.dump(
            {
                "generado_en": datetime.now(TZ_SV).isoformat(),
                "deporte": deporte,
                "rango_fechas": rango_fechas,
                "cartelera": cartelera_final,
            },
            archivo,
            indent=2,
            ensure_ascii=False,
        )

    return {
        "deporte": deporte,
        "rango_fechas": rango_fechas,
        "zona_horaria": "America/El_Salvador",
        "mensaje": mensaje,
        "total_partidos": len(cartelera_final),
        "total_con_modelo": con_modelo,
        "total_con_cuotas": con_cuotas,
        "partidos_con_valor_positivo": positivos,
        "errores_fuente": errores_fuente,
        "cartelera": cartelera_final,
    }
