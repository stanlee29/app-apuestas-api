# Evaluación e integración de herramientas para AppApuestas

**Revisión:** 23 de noviembre de 2026  
**Repositorio:** https://github.com/stanlee29/app-apuestas-api

## Estado ejecutivo

AppApuestas ya integra fuentes distintas por deporte. La regla es no mezclar metodologías ni fabricar estadísticas que el proveedor no publica. Cada bloque debe mostrar fuente, temporada, fecha de consulta y cobertura. Los conectores con scraping externo se mantienen opcionales y sujetos a los términos del proveedor.

| Deporte / función | Fuente principal | Estado |
|---|---|---|
| Fútbol: cartelera y cuotas | SportsGameOdds | Conectado |
| Fútbol: fixtures, xG, remates, heatmaps, jugadores, alineaciones, H2H, momentum, redes de pases y analítica avanzada | PitchAPI | Conectado; cobertura depende del partido |
| Fútbol: eventos y alineaciones auxiliares | TheSportsDB | Auxiliar; clave pública compartida con límites |
| Fútbol: eventos históricos | StatsBomb Open Data | Conectado |
| Fútbol: resultados históricos abiertos | schoChastics football-data | Adaptador opcional; descarga manual |
| NBA: calendario, tiros, game logs y rosters | nba_api / NBA.com Stats | Panel y endpoints conectados para cartelera, rosters, tiros, box scores, métricas avanzadas, player tracking, play-by-play y estadísticas de temporada; sujeto a bloqueos del proveedor |
| NFL: play-by-play, schedule, rosters, lesiones y depth charts | nflreadpy / nflverse | Código y endpoints añadidos; dependencia opcional |
| MLB: Statcast, pitcheos y métricas de contacto | pybaseball / Baseball Savant | Código y endpoints añadidos; dependencia opcional |
| Historial persistente | Supabase Postgres / REST | Adaptador y migración listos; falta configurar una base de AppApuestas |

## Cambios ya incorporados

### Fútbol / Research

La pantalla muestra, cuando PitchAPI tiene cobertura:

- Mapa de remates, jugador, minuto, resultado y valor xG.
- Evolución acumulada de xG.
- Mapas de actividad de equipo y jugadores.
- Redes de pases y centralización.
- Momentum por minuto.
- Analítica avanzada de equipo y jugador: xT, VAEP, pases y conducciones progresivas, creación, métricas defensivas, PPDA, territorio y tempo.
- Estadísticas de partido, jugadores, alineaciones y cronología.
- Últimos cinco resultados anteriores al encuentro, dentro de la temporada seleccionada.

El cliente PitchAPI trata los bloques avanzados como opcionales. Si un partido no tiene eventos/analítica avanzada, conserva el registro principal y devuelve advertencias y una lista de campos sin cobertura. Las respuestas 404 opcionales se cachean. El limitador local reduce las peticiones después de recibir HTTP 429.

**Coordenadas:** los tiros PitchAPI se normalizan en un terreno de 105 × 68 con el equipo atacando hacia x=105. No se gira el visitante en el navegador. Un heatmap de acciones no es tracking continuo ni GPS. La red de pases depende del feed de eventos y su ventana puede limitarse al once inicial.

**Métricas:** xG valora la ocasión de remate; xT y VAEP valoran acciones. No se mezclan métricas de proveedores distintos como si fueran equivalentes. Los valores vacíos no deben convertirse en ceros.

### StatsBomb

Se conserva para investigación histórica de eventos, tiros, coordenadas, xG, actividad, corners, faltas, tarjetas, H2H y backtesting. No es una cartelera actual ni una fuente de plantillas vigentes de todas las ligas. Los análisis derivados deben atribuirse a StatsBomb. Los bloques de alineación no disponibles se cachean como ausentes.

### NBA

El paquete nba_api ya está en las dependencias obligatorias. Se añadieron rutas y un panel con:
- Cartelera y marcadores por fecha.
- Catálogo de equipos.
- Rosters consultados por temporada NBA.
- Shot chart por partido, filtrable por equipo y por jugador.
- Game logs de equipos y jugadores.

Las coordenadas NBA LOC_X/LOC_Y son específicas de baloncesto y no se reutilizan con las escalas de fútbol. El cliente consulta NBA.com Stats, que puede limitar o cambiar sus endpoints; si bloquea la consulta, se informa el error sin inventar datos.

### NFL

Se añadieron nfl_research.py, rutas y panel para calendario, play-by-play por game_id, rosters semanales, informes de lesiones y depth charts. Usa nflreadpy, pero esta dependencia queda en requirements-optional.txt y no se instala en Render automáticamente. Los datos de nflverse tienen licencias por dataset: la mayoría CC BY 4.0 y FTN charting CC BY-SA 4.0. La respuesta debe conservar atribución y distinguir temporada/semana. No tratar el PBP como feed en directo.

### MLB

Se añadieron mlb_research.py, rutas y panel Statcast: lances individuales, tipo y descripción del lanzamiento, velocidad, spin, ubicación plate_x/plate_z, velocidad de salida, ángulo de bateo y métricas esperadas cuando estén publicadas. Usa pybaseball, también opcional. Las consultas se limitan a tres días y a 5.000 registros de respuesta. La licencia MIT del paquete no otorga automáticamente permiso para redistribuir datos de Baseball Savant, FanGraphs o Baseball Reference.

## Repositorios examinados

| Proyecto | Aporte | Decisión |
|---|---|---|
| [mplsoccer](https://github.com/andrewRowlinson/mplsoccer) | Campos, heatmaps, shot maps, pases, radar y gráficos; MIT | En requirements-optional.txt para informes offline. La UI usa SVG para reducir dependencias |
| [kloppy](https://github.com/PySport/kloppy) | Modelo común para eventos y tracking y transformación de coordenadas; BSD-3-Clause | Opcional si se incorpora otro proveedor real de eventos/tracking |
| [socceraction](https://github.com/ML-KULeuven/socceraction) | SPADL, VAEP, xT y valoración de acciones; MIT | Opcional para investigación y validación histórica; no duplica las métricas ya recibidas de PitchAPI |
| [EasySoccerData](https://github.com/manucabral/EasySoccerData) | Adaptadores en evolución para SofaScore, Promiedos y otras webs | No se usa en producción. MIT cubre el código, no los datos ni los términos de cada sitio |
| [open-football](https://github.com/withqwerty/open-football) | Catálogo CC0 de datasets y recursos abiertos | Índice de fuentes, no API en vivo |
| [schochastics/football-data](https://github.com/schochastics/football-data) | Parquet con 1.237.935 resultados anunciados de 207 ligas y 20 torneos entre 1888 y 2023 | Adaptador y descarga manual opcional. ODC-BY exige atribución. Solo marcadores, no xG/eventos |
| [nba_api](https://github.com/swar/nba_api) | Endpoints NBA.com: calendario, rosters, tiros, game logs, box score y play-by-play | Conectado; disponibilidad externa no garantizada |
| [nflreadpy](https://github.com/nflverse/nflreadpy) | PBP, schedule, estadísticas de jugadores/equipos, rosters, lesiones y depth charts | Conector opcional añadido |
| [pybaseball](https://github.com/jldbc/pybaseball) | Statcast y estadísticas de bateo/lanzamiento | Conector opcional añadido |

### Fuentes descartadas o restringidas

EasySoccerData no se activa como scraper general de producción: cada web tiene condiciones distintas y endpoints no oficiales pueden cambiar. football-data.co.uk no se incorpora para automatización o entrenamiento de IA sin autorización adicional; que un archivo esté disponible para descargar no concede derechos ilimitados.

## Archivo histórico Supabase de AppApuestas

Se reutilizó un proyecto Supabase anterior y se convirtió en el almacén privado de investigación histórica de AppApuestas. El proyecto sigue mostrando temporalmente el nombre antiguo **edgebet-historical**; el nombre y la organización se deben ajustar desde el Dashboard de Supabase.

**Proyecto asignado:** `qqclrmhfudkckadxmbiy` · región `ca-central-1`  
**Dashboard:** https://supabase.com/dashboard/project/qqclrmhfudkckadxmbiy

### Datos conservados

| Conjunto | Registros | Uso |
|---|---:|---|
| Resultados de fútbol de Football-Data.co.uk | 64,586 | Marcadores y estadísticas históricas de equipos |
| Resultados MLB StatsAPI | 14,577 | Historial de partidos de béisbol |
| Resúmenes de mercados y cuotas | 440,959 | Apertura, cierre, mínimos/máximos, promedios y recuento de observaciones |
| American Soccer Analysis | 3,351 | xG por equipo y métricas publicadas |
| StatsBomb Open Data | 32 | xG, remates y referencia avanzada de eventos |
| Identidades de equipos | 153 | Equivalencias entre nombres e IDs de proveedores, confianza mínima 0.90 |
| Alias de eventos | 84 | Cruce de identificadores de eventos, confianza mínima 0.90 |

Los 440,959 resúmenes compactan 821,636 observaciones anteriores. Se conservan apertura/cierre y rangos; **no** es un feed tick a tick. 439,169 grupos conservan alguna probabilidad justa. En los demás mercados solo queda la probabilidad implícita; no se inventa una probabilidad justa.

### Tablas privadas

- `historical_matches`: resultados históricos de fútbol y MLB.
- `historical_match_features`: métricas avanzadas de ASA y StatsBomb, sin payloads JSON originales.
- `market_odds_summary`: resúmenes compactos de precios de mercado.
- `team_identity_map` y `event_identity_aliases`: equivalencias de IDs con confianza.
- `research_snapshots`: snapshots diarios de análisis generados por AppApuestas.

Las seis tablas tienen RLS activo. No hay políticas para `anon` ni `authenticated`; el backend usa una clave secreta de Supabase (`sb_secret_`, que opera con el rol `service_role`) desde Render. La clave de servicio nunca debe incluirse en el navegador, GitHub ni APK.

### Endpoints nuevos

- Estado del almacenamiento: `GET /api/v1/research/storage/status`.
- Snapshots por partido: `GET /api/v1/research/storage/history/{match_id}?provider=pitchapi`.
- Historial anterior de un equipo: `GET /api/v1/research/archive/teams/{team_name}?before_date=YYYY-MM-DD&limit=5`.
- Resúmenes de cuotas por evento: `GET /api/v1/research/archive/events/{event_id}/markets?limit=50`.

El endpoint de equipo limita los partidos a fechas anteriores al encuentro consultado y separa resultados de métricas avanzadas. Los campos sin cobertura permanecen nulos; el resultado histórico no se presenta como estadística actual.

### Licencias y límites

- American Soccer Analysis: datos CC BY-SA 4.0; conservar atribución y compartir adaptaciones bajo las condiciones aplicables.
- StatsBomb Open Data: atribuir a StatsBomb y utilizar su logotipo cuando se publiquen análisis derivados, conforme a sus condiciones.
- Football-Data.co.uk y MLB StatsAPI: se conserva la procedencia; no se debe asumir autorización ilimitada de redistribución o uso comercial solo por disponer de los registros.
- Se excluyeron predicciones sombra sin calibrar, tablas de calibración de EdgeBet, colas, datos de usuario, payloads de scraping sin valor verificable, Statcast con coordenadas marcadas como no válidas y credenciales antiguas.

### Limpieza y estado operativo

- Se retiraron las tablas SQL y secretos de EdgeBet del proyecto histórico.
- Se desprogramaron las tareas cron de EdgeBet y se retiraron sus funciones SQL.
- Quedan cuatro Edge Functions antiguas de EdgeBet desplegadas con JWT desactivado. No se pudieron eliminar desde las herramientas conectadas; deben borrarse manualmente desde **Supabase Dashboard → Edge Functions**.
- Tamaño de base comprobado tras la limpieza: **223 MB**, por debajo del límite de 500 MB del plan gratuito. Conteos remotos verificados: 79,163 resultados, 440,959 resúmenes de mercados, 3,383 métricas avanzadas, 153 identidades de equipos y 84 alias de eventos. Health advisor sin incidencias.
- El proyecto principal antiguo de EdgeBet (`lrrtzrcmmjtukljgeqju`) se pausó correctamente y Supabase lo muestra como `INACTIVE`. Sus datos útiles ya se copiaron; su eliminación definitiva queda pendiente desde Dashboard → Settings → General → Delete project.
- El proyecto usado para AppApuestas conserva todavía el nombre histórico `edgebet-historical`; cambiarlo manualmente a `app-apuestas-research` desde Settings → General.
- La ejecución de cuotas compacta 821,636+ observaciones a 440,959 grupos de mercado. Se conservan apertura/cierre y rangos, no cada tick intermedio.

Variables privadas en Render: `SUPABASE_URL`, `SUPABASE_SECRET_KEY` (recomendada) o `SUPABASE_SERVICE_ROLE_KEY` (legacy), `SUPABASE_RESEARCH_TABLE=research_snapshots` y `APP_MODEL_VERSION`. La URL y el nombre de tabla ya están configurados en Render. Para habilitar las consultas falta añadir `SUPABASE_SECRET_KEY` desde Settings → Environment de Render. No compartas esa clave por chat; no uses la publishable/anon key.

## Seguridad y estabilidad

- POST /actualizar-datos está desactivado por defecto. Requiere ADMIN_API_KEY en Render y el encabezado X-Admin-Key.
- Las cachés se limitan por tiempo y cantidad para reducir consultas y memoria.
- NFL, MLB, mplsoccer, kloppy, socceraction y DuckDB están en requirements-optional.txt. No se instalan durante el build normal.
- El parquet histórico no se incluye en Git ni se descarga al iniciar la aplicación.
- La API de cuotas y apuestas sigue siendo de lectura; la app no envía apuestas.
- Los modelos históricos y mercados experimentales requieren backtesting cronológico por liga/mercado. Una probabilidad alta no implica certeza ni rentabilidad.

## Validación pendiente

La fuente de verdad de despliegues es Render y la de pruebas, GitHub Actions. GitHub Actions está configurado para ejecutar las pruebas Python y verificar sintaxis JS; los tres pasos usan acciones fijadas a SHA completo. En las últimas ejecuciones, sin embargo, GitHub terminó el job antes de asignar runner (runner_id=0, runner_name vacío y cero pasos). No se puede declarar la suite aprobada hasta corregir los permisos/política de Actions y observar pasos completados.
En Settings → Actions → General, la política debe permitir las tres acciones oficiales fijadas en .github/workflows/tests.yml: checkout, setup-python y setup-node. Para política selectiva, añadir sus referencias SHA completas; mantener activa la protección de SHA completo.
