"""Modelo experimental Poisson + corrección Dixon-Coles para fútbol.

Utiliza marcadores históricos de una competición/temporada. No infiere xG,
remates, corners ni tarjetas desde el marcador. Debe validarse fuera de muestra.
"""
from __future__ import annotations

import math
import unicodedata
import re
from datetime import date, datetime, timezone
from typing import Any


def _team_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(
            value.get("name")
            or value.get("home_team_name")
            or value.get("away_team_name")
            or ""
        )
    return str(value or "")


def _normalise(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", normalized.casefold())


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def poisson_pmf(goals: int, expected: float) -> float:
    if expected <= 0:
        return 1.0 if goals == 0 else 0.0
    return math.exp(goals * math.log(expected) - expected - math.lgamma(goals + 1))


def dixon_coles_tau(home_goals: int, away_goals: int, lambda_home: float, lambda_away: float, rho: float) -> float:
    if home_goals == 0 and away_goals == 0:
        return max(0.0, 1.0 - lambda_home * lambda_away * rho)
    if home_goals == 0 and away_goals == 1:
        return max(0.0, 1.0 + lambda_home * rho)
    if home_goals == 1 and away_goals == 0:
        return max(0.0, 1.0 + lambda_away * rho)
    if home_goals == 1 and away_goals == 1:
        return max(0.0, 1.0 - rho)
    return 1.0


def _weighted_average(rows: list[dict[str, Any]], value_key: str, base_date: date, half_life_days: float, prior_mean: float, prior_games: float) -> tuple[float, int]:
    numerator = 0.0
    denominator = 0.0
    raw_count = 0
    for row in rows:
        value = row.get(value_key)
        match_date = row.get("_date")
        if not isinstance(value, (int, float)) or match_date is None:
            continue
        age = max(0, (base_date - match_date).days)
        weight = math.pow(0.5, age / half_life_days)
        numerator += float(value) * weight
        denominator += weight
        raw_count += 1
    mean = (numerator + prior_mean * prior_games) / (denominator + prior_games) if denominator + prior_games > 0 else prior_mean
    return mean, raw_count


def predict_from_matches(
    matches: list[dict[str, Any]],
    home_team_name: str,
    away_team_name: str,
    *,
    rho: float = -0.08,
    half_life_days: float = 180.0,
    prior_games: float = 5.0,
    xg_rates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not home_team_name.strip() or not away_team_name.strip():
        raise ValueError("Debes indicar los dos equipos.")
    if _normalise(home_team_name) == _normalise(away_team_name):
        raise ValueError("El equipo local y el visitante deben ser distintos.")
    if not -0.25 <= rho <= 0.25:
        raise ValueError("rho debe estar entre -0.25 y 0.25.")
    if half_life_days <= 0 or prior_games < 0:
        raise ValueError("Los parámetros de recencia y regularización no son válidos.")

    rows: list[dict[str, Any]] = []
    names: dict[str, str] = {}
    for raw in matches:
        if not isinstance(raw, dict):
            continue
        # El modelo de marcadores puede usar todo resultado publicado,
        # aunque StatsBomb no haya liberado el feed de eventos de ese partido.
        home = _team_name(raw.get("home_team"))
        away = _team_name(raw.get("away_team"))
        try:
            home_score, away_score = int(raw["home_score"]), int(raw["away_score"])
        except (KeyError, TypeError, ValueError):
            continue
        match_date = _parse_date(raw.get("match_date"))
        if not home or not away or match_date is None or home_score < 0 or away_score < 0:
            continue
        names[_normalise(home)] = home
        names[_normalise(away)] = away
        rows.append({
            "home": home, "away": away,
            "home_score": home_score, "away_score": away_score,
            "_date": match_date,
        })

    home_key, away_key = _normalise(home_team_name), _normalise(away_team_name)
    home_actual, away_actual = names.get(home_key), names.get(away_key)
    if not home_actual:
        raise ValueError(f"No se encontró '{home_team_name}' en los históricos de esta competición y temporada.")
    if not away_actual:
        raise ValueError(f"No se encontró '{away_team_name}' en los históricos de esta competición y temporada.")
    if len(rows) < 20:
        raise ValueError(f"Histórico insuficiente: solo hay {len(rows)} partidos finalizados; se requieren al menos 20.")

    reference_date = max(row["_date"] for row in rows)
    home_rows = [row for row in rows if _normalise(row["home"]) == home_key]
    away_rows = [row for row in rows if _normalise(row["away"]) == away_key]
    league_home, _ = _weighted_average(rows, "home_score", reference_date, half_life_days, 1.35, 0)
    league_away, _ = _weighted_average(rows, "away_score", reference_date, half_life_days, 1.10, 0)
    if league_home <= 0 or league_away <= 0:
        raise ValueError("No hay suficientes goles en el histórico para estimar tasas de liga.")

    home_attack, home_sample = _weighted_average(home_rows, "home_score", reference_date, half_life_days, league_home, prior_games)
    home_conceded, _ = _weighted_average(home_rows, "away_score", reference_date, half_life_days, league_away, prior_games)
    away_attack, away_sample = _weighted_average(away_rows, "away_score", reference_date, half_life_days, league_away, prior_games)
    away_conceded, _ = _weighted_average(away_rows, "home_score", reference_date, half_life_days, league_home, prior_games)

    attack_home_factor = home_attack / league_home
    defence_home_factor = home_conceded / league_away
    attack_away_factor = away_attack / league_away
    defence_away_factor = away_conceded / league_home
    lambda_home_score = max(0.05, min(5.5, league_home * attack_home_factor * defence_away_factor))
    lambda_away_score = max(0.05, min(5.5, league_away * attack_away_factor * defence_home_factor))
    lambda_home, lambda_away = lambda_home_score, lambda_away_score
    xg_used = False
    if isinstance(xg_rates, dict):
        try:
            xg_home = float(xg_rates["lambda_home"])
            xg_away = float(xg_rates["lambda_away"])
            xg_home_n = int(xg_rates.get("home_matches_with_xg", 0))
            xg_away_n = int(xg_rates.get("away_matches_with_xg", 0))
            if xg_home > 0 and xg_away > 0 and xg_home_n >= 3 and xg_away_n >= 3:
                # Al contar con tres o más partidos de cada condición, combina
                # la señal de xG (65%) con las tasas de goles reales (35%).
                lambda_home = max(0.05, min(5.5, 0.65 * xg_home + 0.35 * lambda_home_score))
                lambda_away = max(0.05, min(5.5, 0.65 * xg_away + 0.35 * lambda_away_score))
                xg_used = True
        except (KeyError, TypeError, ValueError):
            xg_used = False

    matrix: list[tuple[int, int, float]] = []
    for home_goals in range(11):
        for away_goals in range(11):
            probability = poisson_pmf(home_goals, lambda_home) * poisson_pmf(away_goals, lambda_away)
            probability *= dixon_coles_tau(home_goals, away_goals, lambda_home, lambda_away, rho)
            matrix.append((home_goals, away_goals, probability))
    total_probability = sum(row[2] for row in matrix)
    if total_probability <= 0:
        raise ValueError("El modelo no pudo normalizar la matriz de marcadores.")
    matrix = [(h, a, p / total_probability) for h, a, p in matrix]

    p_home = sum(p for h, a, p in matrix if h > a)
    p_draw = sum(p for h, a, p in matrix if h == a)
    p_away = sum(p for h, a, p in matrix if h < a)

    totals = {}
    for line in (0.5, 1.5, 2.5, 3.5, 4.5):
        over = sum(p for h, a, p in matrix if h + a > line)
        totals[str(line)] = {"over": round(over * 100, 2), "under": round((1 - over) * 100, 2)}
    btts_yes = sum(p for h, a, p in matrix if h > 0 and a > 0)
    scores = sorted(matrix, key=lambda row: row[2], reverse=True)[:8]

    head_to_head = [
        row for row in rows
        if {_normalise(row["home"]), _normalise(row["away"])} == {home_key, away_key}
    ]
    head_to_head.sort(key=lambda row: row["_date"], reverse=True)
    recent_h2h = [{
        "fecha": row["_date"].isoformat(),
        "local": row["home"], "visitante": row["away"],
        "goles_local": row["home_score"], "goles_visitante": row["away_score"],
    } for row in head_to_head[:5]]

    quality = "exploratoria"
    warnings = [
        "Modelo entrenado con los partidos finalizados de la temporada seleccionada.",
        "rho es un parámetro de corrección inicial, no calibrado para esta liga.",
        "Las probabilidades no están validadas fuera de muestra.",
    ]
    if xg_used:
        warnings.append("Lambda combina xG reciente de StatsBomb (65%) y tasas de goles reales (35%).")
    else:
        warnings.append("No hubo al menos tres partidos xG disponibles para cada condición; se usó el respaldo basado en marcadores.")
    warnings.append("Todavía no incorpora alineaciones, lesiones, clima, cuotas ni mercados de remates/córners/tarjetas.")
    if home_sample < 4 or away_sample < 4:
        warnings.append("Uno de los equipos tiene menos de cuatro partidos de local/visitante en el histórico.")
    if len(rows) >= 80 and home_sample >= 8 and away_sample >= 8:
        quality = "experimental_con_muestra_amplia"

    percent = lambda value: round(value * 100, 2)
    return {
        "fuente_historica": "StatsBomb Open Data",
        "modelo": "Poisson + corrección Dixon-Coles",
        "estado_validacion": quality,
        "metodo_tasas_goles": "xG reciente + goles reales" if xg_used else "goles reales con regularización",
        "partido": {"local": home_actual, "visitante": away_actual},
        "muestra": {
            "partidos_finalizados": len(rows),
            "partidos_local_equipo_local": home_sample,
            "partidos_visitante_equipo_visitante": away_sample,
            "h2h_en_misma_competicion_temporada": len(head_to_head),
            "fecha_referencia": reference_date.isoformat(),
        },
        "goles_esperados": {
            "local": round(lambda_home, 3),
            "visitante": round(lambda_away, 3),
            "total": round(lambda_home + lambda_away, 3),
            "base_goles_local": round(lambda_home_score, 3),
            "base_goles_visitante": round(lambda_away_score, 3),
        },
        "xg_reciente": xg_rates if xg_used else None,
        "probabilidades_1x2_pct": {
            "local": percent(p_home), "empate": percent(p_draw), "visitante": percent(p_away),
        },
        "ambos_marcan_pct": {
            "si": percent(btts_yes), "no": percent(1 - btts_yes),
        },
        "totales_goles_pct": totals,
        "marcadores_mas_probables": [{
            "marcador": f"{home_goals}-{away_goals}", "probabilidad_pct": percent(probability),
        } for home_goals, away_goals, probability in scores],
        "h2h_reciente": recent_h2h,
        "parametros": {"rho": rho, "half_life_days": half_life_days, "prior_games": prior_games},
        "advertencias": warnings,
    }

def evaluate_walk_forward(
    matches: list[dict[str, Any]],
    min_train: int = 30,
    rho: float = -0.08,
) -> dict[str, Any]:
    """Evalúa predicciones cronológicas: cada partido usa solo resultados anteriores."""
    if not 20 <= min_train <= 500:
        raise ValueError("min_train debe estar entre 20 y 500.")
    if not -0.25 <= rho <= 0.25:
        raise ValueError("rho debe estar entre -0.25 y 0.25.")

    prepared = []
    for raw in matches:
        if not isinstance(raw, dict):
            continue
        match_date = _parse_date(raw.get("match_date"))
        if match_date is None:
            continue
        try:
            home_score = int(raw["home_score"])
            away_score = int(raw["away_score"])
        except (KeyError, TypeError, ValueError):
            continue
        if home_score < 0 or away_score < 0:
            continue
        home = _team_name(raw.get("home_team"))
        away = _team_name(raw.get("away_team"))
        if not home or not away:
            continue
        prepared.append({
            **raw,
            "_parsed_date": match_date,
            "home_score": home_score,
            "away_score": away_score,
        })

    prepared.sort(key=lambda item: (
        item["_parsed_date"],
        str(item.get("kick_off") or ""),
        int(item.get("match_id") or 0),
    ))

    predictions = []
    skipped_insufficient = 0
    skipped_unmodelled = 0
    for index, target in enumerate(prepared):
        target_date = target["_parsed_date"]
        # Exclusión de todo el día objetivo para impedir fuga temporal.
        train = [
            row for row in prepared[:index]
            if row["_parsed_date"] < target_date
        ]
        if len(train) < min_train:
            skipped_insufficient += 1
            continue
        try:
            prediction = predict_from_matches(
                train,
                _team_name(target.get("home_team")),
                _team_name(target.get("away_team")),
                rho=rho,
            )
        except ValueError:
            skipped_unmodelled += 1
            continue

        probabilities = prediction["probabilidades_1x2_pct"]
        p_home = probabilities["local"] / 100.0
        p_draw = probabilities["empate"] / 100.0
        p_away = probabilities["visitante"] / 100.0
        actual = (
            0 if target["home_score"] > target["away_score"]
            else 1 if target["home_score"] == target["away_score"]
            else 2
        )
        vector = [1.0 if actual == outcome else 0.0 for outcome in range(3)]
        probs = [p_home, p_draw, p_away]
        brier = sum((probs[i] - vector[i]) ** 2 for i in range(3))
        logloss = -math.log(max(1e-15, probs[actual]))
        predicted = max(range(3), key=lambda i: probs[i])
        predictions.append({
            "fecha": target_date.isoformat(),
            "local": _team_name(target.get("home_team")),
            "visitante": _team_name(target.get("away_team")),
            "probabilidades": probabilities,
            "resultado_real": ("local", "empate", "visitante")[actual],
            "resultado_estimado": ("local", "empate", "visitante")[predicted],
            "acierto": predicted == actual,
            "brier": brier,
            "log_loss": logloss,
        })

    count = len(predictions)
    if count == 0:
        return {
            "modelo": "Poisson + Dixon-Coles",
            "metodo": "walk-forward cronológico sin datos del día objetivo",
            "estado": "muestra_insuficiente",
            "partidos_evaluados": 0,
            "min_train": min_train,
            "partidos_saltados_muestra": skipped_insufficient,
            "partidos_saltados_equipos": skipped_unmodelled,
            "metricas": None,
            "predicciones": [],
            "advertencia": "No hubo suficientes partidos anteriores para evaluar el modelo.",
        }

    avg_brier = sum(item["brier"] for item in predictions) / count
    avg_logloss = sum(item["log_loss"] for item in predictions) / count
    accuracy = sum(1 for item in predictions if item["acierto"]) / count

    # Calibración por rangos de la probabilidad del resultado elegido por el modelo.
    calibration = []
    for lower, upper in ((0.0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01)):
        bucket = []
        for item in predictions:
            selected_probability = max(item["probabilidades"].values()) / 100.0
            if lower <= selected_probability < upper:
                bucket.append(item)
        if bucket:
            calibration.append({
                "rango_probabilidad": f"{int(lower * 100)}-{min(100, int(upper * 100))}%",
                "partidos": len(bucket),
                "probabilidad_media_pct": round(
                    sum(max(item["probabilidades"].values()) for item in bucket) / len(bucket), 2
                ),
                "aciertos_pct": round(
                    100 * sum(1 for item in bucket if item["acierto"]) / len(bucket), 2
                ),
            })

    if count < 30:
        status = "exploratorio_muestra_pequena"
        warning = "Menos de 30 predicciones fuera de muestra: las métricas son muy inestables."
    else:
        status = "backtest_fuera_de_muestra"
        warning = "Backtest cronológico de una sola competición/temporada; no demuestra rentabilidad ni generalización a otras temporadas."

    return {
        "modelo": "Poisson + corrección Dixon-Coles",
        "metodo": "walk-forward cronológico sin datos del día objetivo",
        "estado": status,
        "partidos_evaluados": count,
        "min_train": min_train,
        "partidos_saltados_muestra": skipped_insufficient,
        "partidos_saltados_equipos": skipped_unmodelled,
        "metricas": {
            "brier_multiclase": round(avg_brier, 5),
            "log_loss": round(avg_logloss, 5),
            "accuracy": round(accuracy * 100, 2),
            "accuracy_unidad": "porcentaje",
        },
        "calibracion": calibration,
        "predicciones": predictions[-100:],
        "advertencia": warning,
    }
