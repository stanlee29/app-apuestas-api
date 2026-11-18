# AppApuestas

Aplicación de consulta e investigación deportiva. El backend FastAPI obtiene eventos, mercados y cuotas de SportsGameOdds API v2. La aplicación Flutter se importa y construye desde FlutLab; el backend se despliega de forma independiente.

## Funcionalidad del backend

- Cartelera de fútbol, NBA, NFL y MLB, según las ligas disponibles en la cuenta del proveedor.
- Mercados y selecciones con precios por casa, cuota americana, conversión decimal, línea y hora de actualización.
- Filtro de eventos en vivo y por rango de días.
- Consulta de probabilidades a partir de los históricos locales cuando hay equipos compatibles.
- Cálculo de EV únicamente cuando existe una probabilidad del modelo y una cuota real.
- Caché del servidor alineada por defecto con la frecuencia de 10 minutos anunciada en el plan gratuito.

## Fuente de datos y plan gratuito

El conector utiliza la API v2 de SportsGameOdds:

- Endpoint de eventos: \`GET https://api.sportsgameodds.com/v2/events\`.
- Autenticación privada mediante la cabecera \`X-Api-Key\`.
- Los objetos de evento incluyen los mercados y las cuotas disponibles por casa.
- El plan Amateur publicado incluye 2.500 objetos/mes, 10 solicitudes/minuto, frecuencia de actualización de 10 minutos, 8 ligas y 9 casas.
- Ligas publicadas en ese nivel: NFL, NBA, MLB, NHL, College Football, College Basketball, Champions League y MLS.
- La página de alta indica que se solicita tarjeta al registrarse, pero que el plan gratuito no se cobra salvo que se actualice.

La cobertura no equivale a GanaPlay ni a todas las ligas de fútbol. La disponibilidad efectiva debe confirmarse con la cuenta del proveedor. Nunca se etiqueta una cuota de otra casa como cuota de GanaPlay.

Referencias oficiales:
- https://sportsgameodds.com/pricing
- https://sportsgameodds.com/docs/basics/setup
- https://sportsgameodds.com/docs/endpoints/getEvents
- https://sportsgameodds.com/docs/basics/quickstart

## Configuración

Añade \`SPORTSGAMEODDS_API_KEY\` a las variables privadas de Render. No guardes la clave real en GitHub, dentro de Flutter ni en archivos públicos. Las demás variables opcionales se documentan en \`AppApuestas/.env.example\`.

## Endpoints

| Ruta | Función |
| --- | --- |
| \`GET /health\` | Estado del backend y configuración del proveedor |
| \`GET /api/v1/source/status\` | Estado, ligas y límites publicados |
| \`GET /api/v1/sports\` | Deportes y ligas configuradas |
| \`GET /api/v1/events?deporte=nba&dias=2\` | Eventos, mercados y cuotas |
| \`GET /api/v1/events/{event_id}/markets\` | Mercados completos de un evento |
| \`GET /cartelera/{deporte}?dias=2\` | Respuesta compatible con la aplicación Flutter |
| \`GET /equipos/{deporte}\` | Equipos encontrados en históricos |
| \`GET /predecir\` | Predicción manual con históricos |
| \`POST /actualizar-datos\` | Actualizar los CSV de resultados históricos |

Deportes admitidos: \`futbol\`, \`nba\`, \`nfl\`, \`mlb\`.

## Ejecutar localmente

\`\`\`bash
cd AppApuestas
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api_servidor:app --reload
\`\`\`

Abrir http://127.0.0.1:8000 y http://127.0.0.1:8000/docs.

## Límites operativos

La aplicación móvil puede consultar el backend mientras está abierta. La caché reduce solicitudes repetidas, pero esto no es un recolector permanente 24/7. Un servicio gratuito puede suspenderse y su disco local no debe usarse como histórico persistente. Para almacenar capturas de cuotas y recopilar con la app cerrada se requiere base de datos y un proceso programado/worker con disponibilidad adecuada.

## Modelo estadístico

Las predicciones existentes son una primera aproximación a partir de CSV históricos. No se consideran validadas para uso real hasta comprobar cobertura de históricos, calibración fuera de muestra y métricas como Brier Score y Log Loss.
