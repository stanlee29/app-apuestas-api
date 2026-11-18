"""
Compatibilidad histórica del módulo extractor_ganaplay.
La fuente de cartelera es exclusivamente el feed Altenar autorizado por GanaPlay.
No consulta ESPN, no deduce cuotas y no genera mercados sintéticos.
"""
from typing import Any

from altenar_feed import AltenarFeedClient


def obtener_cartelera_con_valor(deporte: str, dias: int = 0) -> dict[str, Any]:
    """
    Devuelve los eventos publicados por GanaPlay/Altenar.

    El Data Feed de exportación documentado devuelve eventos del día actual.
    El parámetro dias se conserva por compatibilidad con versiones anteriores,
    pero no se utiliza para simular una ventana que el endpoint no garantice.
    Los mercados y las selecciones se solicitan por evento mediante GetMarkets.
    """
    del dias
    result = AltenarFeedClient().get_events(deporte)
    cartelera = []

    for event in result.get("eventos", []):
        cartelera.append({
            "evento_id": event.get("evento_id"),
            "deporte": deporte,
            "liga": event.get("liga") or event.get("categoria") or "",
            "fecha_hora": event.get("fecha_hora") or "",
            "local": event.get("local") or event.get("nombre_evento") or "",
            "visitante": event.get("visitante") or "",
            "estado_evento": event.get("estado_evento"),
            "fuente_eventos": "GanaPlay / Altenar",
            "mercados": [],
            "mercados_cargados": False,
            "probabilidades_modelo": {
                "local": None,
                "empate": None,
                "visitante": None,
            },
            "analisis_ev": {},
            "modelo_disponible": False,
            "tiene_valor_positivo": False,
        })

    return {
        "deporte": deporte,
        "rango_fechas": "",
        "mensaje": "Eventos obtenidos del feed GanaPlay/Altenar. Consulta GetMarkets por evento para cargar cuotas y mercados.",
        "total_partidos": len(cartelera),
        "total_con_cuotas": 0,
        "cartelera": cartelera,
    }
