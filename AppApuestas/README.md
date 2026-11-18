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
