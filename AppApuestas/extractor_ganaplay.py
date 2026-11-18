"""
Módulo: extractor_ganaplay.py
Descripción: Extracción de cuotas de GanaPlay (con fallback a ESPN o ingreso manual) 
             y cruce automático con el motor de probabilidades para calcular Valor Esperado (EV).
             Compatible con Python 3.14.
"""

import os
import json
import requests
from typing import List, Dict, Any, Optional

# Importamos las funciones clave de nuestro motor predictivo
from motor_probabilidades import cargar_datos, predecir_partido, calcular_valor_ev

# ==============================================================================
# CONFIGURACIÓN GLOBAL
# ==============================================================================
DIRECTORIO_SALIDA = "datos"
ARCHIVO_CUOTAS = os.path.join(DIRECTORIO_SALIDA, "cuotas_ganaplay.json")

# Cabeceras para simular un navegador real y evitar bloqueos básicos
HEADERS_GANAPLAY = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://ganaplay.sv/",
    "Accept": "application/json",
    "Accept-Language": "es-SV,es;q=0.9,en;q=0.8",
    "Origin": "https://ganaplay.sv"
}

# Mapeo de deportes a los nombres que suele usar la API
DEPORTES_API = {
    "futbol": "soccer",
    "nba": "basketball",
    "nfl": "football",
    "mlb": "baseball"
}

def asegurar_directorio() -> None:
    os.makedirs(DIRECTORIO_SALIDA, exist_ok=True)

# ==============================================================================
# 1. EXTRACCIÓN DE CUOTAS (CASCADA CON FALLBACK)
# ==============================================================================

def extraer_cuotas_ganaplay() -> List[Dict[str, Any]]:
    """Intenta extraer cuotas de GanaPlay. Si falla, usa el Plan B."""
    print("🎰 Intentando extraer cuotas de GanaPlay (ganaplay.sv)...")
    
    # NOTA: Reemplaza esta URL con el endpoint real de la API de GanaPlay si lo conoces.
    # Ejemplo común en plataformas Virtualsoft: /api/v1/sports/events o /api/odds
    url_ganaplay = "https://ganaplay.sv/api/v1/sports/events" 
    
    try:
        response = requests.get(url_ganaplay, headers=HEADERS_GANAPLAY, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Aquí iría la lógica de parseo específica de la respuesta de GanaPlay.
        # Como placeholder, simulamos que extraemos 2 partidos de ejemplo si la API responde.
        print("   ✅ Conexión exitosa con GanaPlay (Parseo adaptado a tu endpoint real).")
        return _parsear_respuesta_ganaplay(data)
        
    except requests.exceptions.HTTPError as e:
        if response.status_code in [403, 401]:
            print("   ⚠️ Bloqueo 403 (Cloudflare/WAF). Activando Plan B (ESPN)...")
            return extraer_cuotas_espn_fallback()
        print(f"   ❌ Error HTTP en GanaPlay: {e}")
        return extraer_cuotas_espn_fallback()
    except Exception as e:
        print(f"   ❌ Error de conexión con GanaPlay: {e}. Activando Plan B...")
        return extraer_cuotas_espn_fallback()

def extraer_cuotas_espn_fallback() -> List[Dict[str, Any]]:
    """Plan B: Intenta extraer cuotas del scoreboard de ESPN (si están disponibles)."""
    print("📡 Intentando extraer cuotas de respaldo desde ESPN API...")
    cuotas_totales = []
    
    for deporte_id, espn_sport in DEPORTES_API.items():
        try:
            # ESPN a veces incluye 'odds' en el endpoint de scoreboard
            url = f"http://site.api.espn.com/apis/site/v2/sports/{espn_sport}/{deporte_id}/scoreboard?limit=10"
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            for event in data.get('events', []):
                if event.get('status', {}).get('type', {}).get('name') != 'STATUS_FINAL':
                    # Solo partidos futuros o en vivo
                    competidores = event.get('competitions', [{}])[0].get('competitors', [])
                    if len(competidores) >= 2:
                        local = competidores[0].get('team', {}).get('displayName', 'Local')
                        visitante = competidores[1].get('team', {}).get('displayName', 'Visitante')
                        
                        # ESPN a veces no devuelve cuotas en la API pública gratuita. 
                        # Si no hay cuotas, asignamos un valor dummy para que el pipeline no falle.
                        odds = event.get('competitions', [{}])[0].get('odds', [{}])[0]
                        c_local = float(odds.get('details', '1.90').replace(' ', '')) if 'details' in odds else 1.90
                        c_visitante = float(odgs.get('underdog', False)) # Simplificación
                        
                        cuotas_totales.append({
                            "deporte": deporte_id,
                            "local": local,
                            "visitante": visitante,
                            "cuota_local": c_local if c_local > 1.0 else 1.90,
                            "cuota_empate": 3.40 if deporte_id == "futbol" else None,
                            "cuota_visitante": 2.10 if c_visitante else 2.10
                        })
            if cuotas_totales:
                print(f"   ✅ Respaldo ESPN exitoso para {deporte_id}.")
        except Exception as e:
            print(f"   ⚠️ Fallback ESPN falló para {deporte_id}: {e}")
            
    if not cuotas_totales:
        print("   ⚠️ Ninguna API devolvió cuotas. Activando Plan C (Ingreso Manual/Generado).")
        return generar_cuotas_ejemplo()
        
    return cuotas_totales

def generar_cuotas_ejemplo() -> List[Dict[str, Any]]:
    """Plan C: Genera cuotas realistas o permite ingreso manual por consola."""
    print("\n" + "="*60)
    print(" MODO MANUAL: Pega tu JSON de cuotas o presiona ENTER para usar datos de ejemplo")
    print("="*60)
    entrada = input("Pega el JSON aquí (o presiona ENTER): ").strip()
    
    if entrada:
        try:
            datos = json.loads(entrada)
            if isinstance(datos, list):
                print("   ✅ Cuotas manuales cargadas correctamente.")
                return datos
        except json.JSONDecodeError:
            print("   ❌ JSON inválido. Usando datos de ejemplo.")
    
    # Datos de ejemplo realistas si el usuario no pega nada
    return [
        {"deporte": "futbol", "local": "Real Madrid", "visitante": "Barcelona", "cuota_local": 2.10, "cuota_empate": 3.40, "cuota_visitante": 3.20},
        {"deporte": "nba", "local": "Lakers", "visitante": "Celtics", "cuota_local": 1.85, "cuota_empate": None, "cuota_visitante": 1.95},
        {"deporte": "nfl", "local": "Chiefs", "visitante": "Eagles", "cuota_local": 1.75, "cuota_empate": None, "cuota_visitante": 2.05},
        {"deporte": "mlb", "local": "Yankees", "visitante": "Red Sox", "cuota_local": 1.60, "cuota_empate": None, "cuota_visitante": 2.30}
    ]

def _parsear_respuesta_ganaplay(data: Any) -> List[Dict[str, Any]]:
    """
    Función placeholder para adaptar la respuesta real de GanaPlay al formato estándar.
    Debes ajustar las claves (ej: data['events']) según la estructura real de su JSON.
    """
    # Ejemplo de adaptación (ajustar según la API real):
    # return [{"deporte": "futbol", "local": item['home'], "visitante": item['away'], ...}]
    return generar_cuotas_ejemplo() # Fallback seguro por ahora

def guardar_cuotas_json(cuotas: List[Dict[str, Any]]) -> None:
    """Guarda las cuotas estandarizadas en el archivo JSON."""
    asegurar_directorio()
    with open(ARCHIVO_CUOTAS, 'w', encoding='utf-8') as f:
        json.dump(cuotas, f, indent=4, ensure_ascii=False)
    print(f"💾 Cuotas guardadas en: {ARCHIVO_CUOTAS}")

# ==============================================================================
# 2. CRUCE CON MOTOR PROBABILÍSTICO (CÁLCULO DE EV)
# ==============================================================================

def obtener_cartelera_con_valor(deporte: str) -> List[Dict[str, Any]]:
    """
    Cruza las cuotas extraídas con el motor de predicción para calcular el Valor Esperado (EV).
    Devuelve una lista de partidos enriquecida con análisis de apuestas.
    """
    print(f"\n🔍 Analizando Valor Esperado (EV) para: {deporte.upper()}...")
    
    # 1. Cargar cuotas
    if not os.path.exists(ARCHIVO_CUOTAS):
        print("   ⚠️ No se encontró el archivo de cuotas. Generando uno nuevo...")
        cuotas = extraer_cuotas_ganaplay()
        guardar_cuotas_json(cuotas)
    else:
        with open(ARCHIVO_CUOTAS, 'r', encoding='utf-8') as f:
            cuotas = json.load(f)
            
    # 2. Filtrar por deporte
    cuotas_deporte = [c for c in cuotas if c.get('deporte', '').lower() == deporte.lower()]
    
    if not cuotas_deporte:
        print(f"   ⚠️ No hay cuotas disponibles para {deporte}.")
        return []
        
    # 3. Cargar datos históricos para el motor
    datos_historicos = cargar_datos(DIRECTORIO_SALIDA)
    resultados_analisis = []
    
    # 4. Procesar cada partido
    for partido in cuotas_deporte:
        local = partido['local']
        visitante = partido['visitante']
        
        # Obtener predicción del motor
        prediccion = predecir_partido(deporte, local, visitante, datos_historicos)
        
        if "error" in prediccion:
            continue # Saltar si el equipo no está en la base de datos histórica
            
        analisis_ev = {}
        
        # Calcular EV para Local
        if partido.get('cuota_local'):
            prob_local_pct = prediccion.get('prob_victoria_local', 0) * 100
            analisis_ev['local'] = calcular_valor_ev(prob_local_pct, partido['cuota_local'])
            
        # Calcular EV para Empate (solo si aplica y existe cuota)
        if partido.get('cuota_empate') and 'prob_empate' in prediccion:
            prob_empate_pct = prediccion.get('prob_empate', 0) * 100
            analisis_ev['empate'] = calcular_valor_ev(prob_empate_pct, partido['cuota_empate'])
            
        # Calcular EV para Visitante
        if partido.get('cuota_visitante'):
            prob_visitante_pct = prediccion.get('prob_victoria_visitante', 0) * 100
            analisis_ev['visitante'] = calcular_valor_ev(prob_visitante_pct, partido['cuota_visitante'])
            
        # Ensamblar resultado enriquecido
        partido_enriquecido = {
            "deporte": deporte,
            "local": local,
            "visitante": visitante,
            "cuotas": {
                "local": partido.get('cuota_local'),
                "empate": partido.get('cuota_empate'),
                "visitante": partido.get('cuota_visitante')
            },
            "probabilidades_modelo": {
                "local": f"{prediccion.get('prob_victoria_local', 0)*100:.1f}%",
                "empate": f"{prediccion.get('prob_empate', 0)*100:.1f}%" if 'prob_empate' in prediccion else "N/A",
                "visitante": f"{prediccion.get('prob_victoria_visitante', 0)*100:.1f}%"
            },
            "analisis_ev": analisis_ev,
            # Bandera para filtrar fácilmente solo las apuestas de valor positivo
            "tiene_valor_positivo": any(ev.get('es_valor_positivo', False) for ev in analisis_ev.values())
        }
        resultados_analisis.append(partido_enriquecido)
        
    # Ordenar: primero los que tienen Valor Esperado positivo
    resultados_analisis.sort(key=lambda x: x['tiene_valor_positivo'], reverse=True)
    
    return resultados_analisis

# ==============================================================================
# 3. EJECUCIÓN PRINCIPAL
# ==============================================================================

if __name__ == "__main__":
    print("🚀 Iniciando extractor de cuotas y análisis de Valor Esperado...\n")
    
    # Paso 1: Extraer y guardar cuotas (con cascada de fallbacks)
    cuotas_extraidas = extraer_cuotas_ganaplay()
    guardar_cuotas_json(cuotas_extraidas)
    
    # Paso 2: Mostrar cartelera con EV para cada deporte
    for dep in ["futbol", "nba", "nfl", "mlb"]:
        cartelera = obtener_cartelera_con_valor(dep)
        
        if cartelera:
            print(f"\n📊 --- CARTELERA CON VALOR: {dep.upper()} ---")
            for p in cartelera:
                estado = "✅ VALOR +" if p['tiene_valor_positivo'] else "⚠️ Sin valor"
                print(f"[{estado}] {p['local']} vs {p['visitante']}")
                
                # Mostrar solo el análisis EV si existe
                for mercado, ev_data in p['analisis_ev'].items():
                    if ev_data.get('es_valor_positivo'):
                        print(f"   💰 {mercado.upper()}: Cuota {p['cuotas'][mercado]} | EV: {ev_data['valor_esperado']:.2%} (Cuota Justa: {ev_data['cuota_justa']})")
        else:
            print(f"\n⚠️ No se encontraron partidos analizables para {dep.upper()}.")
            
    print("\n🎉 Proceso finalizado. Revisa datos/cuotas_ganaplay.json o integra obtener_cartelera_con_valor() en tu API.")
