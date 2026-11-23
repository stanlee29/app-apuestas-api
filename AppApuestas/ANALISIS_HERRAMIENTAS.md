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
| NBA: calendario, tiros, game logs y rosters | nba_api / NBA.com Stats | Panel y endpoints conectados; sujeto a bloqueos del proveedor |
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

## Almacenamiento histórico

Se incorporó un adaptador opcional que guarda snapshots diarios de análisis de PitchAPI y StatsBomb en Supabase Postgres.

- Migración: AppApuestas/sql/001_research_snapshots.sql.
- Estado: GET /api/v1/research/storage/status.
- Historial: GET /api/v1/research/storage/history/{match_id}?provider=pitchapi.
- Variables privadas en Render: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY y SUPABASE_RESEARCH_TABLE.

**No se ha seleccionado ni modificado ningún proyecto Supabase para AppApuestas.** Para activarlo, hay que elegir el proyecto correcto, aplicar la migración y añadir su service-role key solo en Render. La clave nunca debe estar en la web ni en el APK.

La caché en memoria se pierde al reiniciar o suspender el servicio. La persistencia funciona solo después de habilitar Supabase o instalar el dataset local en un volumen persistente.

## Seguridad y estabilidad

- POST /actualizar-datos está desactivado por defecto. Requiere ADMIN_API_KEY en Render y el encabezado X-Admin-Key.
- Las cachés se limitan por tiempo y cantidad para reducir consultas y memoria.
- NFL, MLB, mplsoccer, kloppy, socceraction y DuckDB están en requirements-optional.txt. No se instalan durante el build normal.
- El parquet histórico no se incluye en Git ni se descarga al iniciar la aplicación.
- La API de cuotas y apuestas sigue siendo de lectura; la app no envía apuestas.
- Los modelos históricos y mercados experimentales requieren backtesting cronológico por liga/mercado. Una probabilidad alta no implica certeza ni rentabilidad.

## Validación pendiente

La fuente de verdad de despliegues es Render y la de pruebas, GitHub Actions. Los trabajos de Actions han presentado fallos sin asignar runner (runner_id=0 y cero pasos ejecutados); esto no demuestra que el código haya fallado ni permite afirmar que las pruebas hayan pasado. Confirmar últimos deploys, logs y pruebas ejecutadas antes de declarar la versión verificada.
