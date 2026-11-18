"""
API FastAPI de EdgeBet.
La cartelera y los mercados proceden del feed Altenar autorizado por GanaPlay.
No se consulta ESPN como sustituto ni se generan cuotas artificiales.
"""
import os
import re
import sys
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from motor_probabilidades import predecir_partido, cargar_datos, calcular_valor_ev
from altenar_feed import (
    AltenarFeedClient,
    FeedConfigurationError,
    FeedAccessError,
    FeedResponseError,
    feed_configuration_status,
)

BASE_DIR = Path(__file__).resolve().parent
DATOS_DIR = BASE_DIR / "datos"
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"
VERSION = "0.2.0"
EVENT_CACHE_SECONDS = max(10, int(os.getenv("ALTENAR_EVENTS_CACHE_SECONDS", "30")))
MARKET_CACHE_SECONDS = max(10, int(os.getenv("ALTENAR_MARKETS_CACHE_SECONDS", "30")))

_event_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_market_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class DeporteEnum(str, Enum):
    nba = "nba"
    nfl = "nfl"
    mlb = "mlb"
    futbol = "futbol"


app = FastAPI(
    title="EdgeBet API",
    description=(
        "API de investigación deportiva. Eventos y mercados se consultan desde el feed "
        "Altenar autorizado por GanaPlay. Solo lectura; no acepta ni envía apuestas."
    ),
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _feed_client() -> AltenarFeedClient:
    try:
        return AltenarFeedClient()
    except (FeedConfigurationError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _feed_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FeedConfigurationError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, FeedAccessError):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, FeedResponseError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=502, detail=f"Error consultando el feed GanaPlay/Altenar: {exc}")


def _get_events_cached(deporte: str) -> dict[str, Any]:
    now = time.monotonic()
    cached = _event_cache.get(deporte)
    if cached and now - cached[0] < EVENT_CACHE_SECONDS:
        return cached[1]

    try:
        result = _feed_client().get_events(deporte)
    except (FeedConfigurationError, FeedAccessError, FeedResponseError) as exc:
        raise _feed_http_error(exc) from exc

    result["cache_segundos"] = EVENT_CACHE_SECONDS
    _event_cache[deporte] = (now, result)
    return result


def _get_markets_cached(event_id: str) -> dict[str, Any]:
    now = time.monotonic()
    cached = _market_cache.get(event_id)
    if cached and now - cached[0] < MARKET_CACHE_SECONDS:
        return cached[1]

    try:
        result = _feed_client().get_markets(event_id)
    except (FeedConfigurationError, FeedAccessError, FeedResponseError) as exc:
        raise _feed_http_error(exc) from exc

    result["cache_segundos"] = MARKET_CACHE_SECONDS
    _market_cache[event_id] = (now, result)
    return result


@app.on_event("startup")
def verificar_datos_historicos():
    """Prepara los CSV históricos solo cuando no existen; nunca fabrica resultados."""
    archivos = [
        "nba_resultados.csv",
        "nfl_resultados.csv",
        "mlb_resultados.csv",
        "futbol_resultados.csv",
    ]
    faltantes = [nombre for nombre in archivos if not (DATOS_DIR / nombre).exists()]
    if not faltantes:
        return

    script_path = BASE_DIR / "extractor_datos.py"
    if not script_path.exists():
        print(f"⚠️ No se encontró el extractor histórico. Faltan: {faltantes}")
        return

    print(f"⚠️ Faltan datasets históricos: {faltantes}. Iniciando extracción.")
    try:
        resultado = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(BASE_DIR),
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        print(resultado.stdout[-1500:])
    except Exception as exc:
        print(f"⚠️ No fue posible actualizar los históricos: {exc}")


@app.get("/health", tags=["General"])
def health():
    archivos = [
        "nba_resultados.csv",
        "nfl_resultados.csv",
        "mlb_resultados.csv",
        "futbol_resultados.csv",
    ]
    return {
        "estado": "ok",
        "aplicacion": "EdgeBet",
        "version": VERSION,
        "hora_utc": datetime.now(timezone.utc).isoformat(),
        "fuente_cartelera": "GanaPlay / Altenar",
        "feed": feed_configuration_status(),
        "datasets": {nombre: (DATOS_DIR / nombre).exists() for nombre in archivos},
    }


@app.get("/api/info", tags=["General"])
def informacion_api():
    return {
        "mensaje": "EdgeBet API activa",
        "documentacion": "/docs",
        "interfaz": "/",
        "version": VERSION,
        "deportes": [deporte.value for deporte in DeporteEnum],
        "fuente_de_eventos_y_mercados": "GanaPlay / Altenar",
    }


@app.get("/api/v1/ganaplay/status", tags=["GanaPlay / Altenar"])
def estado_feed():
    return feed_configuration_status()


@app.get("/api/v1/ganaplay/sports", tags=["GanaPlay / Altenar"])
def deportes_feed():
    try:
        payload = _feed_client().get_sports()
        return {"fuente": "GanaPlay / Altenar", "catalogo": payload}
    except (FeedConfigurationError, FeedAccessError, FeedResponseError) as exc:
        raise _feed_http_error(exc) from exc


@app.get("/api/v1/ganaplay/events", tags=["GanaPlay / Altenar"])
def eventos_ganaplay(
    deporte: DeporteEnum = Query(...),
    live: bool | None = Query(default=None, description="Filtrar eventos en vivo o prepartido"),
):
    result = _get_events_cached(deporte.value)
    events = result.get("eventos", [])
    if live is not None:
        events = [event for event in events if event.get("en_vivo") is live]
    return {
        "fuente": result["fuente"],
        "deporte": result["deporte"],
        "sport_id": result["sport_id"],
        "generado_en": result["generado_en"],
        "total_eventos": len(events),
        "eventos_programados": sum(1 for event in events if not event.get("en_vivo")),
        "eventos_en_vivo": sum(1 for event in events if event.get("en_vivo")),
        "cache_segundos": result["cache_segundos"],
        "eventos": events,
    }


@app.get("/api/v1/ganaplay/events/{event_id}/markets", tags=["GanaPlay / Altenar"])
def mercados_evento(event_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", event_id):
        raise HTTPException(status_code=400, detail="Identificador de evento no válido.")
    return _get_markets_cached(event_id)


@app.get("/cartelera/{deporte}", tags=["Cartelera GanaPlay"])
def obtener_cartelera_ganaplay(deporte: DeporteEnum):
    """Alias compatible con la APK actual; ya no consulta ESPN."""
    result = _get_events_cached(deporte.value)
    events = result.get("eventos", [])
    cartelera = []
    for event in events:
        cartelera.append({
            "evento_id": event.get("evento_id"),
            "deporte": deporte.value,
            "liga": event.get("liga") or event.get("categoria") or "",
            "fecha_hora": event.get("fecha_hora") or "",
            "local": event.get("local") or event.get("nombre_evento") or "Evento",
            "visitante": event.get("visitante") or "",
            "estado_evento": event.get("estado_evento"),
            "fuente_eventos": "GanaPlay / Altenar",
            "fuente_cuotas": "GanaPlay / Altenar",
            "cuotas": {"local": None, "empate": None, "visitante": None},
            "probabilidades_modelo": {"local": None, "empate": None, "visitante": None},
            "modelo_disponible": False,
            "mercados_disponibles": None,
            "tiene_valor_positivo": False,
        })

    return {
        "deporte": deporte.value,
        "fuente": result["fuente"],
        "rango_fechas": datetime.now().strftime("%Y%m%d"),
        "mensaje": (
            "Cartelera recibida del feed GanaPlay/Altenar. "
            "Abre un evento para consultar sus mercados y cuotas."
        ),
        "total_partidos_analizados": len(cartelera),
        "total_con_probabilidades": 0,
        "total_con_cuotas": 0,
        "partidos_con_valor_positivo": 0,
        "cartelera": cartelera,
    }


@app.get("/equipos/{deporte}", tags=["Consulta de Datos"])
def obtener_equipos(deporte: DeporteEnum):
    datos = cargar_datos(str(DATOS_DIR))
    df = datos.get(deporte.value)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No hay datos históricos disponibles para este deporte.")

    equipos = sorted(
        set(df["equipo_local"].dropna().astype(str).unique())
        | set(df["equipo_visitante"].dropna().astype(str).unique())
    )
    return {"deporte": deporte.value, "total_equipos": len(equipos), "equipos": equipos}


@app.get("/predecir", tags=["Motor Predictivo"])
def predecir_resultado(
    deporte: DeporteEnum,
    local: str = Query(min_length=1, max_length=100),
    visitante: str = Query(min_length=1, max_length=100),
    cuota_local: float | None = Query(default=None, gt=1),
    cuota_empate: float | None = Query(default=None, gt=1),
    cuota_visitante: float | None = Query(default=None, gt=1),
):
    datos = cargar_datos(str(DATOS_DIR))
    resultado = predecir_partido(deporte.value, local.strip(), visitante.strip(), datos)
    if "error" in resultado:
        raise HTTPException(status_code=400, detail=resultado["error"])

    analisis_ev = {}
    if cuota_local is not None:
        analisis_ev["local"] = calcular_valor_ev(resultado["prob_victoria_local"] * 100, cuota_local)
    if cuota_visitante is not None:
        analisis_ev["visitante"] = calcular_valor_ev(resultado["prob_victoria_visitante"] * 100, cuota_visitante)
    if "prob_empate" in resultado and cuota_empate is not None:
        analisis_ev["empate"] = calcular_valor_ev(resultado["prob_empate"] * 100, cuota_empate)

    if analisis_ev:
        resultado["analisis_apuestas"] = analisis_ev

    return {
        "deporte": deporte.value,
        "partido": f"{local.strip()} vs {visitante.strip()}",
        "prediccion": resultado,
    }


@app.post("/actualizar-datos", tags=["Administración"])
def actualizar_datasets():
    script_path = BASE_DIR / "extractor_datos.py"
    if not script_path.exists():
        raise HTTPException(status_code=500, detail="No se encontró extractor_datos.py")

    try:
        resultado = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(BASE_DIR),
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return {
            "mensaje": "Proceso de actualización finalizado",
            "estado": "success",
            "log": resultado.stdout[-1500:],
        }
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "Falló la extracción histórica", "stderr": (exc.stderr or "")[-1500:]},
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="La actualización excedió cinco minutos.") from exc


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/service-worker.js", include_in_schema=False)
def service_worker():
    return FileResponse(
        STATIC_DIR / "service-worker.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@app.get("/", include_in_schema=False)
def inicio():
    if not INDEX_FILE.exists():
        return {"mensaje": "EdgeBet API activa", "documentacion": "/docs"}
    return FileResponse(INDEX_FILE)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api_servidor:app", host="0.0.0.0", port=port, reload=os.environ.get("RENDER") is None)
