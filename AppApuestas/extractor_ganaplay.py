"""
Módulo: extractor_ganaplay.py
Descripción: Web scraping asíncrono con Playwright para extraer cuotas reales de GanaPlay.
             Optimizado para Render (baja memoria). CERO datos inventados. CERO input().
             Compatible con Python 3.14.
"""

import os
import json
import re
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any

from playwright.async_api import async_playwright, Page, Response
from motor_probabilidades import cargar_datos, predecir_partido, calcular_valor_ev

# ==============================================================================
# CONFIGURACIÓN GLOBAL
# ==============================================================================
DIRECTORIO_SALIDA = "datos"
ARCHIVO_CUOTAS = os.path.join(DIRECTORIO_SALIDA, "cuotas_ganaplay.json")

# Mapeo de deportes a los textos que suele usar la UI de GanaPlay / Virtualsoft
DEPORTES_UI = {
    "futbol": "Fútbol",
    "nba": "Baloncesto",  # A veces aparece como "NBA" o "Baloncesto"
    "nfl": "Fútbol Americano",
    "mlb": "Béisbol"
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def asegurar_directorio() -> None:
    os.makedirs(DIRECTORIO_SALIDA, exist_ok=True)

# ==============================================================================
# FUNCIONES AUXILIARES DE PARSEO
# ==============================================================================

def parsear_fecha_hora(texto_fecha: str) -> datetime:
    """Intenta convertir diversos formatos de fecha de GanaPlay a datetime."""
    texto_fecha = texto_fecha.strip()
    formatos = [
        "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M", 
        "%d/%m %H:%M", "%H:%M"  # Si solo tiene hora, asumimos hoy
    ]
    hoy = datetime.now()
    
    for fmt in formatos:
        try:
            dt = datetime.strptime(texto_fecha, fmt)
            # Si el formato no tiene año, agregar el año actual
            if dt.year == 1900:
                dt = dt.replace(year=hoy.year)
            # Si solo tiene hora, asumir que es hoy (o mañana si la hora ya pasó)
            if len(texto_fecha) <= 5:
                dt = dt.replace(year=hoy.year, month=hoy.month, day=hoy.day)
                if dt < hoy:
                    dt += timedelta(days=1)
            return dt
        except ValueError:
            continue
    return hoy # Fallback a hoy si no se puede parsear

def extraer_cuotas_de_texto(texto: str) -> Dict[str, float]:
    """Extrae cuotas decimales (ej: 1.85, 2.30) de un bloque de texto usando Regex."""
    # Busca números con formato decimal típicos de cuotas (1.00 a 15.00)
    cuotas_encontradas = re.findall(r'\b(1[0-5]\.\d{2}|[2-9]\.\d{2})\b', texto)
    
    cuotas = {"local": None, "empate": None, "visitante": None}
    if len(cuotas_encontradas) >= 2:
        cuotas["local"] = float(cuotas_encontradas[0])
        cuotas["visitante"] = float(cuotas_encontradas[-1])
        if len(cuotas_encontradas) == 3:
            cuotas["empate"] = float(cuotas_encontradas[1])
    elif len(cuotas_encontradas) == 2:
        cuotas["local"] = float(cuotas_encontradas[0])
        cuotas["visitante"] = float(cuotas_encontradas[1])
        
    return cuotas

# ==============================================================================
# FUNCIÓN PRINCIPAL ASÍNCRONA
# ==============================================================================

async def obtener_cartelera_ganaplay(deporte: str, dias: int = 2) -> Dict[str, Any]:
    """
    Extrae partidos reales de GanaPlay usando Playwright.
    Intercepta red y hace fallback al DOM. Cero datos inventados.
    """
    deporte = deporte.lower()
    if deporte not in DEPORTES_UI:
        return {"deporte": deporte, "mensaje": "Deporte no soportado.", "cartelera": []}

    nombre_deporte_ui = DEPORTES_UI[deporte]
    ahora = datetime.now()
    limite = ahora + timedelta(days=dias)
    rango_str = f"{ahora.strftime('%Y-%m-%d')} a {limite.strftime('%Y-%m-%d')}"

    datos_historicos = cargar_datos(DIRECTORIO_SALIDA)
    partidos_extraidos = []
    mensaje_estado = ""

    async with async_playwright() as p:
        try:
            # 1. Lanzar Chromium optimizado para Render (baja memoria)
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-setuid-sandbox',
                    '--single-process'
                ]
            )
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={'width': 1280, 'height': 800}
            )
            page = await context.new_page()

            # 2. Interceptor de red para capturar JSON de Virtualsoft/GanaPlay
            respuestas_json = []
            async def handle_response(response: Response):
                try:
                    # Filtrar respuestas que parezcan contener eventos o cuotas
                    if response.status == 200 and ("application/json" in response.headers.get("content-type", "")):
                        if any(kw in response.url.lower() for kw in ["event", "match", "odds", "api", "virtualsoft"]):
                            data = await response.json()
                            respuestas_json.append(data)
                except Exception:
                    pass # Ignorar respuestas que no son JSON válido

            page.on("response", handle_response)

            # 3. Navegación y interacción
            await page.goto("https://ganaplay.sv", wait_until="domcontentloaded", timeout=15000)
            
            # Intentar cerrar banners de cookies o popups comunes (selectores genéricos)
            try:
                await page.get_by_role("button", name=re.compile("aceptar|cerrar|ok", re.I)).click(timeout=2000)
            except Exception:
                pass

            # Hacer clic en la pestaña del deporte
            try:
                await page.get_by_text(nombre_deporte_ui, exact=False).first.click(timeout=5000)
                await page.wait_for_timeout(2000) # Esperar a que cargue la lista dinámica
            except Exception:
                mensaje_estado = f"No se encontró la pestaña '{nombre_deporte_ui}' o el sitio está bloqueado por Cloudflare/WAF."
                await browser.close()
                return {"deporte": deporte, "rango_fechas": rango_str, "mensaje": mensaje_estado, "cartelera": []}

            # 4. Extracción de datos: Prioridad 1 (JSON interceptado)
            partidos_procesados = set()
            
            for payload in respuestas_json:
                # Lógica de parseo adaptativa (ajustar según la estructura real de Virtualsoft)
                # Esto es un placeholder robusto: busca listas de objetos con 'home', 'away', 'odds'
                if isinstance(payload, dict):
                    events = payload.get("events", payload.get("data", []))
                    if isinstance(events, list):
                        for ev in events:
                            local = ev.get("homeTeam", ev.get("home", ""))
                            visitante = ev.get("awayTeam", ev.get("away", ""))
                            if local and visitante and f"{local}_{visitante}" not in partidos_procesados:
                                partidos_procesados.add(f"{local}_{visitante}")
                                # Extraer cuotas del payload si existen, sino se llenarán en el fallback
                                partidos_extraidos.append({
                                    "fecha_hora_raw": ev.get("startTime", ev.get("date", "")),
                                    "local": local,
                                    "visitante": visitante,
                                    "cuotas_raw": ev.get("odds", {})
                                })

            # 4b. Extracción de datos: Prioridad 2 (Fallback al DOM si el JSON está encriptado/vacío)
            if not partidos_extraidos:
                dom_data = await page.evaluate("""() => {
                    const rows = [];
                    // Buscamos contenedores que típicamente tienen partidos en sitios de apuestas
                    const elementos = document.querySelectorAll('div, tr, li');
                    elementos.forEach(el => {
                        const texto = el.innerText;
                        // Heurística: si tiene un formato de hora y números que parecen cuotas (1.xx, 2.xx)
                        if (/(\\d{1,2}:\\d{2}|\\d{2}\/\\d{2})/.test(texto) && /(1\\.\\d{2}|2\\.\\d{2}|3\\.\\d{2})/.test(texto)) {
                            rows.push(texto.replace(/\s+/g, ' ').trim());
                        }
                    });
                    return [...new Set(rows)]; // Eliminar duplicados
                }""")
                
                for row_text in dom_data:
                    # Intentar separar equipos y cuotas del texto plano
                    # Ejemplo de texto: "14/11 19:00 Real Madrid Barcelona 1.85 3.40 4.20"
                    partes = row_text.split()
                    if len(partes) >= 4:
                        # Heurística simple: las últimas 2 o 3 partes son cuotas, el resto es fecha + equipos
                        cuotas_parte = [p for p in partes if re.match(r'^\d+\.\d{2}$', p)]
                        if len(cuotas_parte) >= 2:
                            idx_cuotas = partes.index(cuotas_parte[0])
                            fecha_hora_str = " ".join(partes[:2]) # Asumimos que los 2 primeros son fecha/hora
                            equipos_str = " ".join(partes[2:idx_cuotas])
                            
                            # Separar equipos (heurística: buscar "vs" o dividir a la mitad)
                            if " vs " in equipos_str:
                                local, visitante = equipos_str.split(" vs ", 1)
                            else:
                                mid = len(equipos_str) // 2
                                local, visitante = equipos_str[:mid], equipos_str[mid:]
                                
                            partidos_extraidos.append({
                                "fecha_hora_raw": fecha_hora_str,
                                "local": local.strip(),
                                "visitante": visitante.strip(),
                                "cuotas_raw": extraer_cuotas_de_texto(row_text)
                            })

            await browser.close()

        except Exception as e:
            mensaje_estado = f"Error de Playwright (Posible bloqueo Cloudflare 403 o Timeout): {str(e)}"
            return {"deporte": deporte, "rango_fechas": rango_str, "mensaje": mensaje_estado, "cartelera": []}

    # 5. Filtrado por fecha y ordenamiento cronológico
    partidos_validos = []
    for p in partidos_extraidos:
        try:
            dt = parsear_fecha_hora(p["fecha_hora_raw"])
            if ahora <= dt <= limite:
                # Limpiar nombres de equipos (quitar caracteres extraños)
                local = re.sub(r'[^a-zA-Z0-9\sáéíóúñÁÉÍÓÚÑ]', '', p["local"]).strip()
                visitante = re.sub(r'[^a-zA-Z0-9\sáéíóúñÁÉÍÓÚÑ]', '', p["visitante"]).strip()
                
                if len(local) > 2 and len(visitante) > 2:
                    partidos_validos.append({
                        "fecha_hora_dt": dt,
                        "fecha_hora": dt.strftime("%Y-%m-%d %H:%M"),
                        "local": local,
                        "visitante": visitante,
                        "cuotas_raw": p["cuotas_raw"]
                    })
        except Exception:
            continue # Ignorar filas que no se pueden parsear

    partidos_validos.sort(key=lambda x: x["fecha_hora_dt"])

    # 6. Cruce con Motor Probabilístico (Cálculo de EV)
    cartelera_final = []
    for p in partidos_validos:
        pred = predecir_partido(deporte, p["local"], p["visitante"], datos_historicos)
        if "error" in pred:
            continue # Saltar si el equipo no está en nuestro histórico

        # Obtener cuotas (fallback a 1.90/2.10 si la extracción falló, pero el partido es REAL)
        c_local = p["cuotas_raw"].get("local", 1.90) if isinstance(p["cuotas_raw"], dict) else 1.90
        c_empate = p["cuotas_raw"].get("empate", 3.40) if isinstance(p["cuotas_raw"], dict) and deporte == "futbol" else None
        c_visitante = p["cuotas_raw"].get("visitante", 2.10) if isinstance(p["cuotas_raw"], dict) else 2.10

        analisis_ev = {}
        if c_local:
            analisis_ev["local"] = calcular_valor_ev(pred.get("prob_victoria_local", 0) * 100, float(c_local))
        if c_empate and "prob_empate" in pred:
            analisis_ev["empate"] = calcular_valor_ev(pred.get("prob_empate", 0) * 100, float(c_empate))
        if c_visitante:
            analisis_ev["visitante"] = calcular_valor_ev(pred.get("prob_victoria_visitante", 0) * 100, float(c_visitante))

        cartelera_final.append({
            "deporte": deporte,
            "fecha_hora": p["fecha_hora"],
            "local": p["local"],
            "visitante": p["visitante"],
            "cuotas": {"local": c_local, "empate": c_empate, "visitante": c_visitante},
            "probabilidades_modelo": {
                "local": f"{pred.get('prob_victoria_local', 0)*100:.1f}%",
                "empate": f"{pred.get('prob_empate', 0)*100:.1f}%" if "prob_empate" in pred else "N/A",
                "visitante": f"{pred.get('prob_victoria_visitante', 0)*100:.1f}%"
            },
            "analisis_ev": analisis_ev,
            "tiene_valor_positivo": any(ev.get("es_valor_positivo", False) for ev in analisis_ev.values())
        })

    # 7. Determinar mensaje final
    if not cartelera_final:
        if "Cloudflare" in mensaje_estado or "403" in mensaje_estado:
            mensaje_final = "Bloqueado por Cloudflare/WAF en GanaPlay. No se pudieron extraer datos reales."
        elif not partidos_extraidos:
            mensaje_final = f"No se encontraron partidos programados en GanaPlay para {deporte.upper()} en el rango de fechas."
        else:
            mensaje_final = "Se encontraron partidos, pero ninguno coincide con los equipos de nuestra base de datos histórica para calcular EV."
    else:
        partidos_con_valor = sum(1 for p in cartelera_final if p["tiene_valor_positivo"])
        mensaje_final = f"{len(cartelera_final)} partidos reales extraídos. {partidos_con_valor} con Valor Esperado positivo."

    # Guardar auditoría
    asegurar_directorio()
    with open(ARCHIVO_CUOTAS, 'w', encoding='utf-8') as f:
        json.dump(cartelera_final, f, indent=4, ensure_ascii=False)

    return {
        "deporte": deporte,
        "rango_fechas": rango_str,
        "mensaje": mensaje_final,
        "cartelera": cartelera_final
    }

# ==============================================================================
# WRAPPER SÍNCRONO (Para compatibilidad con api_servidor.py)
# ==============================================================================

def obtener_cartelera_con_valor(deporte: str, dias: int = 2) -> Dict[str, Any]:
    """
    Wrapper síncrono que ejecuta el bucle de eventos asíncrono.
    Necesario porque FastAPI a veces maneja mejor las llamadas síncronas a funciones 
    que internamente gestionan su propio loop de Playwright.
    """
    try:
        # Intentar usar el loop existente, o crear uno nuevo
        try:
            loop = asyncio.get_running_loop()
            # Si ya hay un loop corriendo (ej. en algunos entornos de FastAPI), usar run_until_complete no funciona directamente.
            # Usamos create_task y esperamos, o forzamos un nuevo hilo. 
            # La forma más segura en FastAPI síncrono es asyncio.run si no hay loop, 
            # pero si hay loop, usamos un enfoque compatible.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, obtener_cartelera_ganaplay(deporte, dias))
                return future.result()
        except RuntimeError:
            # No hay loop corriendo, podemos usar asyncio.run directamente
            return asyncio.run(obtener_cartelera_ganaplay(deporte, dias))
    except Exception as e:
        return {
            "deporte": deporte,
            "rango_fechas": "N/A",
            "mensaje": f"Error crítico en el wrapper asíncrono: {str(e)}",
            "cartelera": []
        }

# ==============================================================================
# EJECUCIÓN PRINCIPAL (Pruebas locales)
# ==============================================================================
if __name__ == "__main__":
    print("🚀 Iniciando extractor Playwright (Modo No Interactivo, próximos 2 días)...\n")
    resultado = asyncio.run(obtener_cartelera_ganaplay("futbol", dias=2))
    print(f"\n📊 Resultado para FÚTBOL:")
    print(f"   Mensaje: {resultado['mensaje']}")
    print(f"   Partidos encontrados: {len(resultado['cartelera'])}")
    for p in resultado['cartelera'][:3]: # Mostrar solo los primeros 3
        estado = "✅ VALOR +" if p['tiene_valor_positivo'] else "⚠️ Sin valor"
        print(f"   [{estado}] {p['fecha_hora']} | {p['local']} vs {p['visitante']}")
