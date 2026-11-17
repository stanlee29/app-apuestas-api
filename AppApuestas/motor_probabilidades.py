"""
Módulo: motor_probabilidades.py
Descripción: Motor predictivo deportivo basado en modelos estadísticos clásicos (Poisson y Normal).
             Compatible con Python 3.14. Usa únicamente: pandas, math, statistics, json, os.
"""

import os
import json
import math
import statistics
import pandas as pd
from typing import Dict, List, Any, Tuple

# ==============================================================================
# 1. FUNCIONES MATEMÁTICAS BASE (Sin SciPy)
# ==============================================================================

def poisson_pmf(k: int, lam: float) -> float:
    """Función de Masa de Probabilidad de Poisson: P(X = k)"""
    if lam <= 0:
        return 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)

def norm_cdf(x: float, mu: float, sigma: float) -> float:
    """
    Función de Distribución Acumulativa Normal usando math.erf.
    P(X <= x) = 0.5 * [1 + erf((x - mu) / (sigma * sqrt(2)))]
    """
    if sigma <= 0:
        return 0.5 if x >= mu else 0.0
    z = (x - mu) / (sigma * math.sqrt(2.0))
    return 0.5 * (1.0 + math.erf(z))

# ==============================================================================
# 2. CARGA Y PROCESAMIENTO DE DATOS
# ==============================================================================

def cargar_datos(ruta_carpeta: str = "datos") -> Dict[str, pd.DataFrame]:
    """Carga los 4 CSVs estandarizados y limpia los datos."""
    deportes = ["nba", "nfl", "mlb", "futbol"]
    datos = {}
    
    for dep in deportes:
        ruta_archivo = os.path.join(ruta_carpeta, f"{dep}_resultados.csv")
        if os.path.exists(ruta_archivo):
            df = pd.read_csv(ruta_archivo)
            # Estandarización y limpieza forzosa (sin inplace=True)
            df = df.rename(columns=str.lower)
            df = df.assign(
                puntos_local=pd.to_numeric(df['puntos_local'], errors='coerce').fillna(0),
                puntos_visitante=pd.to_numeric(df['puntos_visitante'], errors='coerce').fillna(0)
            )
            datos[dep] = df
        else:
            print(f"⚠️ Advertencia: No se encontró {ruta_archivo}. Se usará un DataFrame vacío.")
            columnas = ['fecha', 'equipo_local', 'equipo_visitante', 'puntos_local', 'puntos_visitante']
            datos[dep] = pd.DataFrame(columns=columnas)
            
    return datos

def obtener_estadisticas_equipo(df: pd.DataFrame, eq_local: str, eq_visitante: str) -> Dict[str, float]:
    """
    Calcula la fuerza ofensiva y defensiva de cada equipo en su rol (local/visitante).
    Si un equipo no existe en los datos, hace fallback al promedio de la liga.
    """
    # Promedios de la liga
    league_home_scored = float(df['puntos_local'].mean())
    league_away_scored = float(df['puntos_visitante'].mean())
    
    # Desviación estándar de la liga para el modelo Normal (NBA/NFL)
    diff_series = df['puntos_local'] - df['puntos_visitante']
    total_series = df['puntos_local'] + df['puntos_visitante']
    
    league_diff_std = float(diff_series.std()) if len(diff_series) > 1 else 10.0
    league_total_std = float(total_series.std()) if len(total_series) > 1 else 10.0

    # Estadísticas del Equipo Local (cuando juega en casa)
    home_games = df[df['equipo_local'] == eq_local]
    home_off = float(home_games['puntos_local'].mean()) if not home_games.empty else league_home_scored
    home_def = float(home_games['puntos_visitante'].mean()) if not home_games.empty else league_away_scored

    # Estadísticas del Equipo Visitante (cuando juega fuera)
    away_games = df[df['equipo_visitante'] == eq_visitante]
    away_off = float(away_games['puntos_visitante'].mean()) if not away_games.empty else league_away_scored
    away_def = float(away_games['puntos_local'].mean()) if not away_games.empty else league_home_scored

    return {
        "home_off": max(0.1, home_off), "home_def": max(0.1, home_def),
        "away_off": max(0.1, away_off), "away_def": max(0.1, away_def),
        "league_diff_std": max(1.0, league_diff_std),
        "league_total_std": max(1.0, league_total_std)
    }

# ==============================================================================
# 3. MOTORES DE PREDICCIÓN
# ==============================================================================

def predecir_poisson(lam_h: float, lam_a: float, under_limit: float, include_draw: bool) -> Dict[str, Any]:
    """Calcula probabilidades usando la distribución de Poisson (Fútbol y MLB)."""
    max_k = 15  # Límite seguro: >99.9% de la masa de probabilidad está por debajo de 15 goles/carreras
    
    prob_h, prob_d, prob_a, prob_under = 0.0, 0.0, 0.0, 0.0

    for h in range(max_k + 1):
        for a in range(max_k + 1):
            p = poisson_pmf(h, lam_h) * poisson_pmf(a, lam_a)
            
            if h > a:
                prob_h += p
            elif h == a:
                prob_d += p
            else:
                prob_a += p
            
            if (h + a) <= under_limit:
                prob_under += p

    prob_over = 1.0 - prob_under

    resultado = {
        "modelo": "Poisson",
        "goles_esperados_local": round(lam_h, 2),
        "goles_esperados_visitante": round(lam_a, 2),
        "prob_victoria_local": round(prob_h, 4),
        "prob_victoria_visitante": round(prob_a, 4),
        "prob_over": round(prob_over, 4),
        "prob_under": round(prob_under, 4)
    }
    
    if include_draw:
        resultado["prob_empate"] = round(prob_d, 4)
        
    return resultado

def predecir_normal(mu_h: float, mu_a: float, std_diff: float, std_total: float, over_limit: float) -> Dict[str, Any]:
    """Calcula probabilidades usando la Distribución Normal (NBA y NFL)."""
    mu_diff = mu_h - mu_a
    mu_total = mu_h + mu_a
    
    # Probabilidad de Victoria Local: P(Diferencia > 0) = 1 - CDF(0)
    prob_home_win = 1.0 - norm_cdf(0.0, mu_diff, std_diff)
    prob_away_win = 1.0 - prob_home_win # En dist. continua, P(Diferencia == 0) es ~0
    
    # Probabilidad de Over: P(Total > limit) = 1 - CDF(limit)
    prob_over = 1.0 - norm_cdf(over_limit, mu_total, std_total)
    prob_under = 1.0 - prob_over

    return {
        "modelo": "Normal (Puntos Esperados)",
        "puntos_esperados_local": round(mu_h, 2),
        "puntos_esperados_visitante": round(mu_a, 2),
        "handicap_estimado": round(mu_diff, 2),
        "total_puntos_esperados": round(mu_total, 2),
        "prob_victoria_local": round(prob_home_win, 4),
        "prob_victoria_visitante": round(prob_away_win, 4),
        "prob_over": round(prob_over, 4),
        "prob_under": round(prob_under, 4)
    }

def predecir_partido(deporte: str, equipo_local: str, equipo_visitante: str, datos: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """Función principal que enruta la predicción al modelo estadístico correcto."""
    df = datos.get(deporte)
    if df is None or df.empty:
        return {"error": f"No hay datos disponibles para el deporte: {deporte}"}
    
    # Validar que los equipos existen (búsqueda insensible a mayúsculas)
    equipos_validos = set(df['equipo_local'].str.lower().tolist() + df['equipo_visitante'].str.lower().tolist())
    if equipo_local.lower() not in equipos_validos or equipo_visitante.lower() not in equipos_validos:
        return {"error": "Uno o ambos equipos no se encuentran en la base de datos. Verifica la ortografía."}

    stats = obtener_estadisticas_equipo(df, equipo_local, equipo_visitante)
    
    # Cálculo de Valores Esperados (Lambda / Mu)
    # Fórmula clásica: (Ofensiva Local + Defensiva Visitante) / 2
    expected_h = (stats["home_off"] + stats["away_def"]) / 2.0
    expected_a = (stats["away_off"] + stats["home_def"]) / 2.0

    if deporte in ["futbol", "mlb"]:
        under_limit = 2.5 if deporte == "futbol" else 8.5
        include_draw = (deporte == "futbol")
        return predecir_poisson(expected_h, expected_a, under_limit, include_draw)
    else: # nba, nfl
        # Límites típicos de Over/Under (ajustables)
        over_limit = 45.5 if deporte == "nfl" else 225.5
        return predecir_normal(
            expected_h, expected_a, 
            stats["league_diff_std"], 
            stats["league_total_std"], 
            over_limit
        )

# ==============================================================================
# 4. INTERFAZ DE USUARIO Y EXPORTACIÓN
# ==============================================================================

def mostrar_equipos_disponibles(datos: Dict[str, pd.DataFrame]):
    """Muestra una lista limpia de equipos por deporte."""
    print("\n" + "="*60)
    print(" 📊 EQUIPOS DISPONIBLES EN LA BASE DE DATOS")
    print("="*60)
    for dep, df in datos.items():
        if not df.empty:
            # Unificar y ordenar equipos únicos
            equipos = sorted(list(set(df['equipo_local'].tolist() + df['equipo_visitante'].tolist())))
            print(f"\n🏆 {dep.upper()} ({len(equipos)} equipos):")
            # Mostrar en columnas de 4 para ahorrar espacio
            for i in range(0, len(equipos), 4):
                print("  | ".join(f"{eq:<20}" for eq in equipos[i:i+4]))
    print("="*60 + "\n")

def generar_y_guardar_muestra(datos: Dict[str, pd.DataFrame]):
    """Genera 4 predicciones de ejemplo y las guarda en JSON."""
    muestras = []
    ejemplos = [
        ("futbol", "Real Madrid", "Barcelona"),
        ("mlb", "Yankees", "Red Sox"),
        ("nba", "Lakers", "Celtics"),
        ("nfl", "Chiefs", "Eagles")
    ]
    
    for dep, local, visitante in ejemplos:
        res = predecir_partido(dep, local, visitante, datos)
        res["deporte"] = dep
        res["equipo_local"] = local
        res["equipo_visitante"] = visitante
        muestras.append(res)
        
    with open("predicciones_muestra.json", "w", encoding="utf-8") as f:
        json.dump(muestras, f, indent=4, ensure_ascii=False)
    print("💾 Se ha guardado 'predicciones_muestra.json' con 4 escenarios de ejemplo.")

def modo_interactivo(datos: Dict[str, pd.DataFrame]):
    """Bucle interactivo en consola para probar predicciones."""
    print("\n🚀 MODO INTERACTIVO DE PREDICCIÓN (Escribe 'salir' para terminar)")
    while True:
        deporte = input("\n1. Ingresa el deporte (nba, nfl, mlb, futbol): ").strip().lower()
        if deporte == 'salir':
            break
        if deporte not in datos or datos[deporte].empty:
            print("❌ Deporte no válido o sin datos. Intenta de nuevo.")
            continue
            
        local = input("2. Ingresa el Equipo Local: ").strip()
        visitante = input("3. Ingresa el Equipo Visitante: ").strip()
        
        print("\n⏳ Calculando probabilidades...")
        resultado = predecir_partido(deporte, local, visitante, datos)
        
        if "error" in resultado:
            print(f"❌ Error: {resultado['error']}")
        else:
            print("\n" + "*"*50)
            print(f" 📈 PREDICCIÓN: {local.upper()} vs {visitante.upper()} ({deporte.upper()})")
            print("*"*50)
            for clave, valor in resultado.items():
                if clave not in ["deporte", "equipo_local", "equipo_visitante"]:
                    # Formatear probabilidades como porcentajes
                    if "prob" in clave:
                        print(f"   • {clave.replace('_', ' ').title()}: {valor * 100:.2f}%")
                    else:
                        print(f"   • {clave.replace('_', ' ').title()}: {valor}")
            print("*"*50 + "\n")

# ==============================================================================
# 5. EJECUCIÓN PRINCIPAL
# ==============================================================================

if __name__ == "__main__":
    print("🧠 Iniciando Motor de Probabilidades Deportivas (Python 3.14 Ready)...")
    
    # 1. Cargar datos
    datos_deportivos = cargar_datos("datos")
    
    # Verificar que haya al menos un dato cargado
    if all(df.empty for df in datos_deportivos.values()):
        print("❌ Error crítico: No se encontraron datos en la carpeta 'datos/'. Ejecuta primero extractor_datos.py")
    else:
        # 2. Mostrar equipos disponibles
        mostrar_equipos_disponibles(datos_deportivos)
        
        # 3. Generar muestra JSON automática
        generar_y_guardar_muestra(datos_deportivos)
        
        # 4. Iniciar modo interactivo
        modo_interactivo(datos_deportivos)
        
    print("\n👋 Sesión finalizada.")