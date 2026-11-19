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

### Versión

API backend 1.0.9 o posterior.
