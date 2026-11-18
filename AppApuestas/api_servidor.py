"""
Módulo: api_servidor.py
Descripción: Backend FastAPI con menú desplegable de deportes, análisis de EV,
             consulta de partidos futuros (Hoy + N días) y auto-arranque.
             Compatible con Python 3.14.
"""

import os
import sys
import subprocess
from enum import Enum
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from motor_probabilidades import predecir_partido, cargar_datos, calcular_valor_ev
from extractor_ganaplay import obtener_cartelera_con_valor

# ==============================================================================
# ENUM PARA MENÚ DESPLEGABLE EN /docs
# ==============================================================================
class DeporteEnum(str, Enum):
    nba = "nba"
    nfl = "nfl"
    mlb = "mlb"
    futbol = "futbol"

# ==============================================================================
# 1. CONFIGURACIÓN DE LA APLICACIÓN Y CORS
# ==============================================================================
app = FastAPI(
    title="API Predictor Deportivo Pro",
    description="Backend para consulta de equipos, predicciones estadísticas, análisis de EV y cartelera de partidos futuros.",
    version="2.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# 2. EVENTO DE INICIO AUTOMÁTICO (STARTUP)
# ==============================================================================
@app.on_event("startup")
def verificar_y_descargar_datos():
    """Auto-arranque: descarga datos históricos si no existen en la carpeta /datos."""
    datos_dir = "datos"
    archivos = ["nba_resultados.csv", "nfl_resultados.csv", "mlb_resultados.csv", "futbol_resultados.csv"]

    if not os.path.exists(datos_dir) or not all(os.path.exists(os.path.join(datos_dir, f)) for f in archivos):
        print("⚠️ Arranque sin datos históricos. Ejecutando extractor automático...")
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extractor_datos.py")
        try:
            subprocess.run([sys.executable, script_path], check=True, capture_output=True, text=True, timeout=300)
            print("✅ Descarga automática de datos históricos completada.")
        except Exception as e:
            print(f"❌ Error en arranque automático de datos: {e}")

# ==============================================================================
# 3. ENDPOINTS
# ==============================================================================

@app.get("/equipos/{deporte}", tags=["Consulta de Datos"])
def obtener_equipos(deporte: DeporteEnum):
    datos = cargar_datos("datos")
    df = datos.get(deporte.value)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="Sin datos históricos. Ejecuta POST /actualizar-datos")

    equipos = sorted(list(set(df['equipo_local'].dropna().astype(str).unique()) | set(df['equipo_visitante'].dropna().astype(str).unique())))
    return {"deporte": deporte.value, "total_equipos": len(equipos), "equipos": equipos}


@app.get("/predecir", tags=["Motor Predictivo"])
def predecir_resultado(
    deporte: DeporteEnum,
    local: str,
    visitante: str,
    cuota_local: float = None,
    cuota_empate: float = None,
    cuota_visitante: float = None
):
    datos = cargar_datos("datos")
    resultado = predecir_partido(deporte.value, local, visitante, datos)

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

    return {"deporte": deporte.value, "partido": f"{local} vs {visitante}", "prediccion": resultado}


@app.get("/cartelera/{deporte}", tags=["Cartelera con Valor"])
def obtener_cartelera_valor(
    deporte: DeporteEnum,
    dias: int = Query(default=2, ge=1, le=14, description="Número de días hacia adelante a consultar (1 a 14)")
):
    """
    Extrae partidos y cuotas desde HOY hasta HOY + N días, calcula el EV
    cruzando con el motor y devuelve la lista ordenada de mayor a menor Valor Esperado.
    Si el deporte está en pausa, devuelve lista vacía con mensaje informativo (NO error 500).
    """
    try:
        resultado = obtener_cartelera_con_valor(deporte.value, dias=dias)

        return {
            "deporte": deporte.value,
            "rango_fechas": resultado.get("rango_fechas", ""),
            "mensaje": resultado.get("mensaje", ""),
            "total_partidos_analizados": len(resultado.get("cartelera", [])),
            "partidos_con_valor_positivo": sum(1 for p in resultado.get("cartelera", []) if p.get("tiene_valor_positivo", False)),
            "cartelera": resultado.get("cartelera", [])
        }
    except Exception as e:
        # Nunca devolver 500 por falta de partidos; solo por errores críticos
        raise HTTPException(status_code=500, detail=f"Error crítico al generar la cartelera: {str(e)}")


@app.post("/actualizar-datos", tags=["Administración"])
def actualizar_datasets():
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extractor_datos.py")
    if not os.path.exists(script_path):
        raise HTTPException(status_code=500, detail="No se encontró extractor_datos.py")

    try:
        resultado = subprocess.run(
            [sys.executable, script_path],
            check=True, capture_output=True, text=True, timeout=300
        )
        return {
            "mensaje": "Datos históricos actualizados exitosamente",
            "estado": "success",
            "log": resultado.stdout[-300:]
        }
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail={"error": "Fallo en extractor", "stderr": e.stderr[-300:]})
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeout de 5 minutos excedido")


@app.get("/", tags=["General"])
def root():
    return {"mensaje": "API Predictor Deportivo Pro Activa", "documentacion": "/docs", "version": "2.2.0"}


# ==============================================================================
# 4. EJECUCIÓN PRINCIPAL
# ==============================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    is_production = os.environ.get("RENDER") is not None
    print(f"🚀 Servidor corriendo en http://0.0.0.0:{port}")
    uvicorn.run("api_servidor:app", host="0.0.0.0", port=port, reload=not is_production)
