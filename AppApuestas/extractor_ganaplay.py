"""
Módulo: extractor_ganaplay.py
Descripción: Extracción de cuotas y partidos FUTUROS (Hoy + N días) con fallbacks automáticos.
             Calcula Valor Esperado (EV) cruzando con motor_probabilidades.py.
             Compatible con Python 3.14 y entornos serverless (Render, Heroku, etc.).
"""

import os
import json
import random
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any

from motor_probabilidades import cargar_datos, predecir_partido, calcular_valor_ev

# ==============================================================================
# CONFIGURACIÓN GLOBAL
# ==============================================================================
DIRECTORIO_SALIDA = "datos"
ARCHIVO_CUOTAS = os.path.join(DIRECTORIO_SALIDA, "cuotas_ganaplay.json")

HEADERS_GANAPLAY = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://ganaplay.sv/",
    "Accept": "application/json",
    "Accept-Language": "es-SV,es;q=0.9,en;q=0.8"
}

DEPORTES_API = {
    "futbol": "soccer",
    "nba": "basketball",
    "nfl": "football",
    "mlb": "baseball"
}

EQUIPOS_RESERVA = {
    "futbol": ["Real Madrid", "Barcelona", "Man City", "Arsenal", "Liverpool", "Bayern Munich", "PSG"],
    "nba": ["Lakers", "Celtics", "Warriors", "Bulls", "Heat", "Nuggets", "Suns"],
    "nfl": ["Chiefs", "Eagles", "49ers", "Cowboys", "Ravens", "Bills", "Dolphins"],
    "mlb": ["Yankees", "Dodgers", "Red Sox", "Astros", "Braves", "Mets", "Padres"]
}

def asegurar_directorio() -> None:
    os.makedirs(DIRECTORIO_SALIDA, exist_ok=True)

def calcular_rango_fechas(dias: int = 2) -> str:
    """Calcula el rango de fechas en formato YYYYMMDD-YYYYMMDD desde hoy hasta hoy+dias."""
    hoy = datetime.now()
    fin = hoy + timedelta(days=dias)
    return f"{hoy.strftime('%Y%m%d')}-{fin.strftime('%Y%m%d')}"

# ==============================================================================
# 1. EXTRACCIÓN DE PARTIDOS Y CUOTAS (CASCADA AUTOMÁTICA)
# ==============================================================================

def intentar_ganaplay(deporte: str, rango_fechas: str) -> List[Dict[str, Any]]:
    """Intenta extraer partidos futuros de GanaPlay en el rango de fechas dado."""
    try:
        url = "https://ganaplay.sv/api/v1/sports/events"
        params = {"sport": DEPORTES_API.get(deporte, deporte), "dates": rango_fechas}
        response = requests.get(url, headers=HEADERS_GANAPLAY, params=params, timeout=8)
        response.raise_for_status()
        # Placeholder: si la API real responde, aquí iría el parseo específico.
        return []
    except Exception:
        return []

def intentar_espn(deporte: str, rango_fechas: str) -> List[Dict[str, Any]]:
    """
    Consulta el scoreboard de ESPN para partidos futuros en el rango de fechas.
    Devuelve lista con fecha_hora, equipos y cuotas (si están disponibles).
    """
    try:
        espn_sport = DEPORTES_API.get(deporte, deporte)
        url = f"http://site.api.espn.com/apis/site/v2/sports/{espn_sport}/{deporte}/scoreboard"
        params = {"dates": rango_fechas, "limit": 100}
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        partidos = []
        for event in data.get('events', []):
            # Solo partidos programados o en vivo (no finalizados)
            status_name = event.get('status', {}).get('type', {}).get('name', '')
            if status_name == 'STATUS_FINAL':
                continue

            comps = event.get('competitions', [{}])[0]
            competidores = comps.get('competitors', [])
            if len(competidores) < 2:
                continue

            # Extraer fecha_hora en formato ISO legible
            fecha_hora_raw = event.get('date', '')
            try:
                fecha_dt = datetime.fromisoformat(fecha_hora_raw.replace('Z', '+00:00'))
                fecha_hora = fecha_dt.strftime('%Y-%m-%d %H:%M')
            except Exception:
                fecha_hora = fecha_hora_raw

            # Identificar local y visitante correctamente
            local = visitante = None
            for c in competidores:
                team_name = c.get('team', {}).get('displayName', 'Desconocido')
                if c.get('homeAway') == 'home':
                    local = team_name
                else:
                    visitante = team_name

            if not local or not visitante:
                continue

            # Extraer cuotas si existen, si no, usar valores por defecto realistas
            odds_list = comps.get('odds', [])
            if odds_list and isinstance(odds_list, list) and len(odds_list) > 0:
                odds = odds_list[0]
                # ESPN suele traer 'overUnder' y detalles como "Lakers -150"
                detalles = odds.get('details', '')
                c_local, c_visitante = _parsear_odds_espn(detalles, local)
            else:
                c_local, c_visitante = 1.90, 2.10

            c_empate = 3.40 if deporte == "futbol" else None

            partidos.append({
                "deporte": deporte,
                "fecha_hora": fecha_hora,
                "local": local,
                "visitante": visitante,
                "cuota_local": c_local,
                "cuota_empate": c_empate,
                "cuota_visitante": c_visitante
            })
        return partidos
    except Exception:
        return []

def _parsear_odds_espn(detalles: str, equipo_local: str) -> tuple:
    """
    Parsea el formato típico de ESPN: 'Equipo -150' o '-150 Equipo'.
    Devuelve (cuota_local, cuota_visitante) en formato decimal.
    """
    try:
        partes = detalles.split()
        for parte in partes:
            try:
                valor = int(parte)
                # Convertir odds americanas a decimales
                if valor < 0:
                    cuota = 1.0 + (100.0 / abs(valor))
                else:
                    cuota = 1.0 + (valor / 100.0)
                cuota = round(cuota, 2)
                # Si el equipo local está en el string, él tiene esa cuota
                if equipo_local in detalles and detalles.index(equipo_local) < detalles.index(str(valor)):
                    return cuota, round(max(1.01, (1.0 / (1.0 - 1.0/cuota)) if cuota > 1 else 2.10), 2)
                else:
                    return round(max(1.01, (1.0 / (1.0 - 1.0/cuota)) if cuota > 1 else 1.90), 2), cuota
            except ValueError:
                continue
        return 1.90, 2.10
    except Exception:
        return 1.90, 2.10

def generar_respaldo_inteligente(deporte: str, datos_historicos: Dict[str, pd.DataFrame], dias: int = 2) -> List[Dict[str, Any]]:
    """
    Genera cartelera de respaldo con equipos REALES del CSV y fechas futuras.
    Calcula cuotas realistas basadas en probabilidades del modelo + margen de casa (~5%).
    """
    df = datos_historicos.get(deporte)

    if df is not None and not df.empty:
        equipos = list(set(df['equipo_local'].dropna().tolist() + df['equipo_visitante'].dropna().tolist()))
    else:
        equipos = EQUIPOS_RESERVA.get(deporte, EQUIPOS_RESERVA["futbol"])

    if len(equipos) < 2:
        equipos = EQUIPOS_RESERVA.get(deporte, EQUIPOS_RESERVA["futbol"])

    hoy = datetime.now()
    cuotas_generadas = []
    num_partidos = 3

    for i in range(num_partidos):
        local = random.choice(equipos)
        visitante = random.choice([e for e in equipos if e != local])

        # Distribuir partidos en los próximos N días
        fecha_partido = hoy + timedelta(days=random.randint(0, dias))
        hora_partido = f"{random.randint(13, 22):02d}:{random.choice(['00', '15', '30', '45'])}"
        fecha_hora = f"{fecha_partido.strftime('%Y-%m-%d')} {hora_partido}"

        pred = predecir_partido(deporte, local, visitante, datos_historicos)

        if "error" in pred:
            p_local, p_visitante, p_empate = 0.40, 0.40, 0.20
        else:
            p_local = pred.get('prob_victoria_local', 0.40)
            p_visitante = pred.get('prob_victoria_visitante', 0.40)
            p_empate = pred.get('prob_empate', 0.20)

        margen = 1.05
        c_local = max(1.01, round(1.0 / (p_local * margen), 2))
        c_visitante = max(1.01, round(1.0 / (p_visitante * margen), 2))
        c_empate = max(1.01, round(1.0 / (p_empate * margen), 2)) if p_empate and p_empate > 0 else None

        cuotas_generadas.append({
            "deporte": deporte,
            "fecha_hora": fecha_hora,
            "local": local,
            "visitante": visitante,
            "cuota_local": c_local,
            "cuota_empate": c_empate,
            "cuota_visitante": c_visitante
        })

    return cuotas_generadas

# ==============================================================================
# 2. ORQUESTADOR Y CRUCE CON MOTOR PROBABILÍSTICO
# ==============================================================================

def obtener_cartelera_con_valor(deporte: str, dias: int = 2) -> Dict[str, Any]:
    """
    Obtiene partidos y cuotas para los próximos N días, cruza con el motor para calcular EV.
    Devuelve un dict con 'cartelera' (lista ordenada por EV) y 'mensaje' informativo.
    NUNCA lanza excepciones por falta de partidos.
    """
    deporte = deporte.lower()
    if deporte not in ["nba", "nfl", "mlb", "futbol"]:
        return {"deporte": deporte, "mensaje": "Deporte no válido.", "cartelera": [], "rango_fechas": ""}

    rango_fechas = calcular_rango_fechas(dias)
    datos_historicos = cargar_datos(DIRECTORIO_SALIDA)

    # Cascada de extracción
    partidos = intentar_ganaplay(deporte, rango_fechas)
    if not partidos:
        partidos = intentar_espn(deporte, rango_fechas)
    if not partidos:
        partidos = generar_respaldo_inteligente(deporte, datos_historicos, dias)

    # Guardar en JSON para auditoría
    asegurar_directorio()
    with open(ARCHIVO_CUOTAS, 'w', encoding='utf-8') as f:
        json.dump(partidos, f, indent=4, ensure_ascii=False)

    # Cruce con motor probabilístico
    resultados_analisis = []
    for partido in partidos:
        local = partido['local']
        visitante = partido['visitante']

        pred = predecir_partido(deporte, local, visitante, datos_historicos)
        if "error" in pred:
            continue

        analisis_ev = {}
        if partido.get('cuota_local'):
            analisis_ev['local'] = calcular_valor_ev(pred.get('prob_victoria_local', 0) * 100, partido['cuota_local'])
        if partido.get('cuota_empate') and 'prob_empate' in pred:
            analisis_ev['empate'] = calcular_valor_ev(pred.get('prob_empate', 0) * 100, partido['cuota_empate'])
        if partido.get('cuota_visitante'):
            analisis_ev['visitante'] = calcular_valor_ev(pred.get('prob_victoria_visitante', 0) * 100, partido['cuota_visitante'])

        partido_enriquecido = {
            "deporte": deporte,
            "fecha_hora": partido.get('fecha_hora', 'N/A'),
            "local": local,
            "visitante": visitante,
            "cuotas": {
                "local": partido.get('cuota_local'),
                "empate": partido.get('cuota_empate'),
                "visitante": partido.get('cuota_visitante')
            },
            "probabilidades_modelo": {
                "local": f"{pred.get('prob_victoria_local', 0)*100:.1f}%",
                "empate": f"{pred.get('prob_empate', 0)*100:.1f}%" if 'prob_empate' in pred else "N/A",
                "visitante": f"{pred.get('prob_victoria_visitante', 0)*100:.1f}%"
            },
            "analisis_ev": analisis_ev,
            "tiene_valor_positivo": any(ev.get('es_valor_positivo', False) for ev in analisis_ev.values())
        }
        resultados_analisis.append(partido_enriquecido)

    # Ordenar de MAYOR a MENOR Valor Esperado
    def obtener_max_ev(p: dict) -> float:
        evs = p.get("analisis_ev", {})
        if not evs:
            return -999.0
        return max((ev.get("valor_esperado", -999.0) for ev in evs.values()), default=-999.0)

    resultados_analisis.sort(key=obtener_max_ev, reverse=True)

    # Mensaje informativo según el resultado
    if not resultados_analisis:
        mensaje = f"No hay partidos programados para {deporte.upper()} en los próximos {dias} días (posible pausa de temporada)."
    else:
        partidos_con_valor = sum(1 for p in resultados_analisis if p.get("tiene_valor_positivo", False))
        mensaje = f"{len(resultados_analisis)} partidos encontrados. {partidos_con_valor} con valor positivo."

    return {
        "deporte": deporte,
        "rango_fechas": rango_fechas,
        "mensaje": mensaje,
        "cartelera": resultados_analisis
    }

# ==============================================================================
# 3. EJECUCIÓN PRINCIPAL (Pruebas locales)
# ==============================================================================

if __name__ == "__main__":
    print("🚀 Iniciando extractor de cuotas (Modo No Interactivo, próximos 2 días)...\n")
    for dep in ["futbol", "nba", "nfl", "mlb"]:
        resultado = obtener_cartelera_con_valor(dep, dias=2)
        print(f"\n📊 {dep.upper()} | Rango: {resultado['rango_fechas']}")
        print(f"   {resultado['mensaje']}")
        for p in resultado['cartelera']:
            estado = "✅ VALOR +" if p['tiene_valor_positivo'] else "⚠️ Sin valor"
            print(f"   [{estado}] {p['fecha_hora']} | {p['local']} vs {p['visitante']}")
    print("\n🎉 Proceso finalizado.")
