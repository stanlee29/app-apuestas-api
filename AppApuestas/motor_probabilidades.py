"""
Módulo: motor_probabilidades.py
Descripción: Motor predictivo con ponderación de forma reciente (60/40) y cálculo de Valor Esperado (EV).
"""

import os
import math
import pandas as pd
from typing import Dict, Any

def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0: return 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)

def norm_cdf(x: float, mu: float, sigma: float) -> float:
    if sigma <= 0: return 0.5 if x >= mu else 0.0
    z = (x - mu) / (sigma * math.sqrt(2.0))
    return 0.5 * (1.0 + math.erf(z))

def calcular_valor_ev(probabilidad_pct: float, cuota_casa: float) -> Dict[str, Any]:
    """Calcula la Cuota Justa y el Valor Esperado (EV) de una apuesta."""
    prob_decimal = probabilidad_pct / 100.0
    cuota_justa = 1.0 / prob_decimal if prob_decimal > 0 else 0.0
    ev = (prob_decimal * cuota_casa) - 1.0
    return {
        "cuota_justa": round(cuota_justa, 2),
        "valor_esperado": round(ev, 4),
        "es_valor_positivo": ev > 0
    }

def cargar_datos(ruta_carpeta: str = "datos") -> Dict[str, pd.DataFrame]:
    deportes = ["nba", "nfl", "mlb", "futbol"]
    datos = {}
    for dep in deportes:
        ruta = os.path.join(ruta_carpeta, f"{dep}_resultados.csv")
        if os.path.exists(ruta):
            df = pd.read_csv(ruta).rename(columns=str.lower)
            df = df.assign(
                puntos_local=pd.to_numeric(df['puntos_local'], errors='coerce').fillna(0),
                puntos_visitante=pd.to_numeric(df['puntos_visitante'], errors='coerce').fillna(0)
            )
            datos[dep] = df
        else:
            datos[dep] = pd.DataFrame(columns=['fecha', 'equipo_local', 'equipo_visitante', 'puntos_local', 'puntos_visitante'])
    return datos

def obtener_estadisticas_equipo(df: pd.DataFrame, eq_local: str, eq_visitante: str) -> Dict[str, float]:
    """Calcula fuerza ofensiva/defensiva con peso 60% últimos 10 partidos, 40% resto de temporada."""
    league_home_scored = float(df['puntos_local'].mean())
    league_away_scored = float(df['puntos_visitante'].mean())
    league_diff_std = float(df['puntos_local'].sub(df['puntos_visitante']).std()) if len(df) > 1 else 10.0
    league_total_std = float(df['puntos_local'].add(df['puntos_visitante']).std()) if len(df) > 1 else 10.0

    def weighted_mean(col, team, is_home):
        # Filtrar partidos del equipo en la condición dada (local o visitante)
        mask = (df['equipo_local'] == team) if is_home else (df['equipo_visitante'] == team)
        team_games = df[mask].sort_values(by='fecha', ascending=False) # Más recientes primero
        
        if team_games.empty:
            return league_home_scored if is_home else league_away_scored
            
        last_10 = team_games.head(10)
        rest = team_games.iloc[10:]
        
        mean_last10 = float(last_10[col].mean())
        mean_rest = float(rest[col].mean()) if not rest.empty else mean_last10
        
        # Ponderación 60% reciente, 40% histórico
        return (mean_last10 * 0.6) + (mean_rest * 0.4)

    return {
        "home_off": max(0.1, weighted_mean('puntos_local', eq_local, is_home=True)),
        "home_def": max(0.1, weighted_mean('puntos_visitante', eq_local, is_home=True)), # Lo que recibe jugando en casa
        "away_off": max(0.1, weighted_mean('puntos_visitante', eq_visitante, is_home=False)),
        "away_def": max(0.1, weighted_mean('puntos_local', eq_visitante, is_home=False)), # Lo que recibe jugando fuera
        "league_diff_std": max(1.0, league_diff_std),
        "league_total_std": max(1.0, league_total_std)
    }

def predecir_poisson(lam_h: float, lam_a: float, under_limit: float, include_draw: bool) -> Dict[str, Any]:
    max_k = 15
    prob_h, prob_d, prob_a, prob_under = 0.0, 0.0, 0.0, 0.0
    for h in range(max_k + 1):
        for a in range(max_k + 1):
            p = poisson_pmf(h, lam_h) * poisson_pmf(a, lam_a)
            if h > a: prob_h += p
            elif h == a: prob_d += p
            else: prob_a += p
            if (h + a) <= under_limit: prob_under += p

    res = {
        "modelo": "Poisson",
        "goles_esperados_local": round(lam_h, 2),
        "goles_esperados_visitante": round(lam_a, 2),
        "prob_victoria_local": round(prob_h, 4),
        "prob_victoria_visitante": round(prob_a, 4),
        "prob_over": round(1.0 - prob_under, 4),
        "prob_under": round(prob_under, 4)
    }
    if include_draw: res["prob_empate"] = round(prob_d, 4)
    return res

def predecir_normal(mu_h: float, mu_a: float, std_diff: float, std_total: float, over_limit: float) -> Dict[str, Any]:
    mu_diff, mu_total = mu_h - mu_a, mu_h + mu_a
    prob_home_win = 1.0 - norm_cdf(0.0, mu_diff, std_diff)
    prob_over = 1.0 - norm_cdf(over_limit, mu_total, std_total)
    
    return {
        "modelo": "Normal (Puntos Esperados)",
        "puntos_esperados_local": round(mu_h, 2),
        "puntos_esperados_visitante": round(mu_a, 2),
        "handicap_estimado": round(mu_diff, 2),
        "total_puntos_esperados": round(mu_total, 2),
        "prob_victoria_local": round(prob_home_win, 4),
        "prob_victoria_visitante": round(1.0 - prob_home_win, 4),
        "prob_over": round(prob_over, 4),
        "prob_under": round(1.0 - prob_over, 4)
    }

def predecir_partido(deporte: str, equipo_local: str, equipo_visitante: str, datos: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    df = datos.get(deporte)
    if df is None or df.empty: return {"error": f"Sin datos para: {deporte}"}
    
    equipos_validos = set(df['equipo_local'].str.lower().tolist() + df['equipo_visitante'].str.lower().tolist())
    if equipo_local.lower() not in equipos_validos or equipo_visitante.lower() not in equipos_validos:
        return {"error": "Equipo no encontrado en la base de datos."}

    stats = obtener_estadisticas_equipo(df, equipo_local, equipo_visitante)
    expected_h = (stats["home_off"] + stats["away_def"]) / 2.0
    expected_a = (stats["away_off"] + stats["home_def"]) / 2.0

    if deporte in ["futbol", "mlb"]:
        under_limit = 2.5 if deporte == "futbol" else 8.5
        return predecir_poisson(expected_h, expected_a, under_limit, include_draw=(deporte == "futbol"))
    else:
        over_limit = 45.5 if deporte == "nfl" else 225.5
        return predecir_normal(expected_h, expected_a, stats["league_diff_std"], stats["league_total_std"], over_limit)
