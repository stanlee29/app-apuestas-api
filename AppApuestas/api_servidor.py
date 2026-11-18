"""API de AppApuestas: cartelera, mercados y análisis estadístico."""
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from motor_probabilidades import predecir_partido, cargar_datos, calcular_valor_ev
from sports_game_odds import (
    SportsGameOddsClient,
    ProviderConfigurationError,
    ProviderAccessError,
    ProviderResponseError,
    provider_status,
    EL_SALVADOR_TZ,
)

from integraciones_pitchapi import PitchAPIClient, PitchAPIError, pitchapi_status
from statsbomb_open_data import StatsBombOpenData, StatsBombDataError, statsbomb_status
from modelos_futbol import predict_from_matches, evaluate_walk_forward

BASE_DIR = Path(__file__).resolve().parent
DATOS_DIR = BASE_DIR / "datos"
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"
VERSION = "1.0.6"
EVENT_CACHE_SECONDS = max(60, int(os.getenv("SPORTSGAMEODDS_CACHE_SECONDS", "600")))
MARKET_CACHE_SECONDS = max(60, int(os.getenv("SPORTSGAMEODDS_MARKET_CACHE_SECONDS", "600")))

_event_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_market_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_model_data_cache: tuple[float, dict[str, Any]] | None = None


class SportEnum(str, Enum):
    futbol = "futbol"
    nba = "nba"
    nfl = "nfl"
    mlb = "mlb"


app = FastAPI(
    title="AppApuestas API",
    description="API de consulta deportiva, cuotas y mercados. Solo lectura; no acepta ni envía apuestas.",
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


def _client() -> SportsGameOddsClient:
    try:
        return SportsGameOddsClient()
    except (ProviderConfigurationError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _provider_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProviderConfigurationError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, ProviderAccessError):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, ProviderResponseError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=502, detail=f"Error consultando el proveedor deportivo: {exc}")


def _get_events_cached(sport: str, days: int, live: bool | None = None) -> dict[str, Any]:
    local_day = datetime.now(EL_SALVADOR_TZ).date().isoformat()
    key = f"{sport}:{days}:{live}:{local_day}"
    now = time.monotonic()
    cached = _event_cache.get(key)
    if cached and now - cached[0] < EVENT_CACHE_SECONDS:
        return cached[1]

    try:
        result = _client().get_events(sport, days=days, live=live)
    except (ProviderConfigurationError, ProviderAccessError, ProviderResponseError) as exc:
        raise _provider_http_error(exc) from exc

    result["cache_segundos"] = EVENT_CACHE_SECONDS
    _event_cache[key] = (now, result)
    for event in result.get("eventos", []):
        event_id = str(event.get("evento_id") or "")
        if event_id:
            _market_cache[event_id] = (now, {
                "fuente": result["fuente"],
                "evento_id": event_id,
                "total_mercados": event.get("mercados_disponibles", 0),
                "mercados": event.get("mercados", []),
                "uso": result.get("uso", {}),
            })
    return result


def _get_markets_cached(event_id: str) -> dict[str, Any]:
    now = time.monotonic()
    cached = _market_cache.get(event_id)
    if cached and now - cached[0] < MARKET_CACHE_SECONDS:
        return cached[1]

    try:
        result = _client().get_event(event_id)
    except (ProviderConfigurationError, ProviderAccessError, ProviderResponseError) as exc:
        raise _provider_http_error(exc) from exc

    result["cache_segundos"] = MARKET_CACHE_SECONDS
    _market_cache[event_id] = (now, result)
    return result


def _historical_data() -> dict[str, Any]:
    global _model_data_cache
    now = time.monotonic()
    if _model_data_cache and now - _model_data_cache[0] < 300:
        return _model_data_cache[1]
    data = cargar_datos(str(DATOS_DIR))
    _model_data_cache = (now, data)
    return data


def _model_probabilities(sport: str, home: str, away: str) -> tuple[dict[str, Any], str | None]:
    try:
        prediction = predecir_partido(sport, home, away, _historical_data())
    except Exception as exc:
        return {}, f"No fue posible ejecutar el modelo: {type(exc).__name__}"
    if "error" in prediction:
        return {}, str(prediction["error"])

    output = {}
    for key, target in (
        ("prob_victoria_local", "local"),
        ("prob_empate", "empate"),
        ("prob_victoria_visitante", "visitante"),
    ):
        value = prediction.get(key)
        if isinstance(value, (float, int)):
            output[target] = round(float(value) * 100.0, 1)
    return output, None


def _main_market_prices(event: dict[str, Any]) -> dict[str, float | None]:
    result: dict[str, float | None] = {"local": None, "empate": None, "visitante": None}
    markets = event.get("mercados") or []
    candidates = [
        market for market in markets
        if any(token in str(market.get("nombre", "")).casefold() for token in ("moneyline", "match winner", "ganador"))
    ]
    for market in candidates:
        for selection in market.get("selecciones", []):
            side = str(selection.get("lado") or "").casefold()
            target = {"home": "local", "draw": "empate", "away": "visitante"}.get(side)
            if not target:
                continue
            best = selection.get("mejor_cuota") or {}
            price = best.get("cuota_decimal")
            if isinstance(price, (float, int)) and (result[target] is None or price > result[target]):
                result[target] = float(price)
    return result


def _event_for_legacy_card(event: dict[str, Any], sport: str) -> dict[str, Any]:
    probabilities, model_error = _model_probabilities(
        sport, str(event.get("local") or ""), str(event.get("visitante") or "")
    )
    odds = _main_market_prices(event)
    ev = {}
    for key, probability_key in (
        ("local", "local"), ("empate", "empate"), ("visitante", "visitante")
    ):
        probability = probabilities.get(probability_key)
        price = odds.get(key)
        if probability is not None and price is not None:
            ev[key] = calcular_valor_ev(probability, price)

    return {
        "evento_id": event.get("evento_id"),
        "deporte": sport,
        "liga": event.get("liga"),
        "fecha_hora": event.get("fecha_hora"),
        "local": event.get("local"),
        "visitante": event.get("visitante"),
        "estado_evento": event.get("estado_evento"),
        "en_vivo": event.get("en_vivo", False),
        "fuente_eventos": event.get("fuente_eventos"),
        "fuente_cuotas": event.get("fuente_cuotas"),
        "cuotas": odds,
        "probabilidades_modelo": probabilities,
        "modelo_disponible": bool(probabilities),
        "error_modelo": model_error,
        "analisis_ev": ev,
        "mercados_disponibles": event.get("mercados_disponibles", 0),
        "tiene_valor_positivo": any(item.get("es_valor_positivo") for item in ev.values()),
    }


@app.get("/health", tags=["General"])
def health():
    return {
        "estado": "ok",
        "aplicacion": "AppApuestas",
        "version": VERSION,
        "hora_utc": datetime.now(timezone.utc).isoformat(),
        "proveedor": provider_status(),
        "datasets": {
            f"{sport}_resultados.csv": (DATOS_DIR / f"{sport}_resultados.csv").exists()
            for sport in ("futbol", "nba", "nfl", "mlb")
        },
    }


@app.get("/api/info", tags=["General"])
def api_info():
    return {
        "mensaje": "AppApuestas API activa",
        "documentacion": "/docs",
        "interfaz": "/",
        "version": VERSION,
        "deportes": [sport.value for sport in SportEnum],
    }


@app.get("/api/v1/source/status", tags=["Proveedor"])
def source_status():
    return provider_status()


@app.get("/api/v1/research/status", tags=["Investigación"])
def research_status():
    return {
        "proveedores": {
            "sports_game_odds": provider_status(),
            "pitchapi": pitchapi_status(),
            "statsbomb_open_data": statsbomb_status(),
        },
        "capacidades": {
            "cartelera_y_cuotas": "SportsGameOdds",
            "xg_remates_h2h_heatmaps": "PitchAPI (requiere clave gratuita)",
        },
    }


@app.get("/api/v1/research/football/leagues", tags=["Investigación"])
def research_football_leagues():
    try:
        leagues = PitchAPIClient().list_leagues()
    except PitchAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail={
            "codigo": exc.code, "mensaje": str(exc)
        }) from exc
    return {
        "fuente": "PitchAPI",
        "total_ligas": len(leagues),
        "ligas": leagues,
    }


@app.get("/api/v1/research/football/date/{fecha}", tags=["Investigación"])
def research_football_date(
    fecha: str,
    status: str = Query(default="all", pattern="^(played|upcoming|all)$"),
):
    try:
        date.fromisoformat(fecha)
        data = PitchAPIClient().matches_by_date(fecha, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PitchAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail={
            "codigo": exc.code, "mensaje": str(exc)
        }) from exc
    matches = data.get("matches", []) if isinstance(data, dict) else []
    return {
        "fuente": "PitchAPI",
        "fecha": fecha,
        "estado_consultado": status,
        "total_eventos": len(matches),
        "eventos": matches,
    }


@app.get("/api/v1/research/football/leagues/{league_id}/matches", tags=["Investigación"])
def research_football_league_matches(
    league_id: str,
    season: str | None = Query(default=None, max_length=20),
    status: str = Query(default="all", pattern="^(played|upcoming|all)$"),
):
    try:
        data = PitchAPIClient().league_matches(league_id, season=season, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PitchAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail={
            "codigo": exc.code, "mensaje": str(exc)
        }) from exc
    matches = data.get("matches", []) if isinstance(data, dict) else []
    return {
        "fuente": "PitchAPI",
        "liga": data.get("league") if isinstance(data, dict) else None,
        "total_eventos": len(matches),
        "eventos": matches,
    }


@app.get("/api/v1/research/football/matches/{match_id}/analysis", tags=["Investigación"])
def research_football_match_analysis(match_id: str):
    try:
        return PitchAPIClient().match_analysis(match_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PitchAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail={
            "codigo": exc.code, "mensaje": str(exc)
        }) from exc


@app.get("/api/v1/research/football/matches/{match_id}/live", tags=["Investigación"])
def research_football_match_live(match_id: str):
    try:
        return PitchAPIClient().match_live(match_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PitchAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail={
            "codigo": exc.code, "mensaje": str(exc)
        }) from exc


@app.get("/api/v1/research/statsbomb/competitions", tags=["Investigación"])
def research_statsbomb_competitions():
    try:
        competitions = StatsBombOpenData().competitions()
    except StatsBombDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {
        "fuente": "StatsBomb Open Data",
        "total_competiciones": len(competitions),
        "competiciones": competitions,
        "atribucion": "StatsBomb",
    }


@app.get(
    "/api/v1/research/statsbomb/competitions/{competition_id}/seasons/{season_id}/matches",
    tags=["Investigación"],
)
def research_statsbomb_matches(competition_id: int, season_id: int):
    try:
        matches = StatsBombOpenData().matches(competition_id, season_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StatsBombDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    matches.sort(key=lambda item: str(item.get("match_date") or ""), reverse=True)
    return {
        "fuente": "StatsBomb Open Data",
        "competition_id": competition_id,
        "season_id": season_id,
        "total_partidos": len(matches),
        "partidos": matches,
        "atribucion": "StatsBomb",
    }


@app.get("/api/v1/research/statsbomb/matches/{match_id}/analysis", tags=["Investigación"])
def research_statsbomb_match_analysis(
    match_id: int,
    competition_id: int = Query(..., ge=1),
    season_id: int = Query(..., ge=1),
):
    try:
        return StatsBombOpenData().match_analysis(match_id, competition_id, season_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StatsBombDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/api/v1/research/statsbomb/predict", tags=["Modelos"])
def research_statsbomb_predict(
    competition_id: int = Query(..., ge=1),
    season_id: int = Query(..., ge=1),
    fecha_partido: date = Query(..., description="Fecha YYYY-MM-DD del partido que se quiere analizar"),
    local: str = Query(..., min_length=1, max_length=100),
    visitante: str = Query(..., min_length=1, max_length=100),
    rho: float = Query(default=-0.08, ge=-0.25, le=0.25),
):
    try:
        statsbomb = StatsBombOpenData()
        all_matches = statsbomb.matches(competition_id, season_id)
        matches = statsbomb.matches_before_date(all_matches, fecha_partido.isoformat())
        xg_rates = statsbomb.recent_team_xg(matches, local, visitante, limit=8)
        result = predict_from_matches(matches, local, visitante, rho=rho, xg_rates=xg_rates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StatsBombDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    result["competicion_id"] = competition_id
    result["temporada_id"] = season_id
    result["fecha_objetivo"] = fecha_partido.isoformat()
    result["regla_temporal"] = "Solo resultados anteriores al día del partido; el día objetivo queda excluido."
    return result


@app.get("/api/v1/research/statsbomb/backtest", tags=["Modelos"])
def research_statsbomb_backtest(
    competition_id: int = Query(..., ge=1),
    season_id: int = Query(..., ge=1),
    min_train: int = Query(default=30, ge=20, le=500),
    rho: float = Query(default=-0.08, ge=-0.25, le=0.25),
):
    try:
        matches = StatsBombOpenData().matches(competition_id, season_id)
        result = evaluate_walk_forward(matches, min_train=min_train, rho=rho)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StatsBombDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    result["competicion_id"] = competition_id
    result["temporada_id"] = season_id
    return result


@app.get("/api/v1/sports", tags=["Proveedor"])
def sports():
    return {
        "deportes": [
            {"id": "futbol", "nombre": "Fútbol"},
            {"id": "nba", "nombre": "NBA"},
            {"id": "nfl", "nombre": "NFL"},
            {"id": "mlb", "nombre": "MLB"},
        ],
        "ligas_configuradas": provider_status()["ligas"],
    }


@app.get("/api/v1/events", tags=["Eventos"])
def events(
    deporte: SportEnum = Query(...),
    dias: int = Query(default=2, ge=0, le=7),
    live: bool | None = Query(default=None),
):
    result = _get_events_cached(deporte.value, dias, live)
    return {
        "fuente": result["fuente"],
        "deporte": result["deporte"],
        "ligas_consultadas": result["ligas_consultadas"],
        "generado_en": result["generado_en"],
        "total_eventos": result["total_eventos"],
        "eventos_en_vivo": result["eventos_en_vivo"],
        "eventos_programados": result["eventos_programados"],
        "cache_segundos": result["cache_segundos"],
        "ventana_consulta": result.get("ventana_consulta", {}),
        "uso": result.get("uso", {}),
        "eventos": result["eventos"],
    }


@app.get("/api/v1/events/{event_id}/markets", tags=["Mercados"])
def event_markets(event_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", event_id):
        raise HTTPException(status_code=400, detail="Identificador de evento no válido.")
    return _get_markets_cached(event_id)


@app.get("/cartelera/{deporte}", tags=["Cartelera"])
def cartelera(
    deporte: SportEnum,
    dias: int = Query(default=2, ge=0, le=7),
):
    result = _get_events_cached(deporte.value, dias)
    cards = [_event_for_legacy_card(event, deporte.value) for event in result["eventos"]]
    window = result.get("ventana_consulta") or {}
    today_local = datetime.now(EL_SALVADOR_TZ).date()
    start = datetime.fromisoformat(window.get("fecha_inicio_local", today_local.isoformat())).date()
    end = datetime.fromisoformat(
        window.get("fecha_fin_local", (today_local + timedelta(days=dias)).isoformat())
    ).date()
    leagues = result.get("ligas_consultadas", [])
    message = (
        f"Se consultaron {', '.join(leagues)} del {start:%d/%m/%Y} al {end:%d/%m/%Y} "
        "en hora de El Salvador. Abre el detalle para consultar los mercados y precios publicados."
        if cards else
        f"SportsGameOdds no devolvió eventos para {', '.join(leagues)} "
        f"entre el {start:%d/%m/%Y} y el {end:%d/%m/%Y}. "
        "También se incluyen eventos que todavía no tienen cuotas; puede que no haya partidos "
        "en las ligas configuradas para esas fechas."
    )
    return {
        "deporte": deporte.value,
        "fuente": result["fuente"],
        "rango_fechas": f"{start:%Y%m%d}-{end:%Y%m%d}",
        "fecha_inicio_local": start.isoformat(),
        "fecha_fin_local": end.isoformat(),
        "zona_horaria": window.get("zona_horaria", "America/El_Salvador"),
        "dias_incluidos": window.get("dias_incluidos", dias + 1),
        "ligas_consultadas": leagues,
        "ventana_consulta": window,
        "mensaje": message,
        "total_partidos_analizados": len(cards),
        "total_con_probabilidades": sum(1 for item in cards if item["modelo_disponible"]),
        "total_con_cuotas": sum(1 for item in cards if any(item["cuotas"].values())),
        "partidos_con_valor_positivo": sum(1 for item in cards if item["tiene_valor_positivo"]),
        "uso": result.get("uso", {}),
        "cartelera": cards,
    }


@app.get("/equipos/{deporte}", tags=["Históricos"])
def equipos(deporte: SportEnum):
    data = _historical_data()
    frame = data.get(deporte.value)
    if frame is None or frame.empty:
        raise HTTPException(status_code=404, detail="No hay datos históricos para este deporte.")
    names = sorted(
        set(frame["equipo_local"].dropna().astype(str).unique())
        | set(frame["equipo_visitante"].dropna().astype(str).unique())
    )
    return {"deporte": deporte.value, "total_equipos": len(names), "equipos": names}


@app.get("/predecir", tags=["Modelo"])
def predict(
    deporte: SportEnum,
    local: str = Query(min_length=1, max_length=100),
    visitante: str = Query(min_length=1, max_length=100),
    cuota_local: float | None = Query(default=None, gt=1),
    cuota_empate: float | None = Query(default=None, gt=1),
    cuota_visitante: float | None = Query(default=None, gt=1),
):
    try:
        prediction = predecir_partido(deporte.value, local.strip(), visitante.strip(), _historical_data())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error del modelo: {type(exc).__name__}") from exc
    if "error" in prediction:
        raise HTTPException(status_code=400, detail=prediction["error"])

    ev = {}
    probabilities = {
        "local": prediction.get("prob_victoria_local"),
        "empate": prediction.get("prob_empate"),
        "visitante": prediction.get("prob_victoria_visitante"),
    }
    prices = {"local": cuota_local, "empate": cuota_empate, "visitante": cuota_visitante}
    for side, probability in probabilities.items():
        if probability is not None and prices[side] is not None:
            ev[side] = calcular_valor_ev(float(probability) * 100.0, float(prices[side]))
    if ev:
        prediction["analisis_ev"] = ev
    return {
        "deporte": deporte.value,
        "partido": f"{local.strip()} vs {visitante.strip()}",
        "prediccion": prediction,
    }


@app.post("/actualizar-datos", tags=["Administración"])
def update_historical_data():
    import subprocess
    import sys

    script = BASE_DIR / "extractor_datos.py"
    if not script.exists():
        raise HTTPException(status_code=500, detail="No se encontró el extractor histórico.")
    try:
        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(BASE_DIR),
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=500, detail=(exc.stderr or "")[-1500:]) from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="La actualización superó cinco minutos.") from exc
    global _model_data_cache
    _model_data_cache = None
    return {"estado": "success", "log": completed.stdout[-1500:]}


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
def index():
    if not INDEX_FILE.exists():
        return {"mensaje": "AppApuestas API activa", "documentacion": "/docs"}
    return FileResponse(INDEX_FILE)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api_servidor:app", host="0.0.0.0", port=port, reload=os.environ.get("RENDER") is None)
