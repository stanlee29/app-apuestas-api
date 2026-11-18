# EdgeBet API + Flutter PWA

Backend de EdgeBet para la app Flutter/FlutLab. La fuente prevista de eventos, mercados y cuotas es el feed B2B de Altenar habilitado para GanaPlay. No se consulta ESPN como sustituto de GanaPlay ni se construyen cuotas ficticias.

## Arquitectura

- AppApuestas/: API FastAPI, conector de lectura de Altenar, históricos y PWA.
- FlutterApp/: guía y punto de referencia de la app Flutter. El ZIP actualizado para importar en FlutLab se entrega por separado en la conversación.
- GET /api/v1/ganaplay/events: eventos prepartido y en vivo.
- GET /api/v1/ganaplay/events/{event_id}/markets: mercados y selecciones con sus precios.
- GET /api/v1/ganaplay/status: estado de configuración del feed.
- GET /health: estado del backend.

## Feed GanaPlay / Altenar

El feed Data Export descrito en documentación pública de Altenar está dirigido a operadores/licenciatarios B2B. El acceso se controla mediante whitelist de IP y un importerId asignado al operador durante la integración. No uses un importer ID de ejemplo, endpoints de staging ni credenciales de otra marca.

Antes de habilitarlo, solicita a GanaPlay/Altenar:
1. Endpoint de producción para el Data Feed de GanaPlay El Salvador.
2. importerId asignado a esa marca.
3. Autorización y whitelist de la IP pública del servicio EdgeBet.
4. Confirmación del uso permitido para consulta/analítica externa y de los límites de frecuencia.
5. Una respuesta JSON real de GetSports, GetEvents, GetLiveEvents y GetMarkets para mapear con precisión el esquema del operador.

Configura las variables del entorno de Render a partir de .env.example. No guardes credenciales en el repositorio ni dentro de Flutter.

## Actualización

La APK solicita eventos al abrir la cartelera y vuelve a consultarlos cada 60 segundos mientras la pantalla está abierta. Los mercados de cada partido se consultan al abrir el detalle y se actualizan cada 60 segundos mientras ese detalle permanece abierto. El backend aplica una caché corta configurable.

Esto todavía no constituye un recolector persistente 24/7. Para continuar recopilando cuando la APK está cerrada, hace falta un proceso programado/worker siempre activo y almacenamiento persistente. El filesystem efímero de un servicio web gratuito no debe usarse como histórico.

## Ejecutar localmente

\`\`\`bash
cd AppApuestas
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn api_servidor:app --reload
\`\`\`

Abrir http://127.0.0.1:8000 y http://127.0.0.1:8000/docs.

## Endpoints existentes

| Endpoint | Uso |
| --- | --- |
| GET /health | Estado del backend y configuración del feed |
| GET /api/v1/ganaplay/status | Estado del feed Altenar |
| GET /api/v1/ganaplay/sports | Catálogo de deportes del proveedor |
| GET /api/v1/ganaplay/events?deporte=futbol | Eventos prepartido y en vivo |
| GET /api/v1/ganaplay/events/{event_id}/markets | Mercados y selecciones del evento |
| GET /cartelera/{deporte} | Alias compatible con versiones anteriores de la APK |
| GET /equipos/{deporte} | Equipos en históricos |
| GET /predecir | Predicción estadística manual |

Deportes de la app: futbol, nba, nfl, mlb.

## Importante

La documentación Data Feed consultada describe eventos del día actual y mercados por evento; el periodo de datos y los mercados disponibles deben confirmarse con el feed de producción que Altenar asigne a GanaPlay. La respuesta de producción será necesaria para completar cualquier campo de mercado que cambie entre versiones.
