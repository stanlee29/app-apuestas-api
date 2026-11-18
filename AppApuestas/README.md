# EdgeBet — Sports Research MVP

Primera versión de la aplicación web EdgeBet, servida por FastAPI y adaptable a móvil y escritorio. Puede instalarse como PWA desde un navegador compatible.

## Qué incluye

- Cartelera para fútbol, NBA, NFL y MLB consultada desde el scoreboard público de ESPN.
- Probabilidades estimadas por el motor estadístico cuando existen históricos compatibles para ambos equipos.
- Cuotas decimales únicamente cuando ESPN publica campos moneyline estructurados.
- Cálculo de EV únicamente cuando coinciden probabilidad del modelo y cuota publicada.
- Panel adaptable a móvil, actualización manual y caché de la interfaz para abrir la app sin conexión.

## Ejecutar localmente

Requiere Python 3.12 o superior.

\`\`\`bash
cd AppApuestas
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api_servidor:app --reload
\`\`\`

Abrir http://127.0.0.1:8000. La documentación de la API queda en http://127.0.0.1:8000/docs y el estado del servicio en /health.

## Endpoints principales

| Endpoint | Uso |
| --- | --- |
| \`GET /\` | Interfaz web EdgeBet |
| \`GET /health\` | Estado de la API y presencia de datasets |
| \`GET /cartelera/{deporte}?dias=2\` | Cartelera y análisis |
| \`GET /equipos/{deporte}\` | Equipos existentes en históricos |
| \`GET /predecir\` | Predicción de un enfrentamiento |
| \`POST /actualizar-datos\` | Actualizar resultados históricos |

Valores admitidos para \`deporte\`: \`futbol\`, \`nba\`, \`nfl\`, \`mlb\`. El parámetro \`dias\` admite de 0 a 7.

## Datos y límites actuales

- ESPN es la fuente del calendario. Su disponibilidad, cobertura y respuesta pueden cambiar; un evento no encontrado no se crea artificialmente.
- No se generan cuotas sustitutas. Si el proveedor no entrega moneyline, la app muestra "No disp." y no calcula EV.
- Si los equipos no existen en los CSV históricos, el partido aparece sin predicción en vez de recibir probabilidades por defecto.
- Los históricos son archivos CSV locales. El refresco depende de las fuentes públicas y de las restricciones de cada servicio.
- El motor actual es un modelo estadístico inicial; todavía necesita validación fuera de muestra, calibración por deporte y métricas como Brier Score y Log Loss antes de utilizarse para decisiones reales.

## Despliegue

El archivo \`../render.yaml\` configura un servicio web en el plan gratuito de Render. Desde Render se puede crear un Blueprint usando ese archivo. La instancia gratuita puede entrar en suspensión y tardar en responder al primer acceso.

## Seguridad

No se requieren API keys para el MVP. No agregues claves, contraseñas ni credenciales al repositorio. Antes de habilitar cuentas, tickets, historial personal o cualquier operación con dinero se debe diseñar autenticación, almacenamiento persistente y controles de seguridad.
