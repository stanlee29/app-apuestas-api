"""
API FastAPI para EdgeBet.
Sirve la interfaz PWA y expone endpoints de cartelera, equipos y predicciones.
"""
import os
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from motor_probabilidades import predecir_partido, cargar_datos, calcular_valor_ev
from extractor_ganaplay import obtener_cartelera_con_valor

BASE_DIR = Path(__file__).resolve().parent
DATOS_DIR = BASE_DIR / "datos"
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"
VERSION = "0.1.0"


class DeporteEnum(str, Enum):
    nba = "nba"
    nfl = "nfl"
    mlb = "mlb"
    futbol = "futbol"


app = FastAPI(
    title="EdgeBet API",
    description="API de análisis deportivo y probabilidades estimadas. Las cuotas solo se muestran cuando la fuente las proporciona.",
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


@app.on_event("startup")
def verificar_datos_historicos():
    """Intenta preparar los CSV si faltan. No genera resultados ficticios."""
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


@app.get("/cartelera/{deporte}", tags=["Cartelera ESPN"])
def obtener_cartelera_valor(
    deporte: DeporteEnum,
    dias: int = Query(default=2, ge=0, le=7),
):
    try:
        resultado = obtener_cartelera_con_valor(deporte.value, dias=dias)
        cartelera = resultado.get("cartelera", [])
        return {
            "deporte": deporte.value,
            "rango_fechas": resultado.get("rango_fechas", ""),
            "mensaje": resultado.get("mensaje", ""),
            "total_partidos_analizados": len(cartelera),
            "partidos_con_valor_positivo": sum(
                1 for partido in cartelera if partido.get("tiene_valor_positivo", False)
            ),
            "total_con_probabilidades": sum(
                1 for partido in cartelera if partido.get("modelo_disponible", False)
            ),
            "total_con_cuotas": sum(
                1 for partido in cartelera if partido.get("fuente_cuotas")
            ),
            "cartelera": cartelera,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"No fue posible consultar la cartelera: {exc}") from exc


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
