# AppApuestas — Backend

API deportiva con FastAPI. La cartelera y los mercados se obtienen de SportsGameOdds API v2.

## Configuración de la fuente

1. Crear cuenta en https://sportsgameodds.com/pricing y seleccionar Amateur.
2. Copiar la clave recibida por correo.
3. Agregarla a las variables privadas del servicio Render como \`SPORTSGAMEODDS_API_KEY\`.
4. Verificar \`/health\` y \`/api/v1/source/status\`.
5. Probar \`/api/v1/events?deporte=nba&dias=2\` y abrir un evento mediante \`/api/v1/events/{event_id}/markets\`.

El plan gratuito publicado tiene 2.500 objetos al mes, 10 solicitudes por minuto y actualización cada 10 minutos. El registro solicita tarjeta, pero el proveedor declara que el plan Amateur no genera cargos mientras no se actualice.

La cobertura gratuita incluye ocho ligas: NFL, NBA, MLB, NHL, NCAA Football, NCAA Basketball, Champions League y MLS. No equivale a toda la cartelera mundial; la disponibilidad depende de la liga y el evento.

## Variables

Consulta \`.env.example\`. No guardes claves reales en este repositorio.

## Ejecutar

\`\`\`bash
pip install -r requirements.txt
uvicorn api_servidor:app --reload
\`\`\`

## Research Engine actual

La vista principal de Research usa PitchAPI, no el archivo histórico de StatsBomb. En la aplicación se selecciona liga, temporada y partido. Los partidos en vivo y programados se ordenan antes que los finalizados.

El análisis de un encuentro puede incluir:
- Alineaciones y suplentes, identificando explícitamente si el once está confirmado o es provisional.
- Estadísticas individuales por futbolista: minutos, rating, goles, asistencias, xG, xA y remates cuando estén disponibles.
- Estadísticas de equipo, tiros con xG, mapas de actividad de equipos y jugadores, métricas avanzadas y H2H según la cobertura del partido.

No se inventan datos que el proveedor no entregue. En partidos futuros, las estadísticas de rendimiento pueden estar vacías hasta que el partido se juegue; las alineaciones previas al inicio pueden ser estimaciones. StatsBomb permanece disponible en un bloque separado como archivo histórico y no se mezcla con la plantilla vigente.

## Investigación avanzada de fútbol (PitchAPI)

AppApuestas puede complementar las cuotas de SportsGameOdds con PitchAPI para obtener catálogo de ligas, fixtures, historial desde 2021 y, cuando el partido tenga cobertura, remates con xG, coordenadas, estadísticas de equipos y jugadores, H2H, mapas de calor, eventos, momentum y analítica avanzada.

1. Crear una clave gratuita en https://pitchapi.dev/.
2. En Render, abrir el servicio `app-apuestas-api` → Environment.
3. Agregar la variable privada `PITCHAPI_API_KEY` con la clave de PitchAPI.
4. Guardar los cambios y esperar el despliegue.
5. Comprobar `/api/v1/research/status`.
6. Consultar `/api/v1/research/football/leagues` para cargar el catálogo.
7. Consultar `/api/v1/research/football/date/2026-11-18?status=all` para partidos de una fecha.
8. Consultar `/api/v1/research/football/matches/{match_id}/analysis` para el análisis avanzado.

La clave solo se almacena en Render. Nunca debe añadirse a Flutter, a archivos del repositorio ni compartirse en mensajes.

El catálogo documentado de PitchAPI anuncia 77 ligas y cobertura histórica desde 2021. No todos los partidos tienen necesariamente xG, heatmaps o analítica avanzada; la respuesta informa qué bloques están disponibles. PitchAPI es una fuente de fútbol, no sustituye a las fuentes de cuotas ni cubre por sí sola los demás deportes.

Las métricas xG de PitchAPI conservan su propia metodología. No se deben sumar o mezclar con xG de otros proveedores como si fueran una misma métrica.

## Catálogo y analítica histórica gratuita

### Fuente auxiliar TheSportsDB (API gratuita)

Se incorpora la API v1 pública de TheSportsDB con la clave compartida documentada `123`; no exige una clave personal. Se usa como fuente auxiliar para consultar cartelera por fecha, estadísticas de partido, alineaciones, timeline y una muestra de fichas de jugadores activos.

Rutas:
- `GET /api/v1/research/thesportsdb/status`
- `GET /api/v1/research/thesportsdb/events?fecha=2026-11-22`
- `GET /api/v1/research/thesportsdb/events/{event_id}/analysis?home_team_id=133604&away_team_id=133605`

La documentación publica un límite general de 30 solicitudes por minuto y límites de resultados por endpoint. El cliente aplica caché, serializa las peticiones y limita la consulta de jugadores a los primeros 10 registros activos por club. La cartelera puede estar incompleta; por eso TheSportsDB no reemplaza SportsGameOdds ni PitchAPI.

### StatsBomb Open Data (sin clave)

La API expone:
- `GET /api/v1/research/statsbomb/competitions`: competiciones y temporadas abiertas publicadas.
- `GET /api/v1/research/statsbomb/competitions/{competition_id}/seasons/{season_id}/matches`: partidos de esa temporada.
- `GET /api/v1/research/statsbomb/matches/{match_id}/analysis?competition_id=...&season_id=...`: eventos, remates, xG de cada disparo, coordenadas, mapa de actividad, corners, faltas, tarjetas y H2H de la competición/temporada.
- `GET /api/v1/research/statsbomb/predict?competition_id=...&season_id=...&local=...&visitante=...`: modelo experimental de Poisson con corrección Dixon-Coles a partir de marcadores históricos.

StatsBomb Open Data no es un feed en vivo y solo publica determinadas competiciones y temporadas. Los eventos y resultados deben atribuirse a StatsBomb en los análisis publicados. Los mapas se construyen con coordenadas de eventos registrados, no con tracking continuo de jugadores.

### PitchAPI (clave gratuita)

Agregar `PITCHAPI_API_KEY` como variable privada del servicio Render. El proveedor documenta 77 ligas y acceso gratuito a su catálogo e historial desde 2021. La API ofrece fixtures, remates con xG, estadísticas de equipos/jugadores, H2H, heatmaps, alineaciones, momentum y analítica avanzada cuando está disponible.

Endpoints:
- `GET /api/v1/research/status`
- `GET /api/v1/research/football/leagues`
- `GET /api/v1/research/football/date/{YYYY-MM-DD}?status=all`
- `GET /api/v1/research/football/leagues/{league_id}/matches`
- `GET /api/v1/research/football/matches/{match_id}/analysis`
- `GET /api/v1/research/football/matches/{match_id}/live`

PitchAPI es una fuente de fútbol, no proporciona por sí sola las cuotas de las casas. Su xG conserva la metodología del proveedor y no debe mezclarse como idéntico a xG de StatsBomb.

### Modelo experimental

El primer modelo utiliza marcadores finalizados de una temporada StatsBomb:
- Tasas de goles locales y visitantes ponderadas por recencia (vida media inicial de 180 días).
- Ajuste de fuerza ofensiva/defensiva de local y visitante con regularización hacia el promedio de liga.
- Cuando existen al menos tres partidos recientes con eventos xG para cada condición, combina xG reciente de StatsBomb (65%) con las tasas de goles reales (35%). Si la cobertura no alcanza ese mínimo, utiliza el respaldo basado solo en marcadores.
- Distribución Poisson con corrección Dixon-Coles para marcadores de baja puntuación.
- Salidas: 1X2, ambos marcan, líneas de goles 0.5 a 4.5 y ocho marcadores más probables.

El modelo de goles no incorpora todavía lesiones ni alineaciones. Los mercados de remates, tiros a puerta, córners, faltas y tarjetas se calculan por separado en `/api/v1/research/statsbomb/markets-predict`; son estimaciones experimentales y aún no tienen backtest propio fuera de muestra. El parámetro rho es inicial y no está calibrado por competición; el modelo es exploratorio. La predicción de un partido exige `fecha_partido` y excluye todos los resultados de ese día y posteriores para evitar fuga temporal.

### Backtest cronológico
- `GET /api/v1/research/statsbomb/backtest?competition_id=...&season_id=...&min_train=30`
- Para cada partido evaluado, el entrenamiento utiliza únicamente resultados de fechas anteriores al día objetivo.
- Reporta Brier multiclase, Log Loss, exactitud, calibración por rangos de confianza y predicciones recientes.
- El backtest se limita a la competición/temporada seleccionada. Muestras pequeñas se etiquetan como exploratorias; no demuestra rentabilidad ni generalización a otras ligas.

## Mejoras de visualización táctica e historial

La vista de Research incluye mapas de remates, xG acumulado, mapas de actividad, red de pases, momentum, cronología del encuentro, métricas avanzadas de equipo/jugador y forma reciente. Cada bloque depende de la disponibilidad del dato del proveedor. El mapa de actividad registra eventos con coordenadas; no es tracking GPS continuo. La forma reciente usa los cinco resultados previos dentro de la temporada seleccionada y no considera partidos futuros.

La revisión comparativa de repositorios, herramientas y licencias se encuentra en [ANALISIS_HERRAMIENTAS.md](ANALISIS_HERRAMIENTAS.md). Incluye recomendaciones para fútbol, NBA, NFL y MLB y una lista de fuentes que no conviene automatizar sin permiso.

## Investigación NBA (incluida en producción)

La aplicación incluye un panel NBA separado del análisis de fútbol. Usa `nba_api`, ya incluido en los requisitos obligatorios, y consulta NBA.com Stats sin API key. Las consultas son bajo demanda y se cachean durante cinco minutos.

Endpoints:
- `GET /api/v1/research/nba/status`: disponibilidad del conector.
- `GET /api/v1/research/nba/scoreboard?fecha=YYYY-MM-DD`: cartelera, marcadores y líderes.
- `GET /api/v1/research/nba/teams`: catálogo de franquicias actuales.
- `GET /api/v1/research/nba/teams/{team_id}/roster?season=YYYY-YY`: plantilla de la temporada seleccionada.
- `GET /api/v1/research/nba/games/{game_id}/shots?season=YYYY-YY&team_id=0&player_id=0`: tiros con coordenadas, distancia, periodo y resultado.
- `GET /api/v1/research/nba/logs?season=YYYY-YY&entity=T|P`: game logs por equipo o jugador.
- `GET /api/v1/research/nba/games/{game_id}/boxscore`: estadísticas tradicionales, avanzadas y tracking por jugador/equipo cuando NBA.com las publica.
- `GET /api/v1/research/nba/games/{game_id}/play-by-play`: cronología completa de acciones.
- `GET /api/v1/research/nba/season-stats?season=YYYY-YY&entity=player|team&measure_type=Base|Advanced`: métricas de temporada, por partido o totales.

El panel permite seleccionar el partido, filtrar el mapa por local/visitante o ID de jugador y consultar roster e historial. Si no se especifica temporada, se calcula la temporada NBA vigente. Las coordenadas LOC_X/LOC_Y son coordenadas nativas de tiros NBA y nunca se mezclan con el campo de fútbol. NBA.com puede limitar peticiones o cambiar endpoints; un fallo de origen se informa como error del proveedor, no se completa con datos inventados.

## Investigación NFL (conector opcional)

Instalar `requirements-optional.txt` en un entorno destinado a NFL para habilitar `nflreadpy`. No se instala durante el despliegue base de Render.

Endpoints:
- `GET /api/v1/research/nfl/status`
- `GET /api/v1/research/nfl/schedule?season=2026&week=10`
- `GET /api/v1/research/nfl/games/{game_id}/pbp?season=2026&limit=1500`
- `GET /api/v1/research/nfl/rosters?season=2026&week=10`
- `GET /api/v1/research/nfl/injuries?season=2026`
- `GET /api/v1/research/nfl/depth-charts?season=2026`
- `GET /api/v1/research/nfl/statistics?season=2026&entity=player&summary_level=week`
- `GET /api/v1/research/nfl/snap-counts?season=2026`
- `GET /api/v1/research/nfl/nextgen-stats?season=2026&stat_type=passing`
- `GET /api/v1/research/nfl/pfr-advanced?season=2026&stat_type=pass&summary_level=week`

El PBP requiere el game_id y limita el número de jugadas devueltas. La cobertura de lesiones, depth charts, snap counts y Next Gen Stats depende de las tablas publicadas en nflverse. El paquete se declara experimental. La mayoría de los datos son CC BY 4.0; FTN charting es CC BY-SA 4.0. Verifica la licencia del dataset concreto antes de redistribuirlo.

## Investigación MLB / Statcast (conector opcional)

Instalar `requirements-optional.txt` en el entorno MLB para habilitar `pybaseball`.

Endpoints:
- `GET /api/v1/research/mlb/status`
- `GET /api/v1/research/mlb/statcast?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
- Filtros opcionales: `batter_id` o `pitcher_id` (uno por consulta).
- La ventana está limitada a tres días por solicitud y a 5.000 registros de respuesta.

Statcast puede incluir tipo de lanzamiento, velocidad, spin, localización, velocidad de salida, ángulo de bateo y expected statistics cuando se publican. pybaseball es un scraper de terceros; la licencia MIT del código no concede automáticamente derechos sobre Baseball Savant, FanGraphs o Baseball Reference. No automatizar ni redistribuir hasta revisar sus condiciones aplicables.

## Historial abierto de resultados de fútbol (opcional)

Se añade un adaptador para el parquet `schochastics/football-data`, publicado bajo ODC-BY. El repositorio anuncia 1.237.935 partidos de 207 ligas domésticas y 20 torneos internacionales entre 1888 y 2023. Contiene marcadores y nombres/identificadores de clubes, pero no xG, remates ni eventos.

Para habilitarlo:
1. Instala `duckdb` desde `requirements-optional.txt`.
2. Ejecuta desde `AppApuestas`: `python scripts/download_open_football_results.py`.
3. En Render, asigna `FOOTBALL_OPEN_DATA_PATH` a una ubicación persistente donde exista `games.parquet`. En el plan gratuito sin disco persistente, no actives esta fuente en producción.
4. Consulta `GET /api/v1/research/football/open-data/status` y `GET /api/v1/research/football/open-data/team-history?team_name=Arsenal&limit=10`.
5. Usa `team_ident` cuando el resultado indique varias identidades con el mismo nombre.

El endpoint aplica una fecha de corte estricta anterior al partido objetivo y avisa que la identidad de equipos puede variar en periodos históricos. La atribución ODC-BY se incluye en las respuestas.

## Historial persistente opcional en Supabase

La aplicación incluye un adaptador REST que guarda snapshots diarios de análisis por proveedor, partido y tipo. El almacenamiento está desactivado hasta configurar una base Supabase que se asigne expresamente a AppApuestas.

1. En el proyecto Supabase elegido para AppApuestas, ejecuta `sql/001_research_snapshots.sql`.
2. En Render agrega `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` y, opcionalmente, `SUPABASE_RESEARCH_TABLE`.
3. Nunca pongas la service-role key en Flutter, HTML, JavaScript o GitHub.
4. Comprueba `GET /api/v1/research/storage/status`.
5. Los análisis de PitchAPI guardan un snapshot diario al consultar el partido. Para consultar el historial usa `GET /api/v1/research/storage/history/{match_id}?provider=pitchapi`.

No se seleccionó ni modificó ninguna base Supabase existente. Hay que elegir explícitamente la base de AppApuestas antes de activar las variables. El adaptador no rompe la respuesta de análisis si el storage no está configurado o falla temporalmente.

## Seguridad de operaciones administrativas

`POST /actualizar-datos` queda desactivado si no existe `ADMIN_API_KEY`. Para habilitarlo, crea una clave larga aleatoria en Render y envíala en el encabezado `X-Admin-Key`. No configures esa clave en el cliente web ni en la app móvil.

## Paquetes de investigación offline

`requirements-optional.txt` contiene `nflreadpy`, `pybaseball`, `mplsoccer`, `kloppy`, `socceraction`, `pyarrow` y `duckdb`. No se instalan en el servidor principal automáticamente: mplsoccer/kloppy/socceraction se reservan para informes y normalización offline; el cliente de producción sigue usando datos de proveedores verificables y la UI propia.

### Versión

API backend 1.2.0 o posterior.
