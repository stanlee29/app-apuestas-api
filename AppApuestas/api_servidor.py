"""
Módulo: api_servidor.py
Descripción: Backend FastAPI con análisis de Valor Esperado (EV), auto-arranque 
             y endpoint de cartelera inteligente cruzada con extractor_ganaplay.
             Compatible con Python 3.14.
"""

import os
import sys
import subprocess
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Importaciones del motor predictivo y del extractor de cuotas
from motor_probabilidades import predecir_partido, cargar_datos, calcular_valor_ev
from extractor_ganaplay import obtener_cartelera_con_valor

# ==============================================================================
# 1. CONFIGURACIÓN DE LA APLICACIÓN Y CORS
# ==============================================================================
app = FastAPI(
    title="API Predictor Deportivo Pro",
    description="Backend para consulta de equipos, predicciones estadísticas, análisis de EV y cartelera de valor.",
    version="2.1.0"
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
def obtener_equipos(deporte: str):
    deporte = deporte.lower()
    if deporte not in ["nba", "nfl", "mlb", "futbol"]:
        raise HTTPException(status_code=400, detail="Deporte no válido. Opciones: nba, nfl, mlb, futbol")
    
    datos = cargar_datos("datos")
    df = datos.get(deporte)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="Sin datos históricos. Ejecuta POST /actualizar-datos")
    
    equipos = sorted(list(set(df['equipo_local'].dropna().astype(str).unique()) | set(df['equipo_visitante'].dropna().astype(str).unique())))
    return {"deporte": deporte, "total_equipos": len(equipos), "equipos": equipos}


@app.get("/predecir", tags=["Motor Predictivo"])
def predecir_resultado(
    deporte: str, local: str, visitante: str,
    cuota_local: float = None, cuota_empate: float = None, cuota_visitante: float = None
):
    deporte = deporte.lower()
    if deporte not in ["nba", "nfl", "mlb", "futbol"]:
        raise HTTPException(status_code=400, detail="Deporte no válido.")
    
    datos = cargar_datos("datos")
    resultado = predecir_partido(deporte, local, visitante, datos)
    
    if "error" in resultado:
        raise HTTPException(status_code=400, detail=resultado["error"])
    
    # Análisis de Valor Esperado (EV) si se proporcionan cuotas
    analisis_ev = {}
    if cuota_local is not None:
        analisis_ev["local"] = calcular_valor_ev(resultado["prob_victoria_local"] * 100, cuota_local)
    if cuota_visitante is not None:
        analisis_ev["visitante"] = calcular_valor_ev(resultado["prob_victoria_visitante"] * 100, cuota_visitante)
    if "prob_empate" in resultado and cuota_empate is not None:
        analisis_ev["empate"] = calcular_valor_ev(resultado["prob_empate"] * 100, cuota_empate)
    
    if analisis_ev:
        resultado["analisis_apuestas"] = analisis_ev

    return {"deporte": deporte, "partido": f"{local} vs {visitante}", "prediccion": resultado}


@app.get("/cartelera/{deporte}", tags=["Cartelera con Valor"])
def obtener_cartelera_valor(deporte: str):
    """
    Extrae partidos y cuotas del día, calcula el EV cruzando con el motor 
    y devuelve la lista ordenada de mayor a menor Valor Esperado.
    """
    deporte = deporte.lower()
    if deporte not in ["nba", "nfl", "mlb", "futbol"]:
        raise HTTPException(status_code=400, detail="Deporte no válido. Opciones: nba, nfl, mlb, futbol")
    
    try:
        # 1 & 2: Extraer cuotas y calcular EV automáticamente
        cartelera = obtener_cartelera_con_valor(deporte)
        
        if not cartelera:
            return {
                "deporte": deporte,
                "mensaje": "No se encontraron partidos con cuotas disponibles para analizar.",
                "cartelera": []
            }
        
        # 3: Ordenar de MAYOR a MENOR Valor Esperado
        # Buscamos el EV máximo entre (local, empate, visitante) para usarlo como clave de ordenamiento
        def obtener_max_ev(partido: dict) -> float:
            evs = partido.get("analisis_ev", {})
            if not evs:
                return -999.0
            return max((ev.get("valor_esperado", -999.0) for ev in evs.values()), default=-999.0)
        
        cartelera_ordenada = sorted(cartelera, key=obtener_max_ev, reverse=True)
        
        # Contar cuántos tienen valor positivo para resumen rápido
        partidos_con_valor = sum(1 for p in cartelera_ordenada if p.get("tiene_valor_positivo", False))
        
        return {
            "deporte": deporte,
            "total_partidos_analizados": len(cartelera_ordenada),
            "partidos_con_valor_positivo": partidos_con_valor,
            "cartelera": cartelera_ordenada
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar la cartelera: {str(e)}")


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
    return {"mensaje": "API Predictor Deportivo Pro Activa", "documentacion": "/docs", "version": "2.1.0"}


# ==============================================================================
# 4. EJECUCIÓN PRINCIPAL
# ==============================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    is_production = os.environ.get("RENDER") is not None
    print(f"🚀 Servidor corriendo en http://0.0.0.0:{port}")
    uvicorn.run("api_servidor:app", host="0.0.0.0", port=port, reload=not is_production)
