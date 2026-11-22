# Evaluación de herramientas y fuentes para AppApuestas

Fecha de revisión: 22 de noviembre de 2026.

## Resumen ejecutivo

La prioridad no es acumular scrapers, sino construir un motor de investigación con datos trazables, fechas de corte y cobertura declarada. La aplicación ya cuenta con PitchAPI, StatsBomb Open Data, SportsGameOdds y TheSportsDB. La mayor mejora inmediata consiste en aprovechar los campos que ya llegan de PitchAPI antes de añadir nuevas dependencias.

## Fuentes que ya están conectadas

| Fuente | Uso correcto | Límites |
|---|---|---|
| PitchAPI | Calendario, resultados por liga/temporada, tiros con xG y coordenadas, estadísticas individuales y de equipo, mapas 16x12, red de pases, momentum, eventos, H2H y analítica avanzada | Los bloques avanzados no existen para todos los partidos. Una respuesta ANALYTICS_UNAVAILABLE significa falta de cobertura analítica, no un fallo del partido |
| StatsBomb Open Data | Investigación histórica con eventos, tiros, xG, mapas de actividad, secuencias y backtesting para competiciones/temporadas publicadas | No es un feed en vivo ni representa las plantillas actuales de todas las ligas. Requiere atribución a StatsBomb |
| SportsGameOdds | Cartelera y mercados/cuotas según deporte y plan de la cuenta | Hay que controlar cuota mensual y frecuencia de refresco del plan |
| TheSportsDB | Segunda referencia para determinados eventos, alineaciones y datos auxiliares | La llave pública compartida se puede saturar y la cobertura varía; no debe ser fuente principal |

## Mejoras aplicadas en Research

La pantalla consume datos que el backend ya descargaba y ahora agrega:

- Mapa de tiros con ubicación, jugador, minuto y tamaño relativo al xG.
- Evolución acumulada del xG de ambos equipos.
- Mapas de actividad/heatmaps de equipo y jugador.
- Redes de pases para los onces iniciales, con conexiones y centralización.
- Curva de momentum, cuando existe.
- Métricas avanzadas de equipo: xT, VAEP, pases progresivos, conducciones, creación, defensa, PPDA, territorio y tempo cuando el proveedor las entrega.
- Comparativa avanzada por jugador: VAEP, xT, progresión, creación y defensa.
- Cronología de goles, tarjetas, sustituciones y penaltis.
- Forma reciente: últimos cinco partidos finalizados previos al encuentro, de la temporada seleccionada; no usa resultados futuros.

Las visualizaciones deben mostrar un estado vacío explícito cuando el proveedor no entrega el bloque. Nunca se deben rellenar huecos con estadísticas inferidas como si fueran datos oficiales.

### Interpretación de mapas y métricas

PitchAPI expresa las coordenadas de tiros en metros sobre un campo de 105 x 68 y normaliza la dirección para que el equipo que remata ataque hacia x=105. No hay que girar manualmente los tiros visitantes. Sus mapas de actividad usan una matriz 16 x 12; para comparar ambos equipos en un campo común se solicita el marco home_ltr, que ya ajusta la orientación visitante.

La red de pases describe la circulación del once inicial hasta la primera sustitución. Los receptores pueden ser inferidos y algunas conexiones pueden faltar. No debe interpretarse como tracking continuo.

xG, xT, VAEP, PPDA y momentum son métricas distintas. No deben mezclarse entre proveedores ni tratarse como equivalentes. En particular, xT y VAEP valoran acciones, mientras que xG valora la calidad de una ocasión de remate.

## Repositorios evaluados

| Repositorio | Aporte potencial | Decisión |
|---|---|---|
| [mplsoccer](https://github.com/andrewRowlinson/mplsoccer) | Campos, heatmaps, mapas de tiros/pases, radares, hexbins y gráficos de fútbol; licencia MIT | Recomendado como herramienta para informes PNG/PDF o análisis offline. La interfaz web usa SVG para evitar agregar Matplotlib y peso de dependencias al servicio gratuito |
| [kloppy](https://github.com/PySport/kloppy) | Estandariza formatos de datos de eventos y tracking de distintos proveedores y sistemas de coordenadas; BSD-3-Clause | Recomendado si se incorpora una segunda fuente real de eventos/tracking. No es un proveedor de datos por sí mismo |
| [socceraction](https://github.com/ML-KULeuven/socceraction) | Convierte eventos a SPADL y calcula VAEP/xT y ratings de acciones; MIT | Útil para validación independiente y experimento histórico. No se agrega ahora porque PitchAPI ya publica esas métricas y el repositorio declara un foco académico/reproducibilidad |
| [EasySoccerData](https://github.com/manucabral/EasySoccerData) | Adaptadores para fuentes como SofaScore, FBref, Promiedos, Goaloo, 365Scores, Understat y BeSoccer; MIT para el código | No activar como scraper general de producción. Cada fuente tiene condiciones propias y los endpoints no oficiales pueden cambiar o bloquear el servicio. Evaluar por separado cada adaptador y su permiso |
| [open-football](https://github.com/withqwerty/open-football) | Catálogo de datasets y herramientas de fútbol abierto; CC0 para el catálogo | Útil como índice de nuevos conjuntos de datos, no como API en vivo |
| [nflreadpy](https://github.com/nflverse/nflreadpy) | Play-by-play, estadísticas por jugador/equipo, rosters, lesiones, depth charts, snap counts y Next Gen Stats | Recomendado para una fase NFL. La mayoría de datos nflverse son CC BY 4.0; FTN charting usa CC BY-SA 4.0 y requiere atribución/licencia separada |
| [nba_api](https://github.com/swar/nba_api) | Estadísticas NBA.com, game logs, tiros con coordenadas, shot charts, box scores, play-by-play, WNBA/G League | Ya está en requirements.txt. Conviene crear un módulo real de investigación NBA y probar acceso desde Render; la disponibilidad del sitio externo no está garantizada |
| [pybaseball](https://github.com/jldbc/pybaseball) | Statcast lanzamiento a lanzamiento, velocidad, spin, exit velocity, launch angle, métricas de bateadores/lanzadores | Recomendado para fase MLB. Es scraping de fuentes externas y los términos de Baseball Savant/FanGraphs/Baseball Reference se deben revisar antes de publicar datos |
| [Football Analytics / StatsBomb demo](https://github.com/AlexandreMorel/Football-Analytics) | Ejemplo de visualizaciones de pases, tiros, heatmaps, xG timeline y radares con StatsBomb | Referencia visual/técnica; no conviene desplegar una segunda app Streamlit paralela a FastAPI/PWA |

## Fuentes adicionales revisadas y restricciones

- [football-data.co.uk](https://www.football-data.co.uk/): archivo atractivo de resultados y cuotas históricas. Sin embargo, su política vigente indica uso para personas particulares con descarga manual o automatización ligera (máximo dos veces por semana); excluye proyectos comerciales y proyectos de entrenamiento de IA que usen bots/scrapers. **No integrar ni entrenar AppApuestas con estos CSV sin una autorización/licencia distinta.** La licencia del archivo no debe suponerse por el hecho de que sea descargable.
- [nflreadpy](https://github.com/nflverse/nflreadpy): candidato sólido para NFL. Descarga play-by-play, estadísticas de jugador/equipo, calendarios, rosters por semana, snap counts, Next Gen Stats, lesiones y depth charts. Código MIT; la mayoría de los datasets nflverse son CC BY 4.0, mientras FTN charting es CC BY-SA 4.0. Revisar la licencia concreta por dataset.
- [nba_api](https://github.com/swar/nba_api): ya es dependencia del proyecto. Proporciona 130+ endpoints de NBA.com, incluidos game logs, shot charts, play-by-play, box scores, standings y live feeds sin API key. El código es MIT, pero los datos siguen sujetos a los términos de NBA.com; los endpoints no son un contrato de disponibilidad y pueden cambiar o bloquear peticiones.
- [pybaseball](https://github.com/jldbc/pybaseball): candidato para Statcast/MLB, con lanzamientos individuales y métricas como velocidad de salida, ángulo de lanzamiento, velocidad/spin del pitcheo y datos de bateadores/lanzadores. El paquete es MIT, pero los datos proceden de terceros; hay que respetar los términos de Baseball Savant, FanGraphs y Baseball Reference según cada extracción.

## Qué conviene hacer a continuación

1. **Consolidar almacenamiento histórico persistente.** Ahora existen cachés en memoria, que se pierden al reiniciar o despertar el servicio gratuito. Para historiales de análisis, snapshots y backtesting hace falta un almacén persistente, por ejemplo PostgreSQL de Supabase en su plan gratuito, con claves de partido, proveedor, temporada, timestamp de consulta y versión de modelo. No se debe guardar ni exponer ninguna API key en el cliente.
2. **Completar el historial de fútbol.** Añadir forma a 5/10 partidos, local/visitante, goles, xG, córners y tarjetas por partido cuando existan datos verificables. Calcular todo con una fecha de corte anterior al encuentro objetivo; H2H no debe sustituir la forma reciente.
3. **Auditar cobertura y frescura.** Registrar para cada encuentro qué bloques existen: cuotas, lineup confirmado/provisional, tiros, xG, heatmap, red, eventos, jugadores, H2H y analítica avanzada. Mostrar la hora de la última actualización y no convertir null en cero.
4. **Incorporar NBA y MLB con módulos propios.** Para NBA, reutilizar nba_api (ya está instalado) y validar endpoints de tiros/logs desde Render antes de usarlo en predicción. Para MLB, implementar Statcast por fecha/jugador con rangos cortos, caché y límites de consulta.
5. **Añadir NFL mediante nflreadpy.** Priorizar PBP histórico, rosters semanales, snap counts, lesiones y depth charts; actualizar según la programación de las publicaciones. Es más apto para análisis prepartido e histórico que para marcador minuto a minuto.
6. **Validar los modelos.** Backtesting cronológico por liga y temporada, sin fuga temporal; medir Brier Score, Log Loss y calibración por mercado. Los pronósticos no se deben publicar como “seguros” solo por presentar una probabilidad alta.

## Fuentes y licencias

- PitchAPI: https://pitchapi.dev/ (referencia de endpoints, cobertura, coordenadas, mapas y analítica).
- StatsBomb Open Data: https://github.com/statsbomb/open-data (atribución obligatoria).
- nflverse: https://github.com/nflverse/nflreadpy y https://github.com/nflverse/nflverse-data.
- pybaseball: https://github.com/jldbc/pybaseball; el código y los datos externos tienen condiciones diferentes.
- Consultar las condiciones de uso de cada proveedor antes de usar scrapers o redistribuir datos.

## Estado de validación

La modificación de interfaz se encuentra versionada en GitHub y Render despliega automáticamente cada commit. El workflow de GitHub Actions está fallando antes de ejecutar los pasos (job sin runner asignado, sin pasos ejecutados); por tanto, ese fallo no demuestra que haya errores en el código ni permite afirmar que las pruebas hayan pasado. La verificación final del último deploy se debe leer desde Render.
