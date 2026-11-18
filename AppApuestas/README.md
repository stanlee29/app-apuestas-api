# AppApuestas — Backend

API deportiva con FastAPI. La cartelera y los mercados se obtienen de SportsGameOdds API v2.

## Configuración de la fuente

1. Crear cuenta en https://sportsgameodds.com/pricing y seleccionar Amateur.
2. Copiar la clave recibida por correo.
3. Agregarla a las variables privadas del servicio Render como \`SPORTSGAMEODDS_API_KEY\`.
4. Verificar \`/health\` y \`/api/v1/source/status\`.
5. Probar \`/api/v1/events?deporte=nba&dias=2\` y abrir un evento mediante \`/api/v1/events/{event_id}/markets\`.

El plan gratuito publicado tiene 2.500 objetos al mes, 10 solicitudes por minuto y actualización cada 10 minutos. El registro solicita tarjeta, pero el proveedor declara que el plan Amateur no genera cargos mientras no se actualice.

La cobertura gratuita incluye ocho ligas: NFL, NBA, MLB, NHL, NCAA Football, NCAA Basketball, Champions League y MLS. No equivale a toda la cartelera mundial ni a GanaPlay.

## Variables

Consulta \`.env.example\`. No guardes claves reales en este repositorio.

## Ejecutar

\`\`\`bash
pip install -r requirements.txt
uvicorn api_servidor:app --reload
\`\`\`
