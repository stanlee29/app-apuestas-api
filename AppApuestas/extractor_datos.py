"""
Extracción de históricos deportivos.
Si una fuente falla, conserva un CSV vacío con esquema conocido; nunca inventa resultados.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from nba_api.stats.endpoints import leaguegamelog

BASE_DIR = Path(__file__).resolve().parent
DIRECTORIO_SALIDA = BASE_DIR / "datos"

hoy = datetime.now(timezone(timedelta(hours=-6)))
inicio = hoy - timedelta(days=60)
DATES_RANGE = f"{inicio.strftime('%Y%m%d')}-{hoy.strftime('%Y%m%d')}"

inicio_temporada_nba = hoy.year if hoy.month >= 10 else hoy.year - 1
NBA_SEASON = f"{inicio_temporada_nba}-{str(inicio_temporada_nba + 1)[-2:]}"

HEADERS_ESPN = {
    "User-Agent": "EdgeBet research app/0.1 (public ESPN scoreboard client)",
    "Accept": "application/json",
}
COLUMNAS_ESTANDAR = [
    "fecha",
    "equipo_local",
    "equipo_visitante",
    "puntos_local",
    "puntos_visitante",
]


def asegurar_directorio() -> None:
    DIRECTORIO_SALIDA.mkdir(parents=True, exist_ok=True)


def procesar_y_guardar(df: pd.DataFrame | None, nombre_archivo: str, deporte: str) -> None:
    ruta_archivo = DIRECTORIO_SALIDA / nombre_archivo
    if df is None:
        df = pd.DataFrame(columns=COLUMNAS_ESTANDAR)

    for columna in COLUMNAS_ESTANDAR:
        if columna not in df.columns:
            df[columna] = pd.Series(dtype="object")

    df = df[COLUMNAS_ESTANDAR].copy()
    df = df.dropna(subset=["equipo_local", "equipo_visitante"])
    df["puntos_local"] = pd.to_numeric(df["puntos_local"], errors="coerce")
    df["puntos_visitante"] = pd.to_numeric(df["puntos_visitante"], errors="coerce")
    df = df.dropna(subset=["puntos_local", "puntos_visitante"])
    df["puntos_local"] = df["puntos_local"].astype(int)
    df["puntos_visitante"] = df["puntos_visitante"].astype(int)
    df.to_csv(ruta_archivo, index=False, encoding="utf-8")
    print(f"   {'✅' if not df.empty else '⚠️'} {deporte}: {len(df)} resultados guardados en {ruta_archivo.name}")


def descargar_espn(sport: str, league: str, deporte: str) -> pd.DataFrame:
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
    try:
        response = requests.get(
            url,
            headers=HEADERS_ESPN,
            params={"dates": DATES_RANGE, "limit": 1000},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"   ⚠️ ESPN no respondió para {deporte}: {type(exc).__name__}")
        return pd.DataFrame(columns=COLUMNAS_ESTANDAR)

    registros = []
    for event in data.get("events", []):
        competition_list = event.get("competitions") or []
        if not competition_list:
            continue
        competition = competition_list[0]
        status = (competition.get("status") or event.get("status") or {}).get("type", {})
        if status.get("name") != "STATUS_FINAL":
            continue

        home_team = away_team = None
        home_score = away_score = None
        for competitor in competition.get("competitors", []):
            name = (competitor.get("team") or {}).get("displayName")
            score = competitor.get("score")
            if competitor.get("homeAway") == "home":
                home_team, home_score = name, score
            elif competitor.get("homeAway") == "away":
                away_team, away_score = name, score

        if home_team and away_team and home_score is not None and away_score is not None:
            registros.append({
                "fecha": event.get("date"),
                "equipo_local": home_team,
                "equipo_visitante": away_team,
                "puntos_local": home_score,
                "puntos_visitante": away_score,
            })

    return pd.DataFrame(registros, columns=COLUMNAS_ESTANDAR)


def extraer_datos_nba() -> None:
    print(f"🏀 Extrayendo NBA ({NBA_SEASON})...")
    try:
        data = leaguegamelog.LeagueGameLog(
            season=NBA_SEASON,
            season_type_all_star="Regular Season",
        ).get_data_frames()[0]

        home = data[data["MATCHUP"].str.contains("vs.", na=False)].copy()
        away = data[data["MATCHUP"].str.contains("@", na=False)].copy()

        home = home.rename(columns={
            "GAME_DATE": "fecha",
            "TEAM_NAME": "equipo_local",
            "PTS": "puntos_local",
        })
        away = away.rename(columns={
            "TEAM_NAME": "equipo_visitante",
            "PTS": "puntos_visitante",
        })

        combined = pd.merge(
            home[["GAME_ID", "fecha", "equipo_local", "puntos_local"]],
            away[["GAME_ID", "equipo_visitante", "puntos_visitante"]],
            on="GAME_ID",
            how="inner",
        )
        procesar_y_guardar(combined, "nba_resultados.csv", "NBA")
    except Exception as exc:
        print(f"   ⚠️ No fue posible actualizar NBA: {type(exc).__name__}: {exc}")
        procesar_y_guardar(
            pd.DataFrame(columns=COLUMNAS_ESTANDAR),
            "nba_resultados.csv",
            "NBA",
        )


def extraer_datos_nfl() -> None:
    print("🏈 Extrayendo NFL...")
    procesar_y_guardar(
        descargar_espn("football", "nfl", "NFL"),
        "nfl_resultados.csv",
        "NFL",
    )


def extraer_datos_mlb() -> None:
    print("⚾ Extrayendo MLB...")
    procesar_y_guardar(
        descargar_espn("baseball", "mlb", "MLB"),
        "mlb_resultados.csv",
        "MLB",
    )


def extraer_datos_futbol() -> None:
    print("⚽ Extrayendo fútbol...")
    ligas = [
        ("eng.1", "Premier League"),
        ("esp.1", "LaLiga"),
        ("uefa.champions", "Champions League"),
    ]
    registros = []
    for league_id, nombre in ligas:
        print(f"   Consultando {nombre}...")
        df = descargar_espn("soccer", league_id, nombre)
        if not df.empty:
            registros.extend(df.to_dict("records"))

    procesar_y_guardar(
        pd.DataFrame(registros, columns=COLUMNAS_ESTANDAR),
        "futbol_resultados.csv",
        "Fútbol",
    )


if __name__ == "__main__":
    print(f"Extracción de históricos | Temporada NBA: {NBA_SEASON} | Rango ESPN: {DATES_RANGE}")
    asegurar_directorio()
    extraer_datos_nba()
    extraer_datos_nfl()
    extraer_datos_mlb()
    extraer_datos_futbol()
    print("Proceso de extracción finalizado.")
