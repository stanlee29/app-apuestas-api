# AppApuestas

Aplicación de consulta e investigación deportiva. El backend FastAPI obtiene eventos, mercados y cuotas de SportsGameOdds API v2. La aplicación Flutter se importa y construye desde FlutLab; el backend se despliega de forma independiente.

## Funcionalidad del backend

- Cartelera de fútbol, NBA, NFL y MLB, según las ligas disponibles en la cuenta del proveedor.
- Mercados y selecciones con precios por casa, cuota americana, conversión decimal, línea y hora de actualización.
- Selector de fecha exacta para hoy, mañana o pasado mañana en hora de El Salvador; la consulta anterior por rango sigue disponible para compatibilidad.
- Paginación por cursor de eventos hasta agotar resultados, con un límite configurable que se informa explícitamente cuando se alcanza.
- Filtro de eventos en vivo.
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

La cobertura gratuita se limita a las ligas enumeradas; no representa toda la cartelera mundial. La disponibilidad efectiva debe confirmarse con la cuenta del proveedor. Cada cuota conserva el nombre de la casa que la publica. La paginación de eventos usa nextCursor; por seguridad se limita a 10 páginas por solicitud de forma predeterminada (configurable mediante SPORTSGAMEODDS_MAX_EVENT_PAGES). Si se llega al límite, la respuesta y la interfaz advierten que el resultado podría estar incompleto.

**GanaPlay no es todavía una fuente conectada.** El backend actual consulta SportsGameOdds. La documentación pública localizada del feed Altenar describe un servicio B2B que requiere un importerId exclusivo del operador y autorización de IP (allowlist). Para una conexión directa hacen falta los datos oficiales de integración entregados por GanaPlay/Altenar; no se ha sustituido esa autorización con scraping de endpoints privados.

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
| \`GET /api/v1/events?deporte=nba&dias=2\` | Eventos, mercados y cuotas por rango |
| \`GET /api/v1/events/{event_id}/markets\` | Mercados completos de un evento |
| \`GET /cartelera/{deporte}?fecha=YYYY-MM-DD\` | Cartelera de una fecha exacta (hoy, mañana o pasado mañana) |
| \`GET /cartelera/{deporte}?dias=2\` | Consulta por rango, conservada por compatibilidad |
| \`GET /equipos/{deporte}\` | Equipos encontrados en históricos |
| \`GET /predecir\` | Predicción manual con históricos |
| \`POST /actualizar-datos\` | Actualizar los CSV de resultados históricos |

### Archivo histórico de investigación

El almacén Supabase contiene resultados históricos de fútbol y MLB, métricas xG de American Soccer Analysis y StatsBomb Open Data, identidades de equipos/eventos y resúmenes compactos de cuotas. Las métricas avanzadas conservan atribución; los valores que una fuente no publica permanecen vacíos.

Migraciones:
- `AppApuestas/sql/001_research_snapshots.sql`
- `AppApuestas/sql/002_historical_archive.sql`

Rutas principales:
- `GET /api/v1/research/archive/teams/{team_name}?before_date=YYYY-MM-DD&limit=5`
- `GET /api/v1/research/archive/events/{event_id}/markets?limit=50`
- `GET /api/v1/research/storage/status`
- `POST /api/v1/research/collector/daily` — recolector diario protegido por `X-App-Ingest-Token`; tope de 20 eventos por ejecución y reserva 500 objetos del límite mensual.
- `GET /api/v1/research/odds/history/{event_id}` — snapshots diarios de mercados por evento.
- `GET /api/v1/research/storage/history/{match_id}?provider=pitchapi`

La URL y la clave secreta de Supabase (`sb_secret_...`) se configuran solo en Render. La clave no debe llegar al frontend ni a Flutter. El backend también admite temporalmente la antigua `service_role` JWT. Los resúmenes de cuotas guardan apertura, cierre y rangos; no son un histórico tick a tick.

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

La aplicación consulta al abrir la cartelera o cuando el usuario pulsa actualizar. El recolector histórico de cuotas se ejecuta una vez al día desde Supabase Cron, almacena como máximo 20 eventos y consulta primero `/account/usage` para preservar una reserva de 500 objetos mensuales. No se programa sondeo automático en el nivel gratuito para proteger el límite de 2.500 objetos al mes. La caché del servidor evita repetir una consulta durante 10 minutos. Esto no es un recolector permanente 24/7. Un servicio gratuito puede suspenderse y su disco local no debe usarse como histórico persistente. Para almacenar capturas de cuotas y recopilar con la app cerrada se requiere base de datos y un proceso programado/worker con disponibilidad adecuada.

## Modelo estadístico

Las predicciones existentes son una primera aproximación a partir de CSV históricos. No se consideran validadas para uso real hasta comprobar cobertura de históricos, calibración fuera de muestra y métricas como Brier Score y Log Loss.
