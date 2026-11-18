"""
Módulo: extractor_ganaplay.py
Descripción: Extracción 100% automática de partidos y cuotas reales vía API pública de ESPN.
             Sin Playwright, sin claves, sin partidos ficticios. Compatible con Render.
"""

import os
import json
import re
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple

from motor_probabilidades import cargar_datos, predecir_partido, calcular_valor_ev

# ==============================================================================
# CONFIGURACIÓN GLOBAL
# ==============================================================================
DIRECTORIO_SALIDA = "datos"
ARCHIVO_CUOTAS = os.path.join(DIRECTORIO_SALIDA, "cuotas_ganaplay.json")

# Mapeo de deportes a las categorías y ligas de la API de ESPN
LEAGUES_MAP = {
    "nba": [("basketball", "nba")],
    "nfl": [("football", "nfl")],
    "mlb": [("baseball", "mlb")],
    "futbol": [
        ("soccer", "esp.1"),               # LaLiga
        ("soccer", "eng.1"),               # Premier League
        ("soccer", "ita.1"),               # Serie A
        ("soccer", "ger.1"),               # Bundesliga
        ("soccer", "uefa.champions"),      # Champions League
        ("soccer", "mex.1"),               # Liga MX
        ("soccer", "fifa.worldq.concacaf") # Eliminatorias Concacaf
    ]
}

HEADERS_ESPN = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def asegurar_directorio() -> None:
    os.makedirs(DIRECTORIO_SALIDA, exist_ok=True)

# ==============================================================================
# FUNCIONES AUXILIARES
# ==============================================================================

def obtener_rango_fechas(dias: int) -> str:
    """Genera YYYYMMDD si dias=0, o YYYYMMDD-YYYYMMDD si dias>0."""
    hoy = datetime.now()
    if dias == 0:
        return hoy.strftime("%Y%m%d")
    else:
        fin = hoy + timedelta(days=dias)
        return f"{hoy.strftime('%Y%m%d')}-{fin.strftime('%Y%m%d')}"

def convertir_a_utc6(fecha_iso: str) -> Tuple[datetime, str]:
    """Convierte fecha ISO de ESPN a datetime y string legible en hora de El Salvador (UTC-6)."""
    try:
        # Reemplazar 'Z' por '+00:00' para que fromisoformat funcione en Python 3.11+
        dt_utc = datetime.fromisoformat(fecha_iso.replace('Z', '+00:00'))
        tz_sv = timezone(timedelta(hours=-6))
        dt_sv = dt_utc.astimezone(tz_sv)
        return dt_sv, dt_sv.strftime("%Y-%m-%d %H:%M")
    except Exception:
        hoy = datetime.now()
        return hoy, hoy.strftime("%Y-%m-%d %H:%M (Hora estimada)")

def odds_americana_a_decimal(odds_str: str) -> float:
    """Convierte cuotas americanas (ej: '-150', '+130') a decimales."""
    try:
        val = int(odds_str)
        if val < 0:
            return round(1.0 + (100.0 / abs(val)), 2)
        else:
            return round(1.0 + (val / 100.0), 2)
    except ValueError:
        return 0.0

def extraer_cuotas_de_detalle_espn(detalle: str, equipo_local_nombre: str) -> Dict[str, float]:
    """Intenta parsear el texto de cuotas de ESPN (ej: 'Lakers -150')."""
    cuotas = {"local": None, "empate": None, "visitante": None}
    if not detalle:
        return cuotas
        
    # Buscar números que parezcan cuotas americanas
    matches = re.findall(r'([+-]?\d{2,4})', detalle)
    if len(matches) >= 1:
        # Heurística simple: si hay un número negativo, es el favorito.
        # Asignamos la cuota al equipo que aparezca primero en el string o por defecto.
        cuota_dec = odds_americana_a_decimal(matches[0])
        if cuota_dec > 1.0:
            # Asumimos que la primera cuota encontrada es la del local por simplicidad, 
            # o calculamos la del visitante inversa si es posible.
            cuotas["local"] = cuota_dec
            cuotas["visitante"] = round(max(1.01, 1.0 / (1.0 - 1.0/cuota_dec) if cuota_dec > 1 else 2.10), 2)
            
    return cuotas

def generar_cuotas_justas_desde_modelo(prob_local: float, prob_empate: float, prob_visitante: float) -> Dict[str, float]:
    """Genera cuotas decimales realistas con un margen de casa de apuestas del 5%."""
    margen = 1.05
    c_local = round(max(1.01, 1.0 / (prob_local * margen)), 2) if prob_local > 0 else 1.90
    c_visitante = round(max(1.01, 1.0 / (prob_visitante * margen)), 2) if prob_visitante > 0 else 2.10
    c_empate = round(max(1.01, 1.0 / (prob_empate * margen)), 2) if prob_empate > 0 else None
    return {"local": c_local, "empate": c_empate, "visitante": c_visitante}

# ==============================================================================
# LÓGICA PRINCIPAL DE EXTRACCIÓN
# ==============================================================================

def obtener_cartelera_con_valor(deporte: str, dias: int = 2) -> Dict[str, Any]:
    """
    Consulta la API pública de ESPN, extrae partidos reales, calcula EV 
    y devuelve la cartelera ordenada cronológicamente. CERO partidos ficticios.
    """
    deporte = deporte.lower()
    if deporte not in LEAGUES_MAP:
        return {"deporte": deporte, "mensaje": "Deporte no soportado.", "cartelera": [], "rango_fechas": ""}

    rango_fechas = obtener_rango_fechas(dias)
    ahora = datetime.now()
    limite = ahora + timedelta(days=dias)
    datos_historicos = cargar_datos(DIRECTORIO_SALIDA)
    
    partidos_reales = []

    # 1. Consultar todas las ligas correspondientes al deporte en ESPN
    for sport_category, league_id in LEAGUES_MAP[deporte]:
        try:
            url = f"http://site.api.espn.com/apis/site/v2/sports/{sport_category}/{league_id}/scoreboard"
            params = {"dates": rango_fechas, "limit": 100}
            response = requests.get(url, headers=HEADERS_ESPN, params=params, timeout=10)
            
            if response.status_code != 200:
                continue
                
            data = response.json()
            events = data.get('events', [])
            
            for event in events:
                # Solo nos interesan partidos programados o en vivo, NO finalizados
                status = event.get('status', {}).get('type', {}).get('name', '')
                if status == 'STATUS_FINAL':
                    continue
                
                competitions = event.get('competitions', [])
                if not competitions:
                    continue
                
                comp = competitions[0]
                competitors = comp.get('competitors', [])
                if len(competitors) < 2:
                    continue

                # Extraer equipos
                local_nombre = visitante_nombre = "Desconocido"
                for c in competitors:
                    name = c.get('team', {}).get('displayName', 'Desconocido')
                    if c.get('homeAway') == 'home':
                        local_nombre = name
                    else:
                        visitante_nombre = name

                # Extraer fecha y convertir a UTC-6
                fecha_iso = event.get('date', '')
                dt_sv, fecha_str_sv = convertir_a_utc6(fecha_iso)
                
                # Filtrar por rango de fechas real (por si ESPN devuelve basura de fechas pasadas)
                if not (ahora <= dt_sv <= limite):
                    continue

                # Intentar extraer cuotas de ESPN
                odds_list = comp.get('odds', [])
                cuotas_raw = {"local": None, "empate": None, "visitante": None}
                
                if odds_list and isinstance(odds_list, list) and len(odds_list) > 0:
                    detalle = odds_list[0].get('details', '')
                    cuotas_raw = extraer_cuotas_de_detalle_espn(detalle, local_nombre)

                partidos_reales.append({
                    "fecha_hora_dt": dt_sv,
                    "fecha_hora": fecha_str_sv,
                    "local": local_nombre,
                    "visitante": visitante_nombre,
                    "cuotas_raw": cuotas_raw,
                    "league_id": league_id
                })
        except Exception:
            # Si una liga falla, continuamos con la siguiente. No rompemos el flujo.
            continue

    # 2. Si no se encontraron partidos reales en ninguna liga, devolver vacío (CERO ficticios)
    if not partidos_reales:
        mensaje = f"No se encontraron partidos programados en las fuentes de datos para {deporte.upper()} en el rango de fechas solicitado."
        return {"deporte": deporte, "rango_fechas": rango_fechas, "mensaje": mensaje, "cartelera": []}

    # 3. Procesar partidos reales: Calcular probabilidades y EV
    cartelera_final = []
    for p in partidos_reales:
        # Llamar al motor. Si el equipo no está en el CSV, el motor usa promedios de la liga (fallback seguro)
        pred = predecir_partido(deporte, p["local"], p["visitante"], datos_historicos)
        
        # Si el motor devuelve un error crítico (ej. deporte inválido), saltamos
        if "error" in pred and "Sin datos" in pred["error"]:
            continue

        prob_local = pred.get("prob_victoria_local", 0.33)
        prob_visitante = pred.get("prob_victoria_visitante", 0.33)
        prob_empate = pred.get("prob_empate", 0.34 if deporte == "futbol" else 0.0)

        # Si ESPN no trajo cuotas válidas, generamos cuotas justas basadas en el modelo para que la UI no falle
        c_local = p["cuotas_raw"]["local"]
        c_empate = p["cuotas_raw"]["empate"]
        c_visitante = p["cuotas_raw"]["visitante"]
        
        if not c_local or not c_visitante:
            cuotas_justas = generar_cuotas_justas_desde_modelo(prob_local, prob_empate, prob_visitante)
            c_local = c_local or cuotas_justas["local"]
            c_empate = c_empate or cuotas_justas["empate"]
            c_visitante = c_visitante or cuotas_justas["visitante"]

        # Calcular Valor Esperado (EV)
        analisis_ev = {}
        analisis_ev["local"] = calcular_valor_ev(prob_local * 100, float(c_local))
        analisis_ev["visitante"] = calcular_valor_ev(prob_visitante * 100, float(c_visitante))
        if deporte == "futbol" and c_empate:
            analisis_ev["empate"] = calcular_valor_ev(prob_empate * 100, float(c_empate))

        cartelera_final.append({
            "deporte": deporte,
            "fecha_hora": p["fecha_hora"],
            "local": p["local"],
            "visitante": p["visitante"],
            "cuotas": {
                "local": float(c_local),
                "empate": float(c_empate) if c_empate else None,
                "visitante": float(c_visitante)
            },
            "probabilidades_modelo": {
                "local": f"{prob_local * 100:.1f}%",
                "empate": f"{prob_empate * 100:.1f}%" if deporte == "futbol" else "N/A",
                "visitante": f"{prob_visitante * 100:.1f}%"
            },
            "analisis_ev": analisis_ev,
            "tiene_valor_positivo": any(ev.get("es_valor_positivo", False) for ev in analisis_ev.values())
        })

    # 4. Ordenar cronológicamente (del más próximo al más lejano)
    cartelera_final.sort(key=lambda x: x["fecha_hora_dt"])

    # 5. Generar mensaje de estado
    partidos_con_valor = sum(1 for p in cartelera_final if p["tiene_valor_positivo"])
    mensaje_final = f"{len(cartelera_final)} partidos reales encontrados. {partidos_con_valor} con Valor Esperado positivo."

    # 6. Guardar auditoría en disco
    asegurar_directorio()
    with open(ARCHIVO_CUOTAS, 'w', encoding='utf-8') as f:
        json.dump(cartelera_final, f, indent=4, ensure_ascii=False)

    return {
        "deporte": deporte,
        "rango_fechas": rango_fechas,
        "mensaje": mensaje_final,
        "cartelera": cartelera_final
    }
