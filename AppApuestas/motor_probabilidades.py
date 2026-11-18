"""
Motor estadístico base para estimar resultados y valor esperado.
Las probabilidades son estimaciones del modelo, no garantías.
"""
import math
import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
COLUMNAS = [
    "fecha",
    "equipo_local",
    "equipo_visitante",
    "puntos_local",
    "puntos_visitante",
]


def normalizar_nombre(nombre: Any) -> str:
    texto = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", texto.casefold())


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def norm_cdf(x: float, mu: float, sigma: float) -> float:
    if sigma <= 0:
        return 0.5 if x >= mu else 0.0
    z = (x - mu) / (sigma * math.sqrt(2.0))
    return 0.5 * (1.0 + math.erf(z))


def calcular_valor_ev(probabilidad_pct: float, cuota_casa: float) -> dict[str, Any]:
    """EV por unidad apostada, usando cuota decimal y probabilidad del modelo."""
    probabilidad = float(probabilidad_pct) / 100.0
    cuota = float(cuota_casa)
    if not 0 <= probabilidad <= 1:
        raise ValueError("La probabilidad debe estar entre 0 y 100.")
    if cuota <= 1:
        raise ValueError("La cuota decimal debe ser mayor que 1.")

    cuota_justa = (1.0 / probabilidad) if probabilidad > 0 else None
    ev = (probabilidad * cuota) - 1.0
    return {
        "cuota_justa": round(cuota_justa, 2) if cuota_justa is not None else None,
        "valor_esperado": round(ev, 4),
        "es_valor_positivo": ev > 0,
    }


def cargar_datos(ruta_carpeta: str | Path = "datos") -> dict[str, pd.DataFrame]:
    carpeta = Path(ruta_carpeta)
    if not carpeta.is_absolute():
        carpeta = BASE_DIR / carpeta

    datos: dict[str, pd.DataFrame] = {}
    for deporte in ["nba", "nfl", "mlb", "futbol"]:
        ruta = carpeta / f"{deporte}_resultados.csv"
        if not ruta.exists():
            datos[deporte] = pd.DataFrame(columns=COLUMNAS)
            continue

        try:
            df = pd.read_csv(ruta, encoding="utf-8")
            df.columns = [str(columna).strip().lower() for columna in df.columns]
            if not set(COLUMNAS).issubset(df.columns):
                raise ValueError("El CSV no contiene las columnas requeridas.")
            df = df[COLUMNAS].copy()
            df["equipo_local"] = df["equipo_local"].astype("string").str.strip()
            df["equipo_visitante"] = df["equipo_visitante"].astype("string").str.strip()
            df["puntos_local"] = pd.to_numeric(df["puntos_local"], errors="coerce")
            df["puntos_visitante"] = pd.to_numeric(df["puntos_visitante"], errors="coerce")
            df = df.dropna(subset=["equipo_local", "equipo_visitante", "puntos_local", "puntos_visitante"])
            datos[deporte] = df
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            print(f"⚠️ No se pudo leer {ruta.name}: {exc}")
            datos[deporte] = pd.DataFrame(columns=COLUMNAS)

    return datos


def obtener_estadisticas_equipo(
    df: pd.DataFrame,
    eq_local: str,
    eq_visitante: str,
) -> dict[str, float]:
    league_home_scored = float(df["puntos_local"].mean())
    league_away_scored = float(df["puntos_visitante"].mean())
    league_diff_std = float(df["puntos_local"].sub(df["puntos_visitante"]).std())
    league_total_std = float(df["puntos_local"].add(df["puntos_visitante"]).std())

    if not math.isfinite(league_diff_std) or league_diff_std < 1:
        league_diff_std = 10.0
    if not math.isfinite(league_total_std) or league_total_std < 1:
        league_total_std = 10.0

    def weighted_mean(columna: str, equipo: str, es_local: bool) -> float:
        campo_equipo = "equipo_local" if es_local else "equipo_visitante"
        objetivo = normalizar_nombre(equipo)
        mask = df[campo_equipo].map(normalizar_nombre) == objetivo
        partidos = df.loc[mask].copy()

        if partidos.empty:
            return league_home_scored if es_local else league_away_scored

        partidos["_fecha_orden"] = pd.to_datetime(partidos["fecha"], errors="coerce", utc=True)
        partidos = partidos.sort_values("_fecha_orden", ascending=False, na_position="last")
        recientes = partidos.head(10)
        anteriores = partidos.iloc[10:]

        promedio_reciente = float(recientes[columna].mean())
        promedio_anterior = float(anteriores[columna].mean()) if not anteriores.empty else promedio_reciente
        return (promedio_reciente * 0.6) + (promedio_anterior * 0.4)

    return {
        "home_off": max(0.1, weighted_mean("puntos_local", eq_local, True)),
        "home_def": max(0.1, weighted_mean("puntos_visitante", eq_local, True)),
        "away_off": max(0.1, weighted_mean("puntos_visitante", eq_visitante, False)),
        "away_def": max(0.1, weighted_mean("puntos_local", eq_visitante, False)),
        "league_diff_std": max(1.0, league_diff_std),
        "league_total_std": max(1.0, league_total_std),
    }


def predecir_poisson(
    lam_local: float,
    lam_visitante: float,
    limite_under: float,
    incluir_empate: bool,
) -> dict[str, Any]:
    max_goles = 20
    prob_local = prob_empate = prob_visitante = prob_under = 0.0

    for local in range(max_goles + 1):
        for visitante in range(max_goles + 1):
            probabilidad = poisson_pmf(local, lam_local) * poisson_pmf(visitante, lam_visitante)
            if local > visitante:
                prob_local += probabilidad
            elif local == visitante:
                prob_empate += probabilidad
            else:
                prob_visitante += probabilidad
            if local + visitante <= limite_under:
                prob_under += probabilidad

    total = prob_local + prob_empate + prob_visitante
    if total > 0:
        prob_local /= total
        prob_empate /= total
        prob_visitante /= total
        prob_under /= total

    resultado = {
        "modelo": "Poisson",
        "goles_esperados_local": round(lam_local, 2),
        "goles_esperados_visitante": round(lam_visitante, 2),
        "prob_victoria_local": round(prob_local, 4),
        "prob_victoria_visitante": round(prob_visitante, 4),
        "prob_over": round(1.0 - prob_under, 4),
        "prob_under": round(prob_under, 4),
    }
    if incluir_empate:
        resultado["prob_empate"] = round(prob_empate, 4)
    return resultado


def predecir_normal(
    media_local: float,
    media_visitante: float,
    desv_diferencia: float,
    desv_total: float,
    limite_over: float,
) -> dict[str, Any]:
    media_diferencia = media_local - media_visitante
    media_total = media_local + media_visitante
    prob_local = 1.0 - norm_cdf(0.0, media_diferencia, desv_diferencia)
    prob_over = 1.0 - norm_cdf(limite_over, media_total, desv_total)

    return {
        "modelo": "Normal (puntos esperados)",
        "puntos_esperados_local": round(media_local, 2),
        "puntos_esperados_visitante": round(media_visitante, 2),
        "handicap_estimado": round(media_diferencia, 2),
        "total_puntos_esperados": round(media_total, 2),
        "prob_victoria_local": round(prob_local, 4),
        "prob_victoria_visitante": round(1.0 - prob_local, 4),
        "prob_over": round(prob_over, 4),
        "prob_under": round(1.0 - prob_over, 4),
    }


def predecir_partido(
    deporte: str,
    equipo_local: str,
    equipo_visitante: str,
    datos: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    df = datos.get(deporte)
    if df is None or df.empty:
        return {"error": f"No hay datos históricos suficientes para {deporte}."}

    nombres = pd.concat([df["equipo_local"], df["equipo_visitante"]]).dropna().astype(str).unique()
    mapa = {normalizar_nombre(nombre): nombre for nombre in nombres}
    local_real = mapa.get(normalizar_nombre(equipo_local))
    visitante_real = mapa.get(normalizar_nombre(equipo_visitante))

    if local_real is None:
        return {"error": f"El equipo local '{equipo_local}' no aparece en los históricos."}
    if visitante_real is None:
        return {"error": f"El equipo visitante '{equipo_visitante}' no aparece en los históricos."}

    estadisticas = obtener_estadisticas_equipo(df, local_real, visitante_real)
    media_local = (estadisticas["home_off"] + estadisticas["away_def"]) / 2.0
    media_visitante = (estadisticas["away_off"] + estadisticas["home_def"]) / 2.0

    if deporte in ["futbol", "mlb"]:
        limite_under = 2.5 if deporte == "futbol" else 8.5
        return predecir_poisson(
            media_local,
            media_visitante,
            limite_under,
            incluir_empate=(deporte == "futbol"),
        )

    limite_over = 45.5 if deporte == "nfl" else 225.5
    return predecir_normal(
        media_local,
        media_visitante,
        estadisticas["league_diff_std"],
        estadisticas["league_total_std"],
        limite_over,
    )
