"""
Módulo: api_servidor.py
Descripción: Backend en FastAPI para el sistema de análisis deportivo.
             Expone endpoints para consultar equipos, obtener predicciones 
             y actualizar los datasets bajo demanda (vía subprocess).
             Compatible con Python 3.14.
"""

import os
import sys
import subprocess
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Importaciones EXCLUSIVAS del motor de predicción
# (No se importa nada de extractor_datos.py para evitar conflictos de variables)
from motor_probabilidades import predecir_partido, cargar_datos

# ==============================================================================
# 1. CONFIGURACIÓN DE LA APLICACIÓN Y CORS
# ==============================================================================
app = FastAPI(
    title="API de Análisis Deportivo Predictivo",
    description="Backend para consulta de equipos, predicciones estadísticas y actualización de datos deportivos.",
    version="1.1.0"
)

# CORS abierto para la futura App Android
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# 2. ENDPOINTS
# ==============================================================================

@app.get("/equipos/{deporte}", tags=["Consulta de Datos"])
def obtener_equipos(deporte: str):
    """
    Devuelve la lista en JSON de todos los equipos disponibles 
    en el CSV del deporte especificado.
    """
    deporte = deporte.lower()
    deportes_validos = ["nba", "nfl", "mlb", "futbol"]
    
    if deporte not in deportes_validos:
        raise HTTPException(
            status_code=400, 
            detail=f"Deporte no válido. Opciones permitidas: {', '.join(deportes_validos)}"
        )
    
    try:
        datos = cargar_datos("datos")
        df = datos.get(deporte)
        
        if df is None or df.empty:
            raise HTTPException(
                status_code=404, 
                detail=f"No se encontraron datos para '{deporte}'. Ejecuta el endpoint POST /actualizar-datos primero."
            )
        
        # Unificar equipos de ambas columnas, eliminar nulos y ordenar
        equipos_locales = set(df['equipo_local'].dropna().astype(str).unique())
        equipos_visitantes = set(df['equipo_visitante'].dropna().astype(str).unique())
        equipos_unicos = sorted(list(equipos_locales.union(equipos_visitantes)))
        
        return {
            "deporte": deporte,
            "total_equipos": len(equipos_unicos),
            "equipos": equipos_unicos
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno al procesar los datos: {str(e)}")


@app.get("/predecir", tags=["Motor Predictivo"])
def predecir_resultado(deporte: str, local: str, visitante: str):
    """
    Calcula y devuelve las probabilidades de un partido específico 
    utilizando el motor estadístico (Poisson o Normal).
    """
    deporte = deporte.lower()
    deportes_validos = ["nba", "nfl", "mlb", "futbol"]
    
    if deporte not in deportes_validos:
        raise HTTPException(
            status_code=400, 
            detail=f"Deporte no válido. Opciones permitidas: {', '.join(deportes_validos)}"
        )
    
    if not local or not visitante:
        raise HTTPException(
            status_code=400, 
            detail="Los parámetros 'local' y 'visitante' son obligatorios."
        )
    
    try:
        datos = cargar_datos("datos")
        resultado = predecir_partido(deporte, local, visitante, datos)
        
        if "error" in resultado:
            raise HTTPException(status_code=400, detail=resultado["error"])
        
        return {
            "deporte": deporte,
            "partido": f"{local} vs {visitante}",
            "prediccion": resultado
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")


@app.post("/actualizar-datos", tags=["Administración"])
def actualizar_datasets():
    """
    Ejecuta el script extractor_datos.py como un proceso hijo 
    para refrescar los CSV con la información más reciente.
    """
    # Ruta absoluta al script extractor (asumiendo que está en la misma carpeta que este archivo)
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extractor_datos.py")
    
    if not os.path.exists(script_path):
        raise HTTPException(
            status_code=500, 
            detail=f"No se encontró el script extractor_datos.py en: {script_path}"
        )
    
    try:
        print("🔄 Iniciando actualización de datos bajo demanda (subprocess)...")
        
        # Ejecutar extractor_datos.py como proceso aislado
        # sys.executable garantiza usar el mismo intérprete Python que corre FastAPI
        # capture_output=True captura stdout/stderr para diagnóstico
        resultado = subprocess.run(
            [sys.executable, script_path],
            check=True,
            capture_output=True,
            text=True,
            timeout=300  # Timeout de 5 minutos por si la red es lenta
        )
        
        print("✅ Actualización de datos completada.")
        print(f"📝 Log del extractor:\n{resultado.stdout}")
        
        return {
            "mensaje": "Datos actualizados exitosamente en la carpeta /datos",
            "estado": "success",
            "log_extracto": resultado.stdout[-500:] if resultado.stdout else "Sin salida"
        }
        
    except subprocess.CalledProcessError as e:
        # El script terminó con código de error distinto de 0
        print(f"❌ Error en extractor_datos.py:\n{e.stderr}")
        raise HTTPException(
            status_code=500,
            detail={
                "mensaje": "El script extractor_datos.py falló durante la ejecución",
                "codigo_salida": e.returncode,
                "error_stderr": e.stderr[-500:] if e.stderr else "Sin detalles"
            }
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail="La actualización de datos tardó demasiado tiempo (timeout de 5 minutos excedido)"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error crítico al ejecutar el extractor: {str(e)}"
        )


# ==============================================================================
# 3. ENDPOINT RAÍZ (Health Check)
# ==============================================================================
@app.get("/", tags=["General"])
def root():
    return {
        "mensaje": "API de Análisis Deportivo activa",
        "documentacion": "/docs",
        "version": "1.1.0"
    }

# ==============================================================================
# 4. EJECUCIÓN PRINCIPAL
# ==============================================================================
if __name__ == "__main__":
    import os
    
    # Leer el puerto dinámico asignado por Render (o usar 8000 por defecto en local)
    port = int(os.environ.get("PORT", 8000))
    
    print(f"🚀 Iniciando servidor FastAPI en http://0.0.0.0:{port}")
    print("📚 Documentación interactiva (Swagger UI) disponible en: /docs")
    print("🔴 Documentación alternativa (ReDoc) disponible en: /redoc")
    
    # Detectar si estamos en Render para desactivar el 'reload' (mejor práctica en producción)
    # La variable de entorno 'RENDER' es True automáticamente en sus servidores.
    is_production = os.environ.get("RENDER") is not None
    
    uvicorn.run(
        "api_servidor:app", 
        host="0.0.0.0", 
        port=port, 
        reload=not is_production  # True en tu PC, False en la nube
    )