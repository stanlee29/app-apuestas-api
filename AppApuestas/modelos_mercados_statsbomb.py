"""Modelos de conteo para mercados estadísticos de fútbol con StatsBomb Open Data.

Las estimaciones usan partidos anteriores a la fecha objetivo y eventos históricos
publicados por StatsBomb. No son cuotas de casas ni un modelo validado en producción.
"""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import date
from typing import Any

from statsbomb_open_data import StatsBombDataError, StatsBombOpenData


MARKETS: dict[str, dict[str, Any]] = {
    "remates": {
        "nombre": "Remates totales",
        "metric": "shots",
        "team_lines": [7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5],
        "total_lines": [17.5, 19.5, 21.5, 23.5, 25.5, 27.5, 29.5],
    },
    "remates_a_puerta": {
        "nombre": "Remates a puerta",
        "metric": "shots_on_target",
        "team_lines": [1.5, 2.5, 3.5, 4.5, 5.5],
        "total_lines": [4.5, 5.5, 6.5, 7.5, 8.5, 9.5],
    },
    "corners": {
        "nombre": "Córners",
        "metric": "corners",
        "team_lines": [2.5, 3.5, 4.5, 5.5, 6.5],
        "total_lines": [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5],
    },
    "faltas": {
        "nombre": "Faltas cometidas",
        "metric": "fouls",
        "team_lines": [7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5, 14.5],
        "total_lines": [17.5, 19.5, 21.5, 23.5, 25.5, 27.5, 29.5],
    },
    "tarjetas_amarillas": {
        "nombre": "Tarjetas amarillas",
        "metric": "yellow_cards",
        "team_lines": [0.5, 1.5, 2.5, 3.5],
        "total_lines": [1.5, 2.5, 3.5, 4.5, 5.5],
    },
    "tarjetas_totales": {
        "nombre": "Tarjetas totales (amarillas + rojas)",
        "metric": "total_cards",
        "team_lines": [0.5, 1.5, 2.5, 3.5],
        "total_lines": [1.5, 2.5, 3.5, 4.5, 5.5],
    },
}


def _name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("home_team_name") or value.get("away_team_name") or "")
    return str(value or "")


def _normalise(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", normalized.casefold())


def _match_team_name(match: dict[str, Any], side: str) -> str:
    value = _name(match.get(f"{side}_team"))
    if value:
        return value
    return str(match.get(f"{side}_team_name") or "")


def _card_name(value: Any) -> str:
    return _name(value).casefold()


def extract_match_counts(
    events: list[dict[str, Any]],
    home_team: str,
    away_team: str,
) -> dict[str, dict[str, int]]:
    """Cuenta métricas de evento para ambos equipos en un partido."""
    result = {
        home_team: {
            "shots": 0,
            "shots_on_target": 0,
            "corners": 0,
            "fouls": 0,
            "yellow_cards": 0,
            "red_cards": 0,
            "total_cards": 0,
        },
        away_team: {
            "shots": 0,
            "shots_on_target": 0,
            "corners": 0,
            "fouls": 0,
            "yellow_cards": 0,
            "red_cards": 0,
            "total_cards": 0,
        },
    }
    team_lookup = {_normalise(home_team): home_team, _normalise(away_team): away_team}

    for event in events:
        if not isinstance(event, dict):
            continue
        raw_team = _name(event.get("team"))
        team = team_lookup.get(_normalise(raw_team))
        if team is None:
            continue

        event_type = _name(event.get("type")).casefold()
        if event_type == "shot":
            result[team]["shots"] += 1
            shot = event.get("shot") or {}
            outcome = _name(shot.get("outcome")).casefold() if isinstance(shot, dict) else ""
            if outcome in {"goal", "saved", "saved to post"}:
                result[team]["shots_on_target"] += 1

        elif event_type == "pass":
            pass_data = event.get("pass") or {}
            if isinstance(pass_data, dict) and _name(pass_data.get("type")).casefold() == "corner":
                result[team]["corners"] += 1

        elif event_type == "foul committed":
            result[team]["fouls"] += 1
            foul_data = event.get("foul_committed") or {}
            card = _card_name(foul_data.get("card")) if isinstance(foul_data, dict) else ""
            if "yellow" in card:
                result[team]["yellow_cards"] += 1
            elif "red" in card:
                result[team]["red_cards"] += 1

        elif event_type == "bad behaviour":
            bad_behaviour = event.get("bad_behaviour") or {}
            card = _card_name(bad_behaviour.get("card")) if isinstance(bad_behaviour, dict) else ""
            if "yellow" in card:
                result[team]["yellow_cards"] += 1
            elif "red" in card:
                result[team]["red_cards"] += 1

    for values in result.values():
        values["total_cards"] = values["yellow_cards"] + values["red_cards"]
    return result


def _weighted_mean(values: list[float], decay: float = 0.90) -> float:
    if not values:
        return 0.0
    weights = [decay ** index for index in range(len(values))]
    denominator = sum(weights)
    return sum(value * weight for value, weight in zip(values, weights)) / denominator


def _sample_variance(values: list[float]) -> float:
    if len(values) < 2:
        return max(0.0, values[0] if values else 0.0)
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def build_count_pmf(mean: float, variance: float) -> tuple[list[float], str]:
    """Construye Poisson o binomial negativa por momentos y normaliza la cola."""
    mean = max(0.0, float(mean))
    variance = max(0.0, float(variance))
    if mean <= 1e-12:
        return [1.0], "Poisson"

    use_negative_binomial = variance > mean + 0.10
    if use_negative_binomial:
        dispersion = max(0.20, min(1000.0, mean * mean / (variance - mean)))
        probability = dispersion / (dispersion + mean)
        distribution = "Binomial negativa"
    else:
        dispersion = 0.0
        probability = 0.0
        distribution = "Poisson"

    max_count = min(150, max(25, int(math.ceil(mean + 12 * math.sqrt(max(variance, mean, 1.0)) + 12))))
    pmf: list[float] = []
    for count in range(max_count + 1):
        if use_negative_binomial:
            log_p = (
                math.lgamma(count + dispersion)
                - math.lgamma(dispersion)
                - math.lgamma(count + 1)
                + dispersion * math.log(probability)
                + count * math.log1p(-probability)
            )
        else:
            log_p = count * math.log(mean) - mean - math.lgamma(count + 1)
        pmf.append(math.exp(log_p))

    total = sum(pmf)
    if total <= 0 or not math.isfinite(total):
        raise ValueError("No fue posible construir la distribución de conteo.")
    return [value / total for value in pmf], distribution


def _convolve(first: list[float], second: list[float]) -> list[float]:
    combined = [0.0] * (len(first) + len(second) - 1)
    for i, p_first in enumerate(first):
        if p_first == 0:
            continue
        for j, p_second in enumerate(second):
            combined[i + j] += p_first * p_second
    total = sum(combined)
    return [value / total for value in combined] if total else [1.0]


def _line_probabilities(pmf: list[float], lines: list[float]) -> list[dict[str, float]]:
    results = []
    for line in lines:
        over = sum(probability for count, probability in enumerate(pmf) if count > line)
        over = min(1.0, max(0.0, over))
        results.append({
            "linea": line,
            "over_pct": round(over * 100, 2),
            "under_pct": round((1.0 - over) * 100, 2),
        })
    return results


def _market_side(
    attack_values: list[float],
    conceded_values: list[float],
    lines: list[float],
) -> tuple[dict[str, Any], list[float], str]:
    attack_mean = _weighted_mean(attack_values)
    conceded_mean = _weighted_mean(conceded_values)
    expected = max(0.0, (attack_mean + conceded_mean) / 2.0)
    variance = _sample_variance(attack_values + conceded_values)
    pmf, distribution = build_count_pmf(expected, variance)
    return ({
        "media_esperada": round(expected, 2),
        "media_propia_reciente": round(attack_mean, 2),
        "media_concedida_por_rival": round(conceded_mean, 2),
        "muestra_propia": len(attack_values),
        "muestra_concedida": len(conceded_values),
        "distribucion": distribution,
        "lineas": _line_probabilities(pmf, lines),
    }, pmf, distribution)


def predict_match_markets(
    statsbomb: StatsBombOpenData,
    all_matches: list[dict[str, Any]],
    target_date: str,
    home_team_name: str,
    away_team_name: str,
    limit: int = 8,
) -> dict[str, Any]:
    """Estima líneas de remates, tiros a puerta, córners, faltas y tarjetas.

    La fecha objetivo y los partidos posteriores se excluyen estrictamente.
    Para cada equipo se usa su muestra más reciente en la condición relevante:
    local en casa y visitante fuera. La media esperada combina producción propia
    y conteo concedido por el rival.
    """
    if not 4 <= limit <= 12:
        raise ValueError("La ventana histórica debe estar entre 4 y 12 partidos.")
    target = date.fromisoformat(target_date)
    if not home_team_name.strip() or not away_team_name.strip():
        raise ValueError("Debes indicar equipo local y visitante.")
    home_key, away_key = _normalise(home_team_name), _normalise(away_team_name)
    if not home_key or home_key == away_key:
        raise ValueError("Los equipos deben ser distintos.")

    historical = StatsBombOpenData.matches_before_date(all_matches, target.isoformat())
    completed = []
    for match in historical:
        if not isinstance(match, dict):
            continue
        if match.get("home_score") is None or match.get("away_score") is None:
            continue
        status = str(match.get("match_status") or "").casefold()
        if status and status not in {"available", "played", "complete", "completed"}:
            continue
        home = _match_team_name(match, "home")
        away = _match_team_name(match, "away")
        if home and away:
            completed.append(match)
    completed.sort(key=lambda row: str(row.get("match_date") or ""), reverse=True)

    home_candidates = [
        row for row in completed if _normalise(_match_team_name(row, "home")) == home_key
    ]
    away_candidates = [
        row for row in completed if _normalise(_match_team_name(row, "away")) == away_key
    ]

    cache: dict[int, dict[str, dict[str, int]] | None] = {}
    skipped = 0

    def get_counts(match: dict[str, Any]) -> dict[str, dict[str, int]] | None:
        nonlocal skipped
        try:
            match_id = int(match.get("match_id") or 0)
        except (TypeError, ValueError):
            skipped += 1
            return None
        if match_id <= 0:
            skipped += 1
            return None
        if match_id not in cache:
            home = _match_team_name(match, "home")
            away = _match_team_name(match, "away")
            try:
                events = statsbomb._json(f"events/{match_id}.json", ttl=24 * 60 * 60)
                if not isinstance(events, list) or not events:
                    cache[match_id] = None
                else:
                    cache[match_id] = extract_match_counts(events, home, away)
            except StatsBombDataError:
                cache[match_id] = None
            if cache[match_id] is None:
                skipped += 1
        return cache[match_id]

    home_rows: list[tuple[dict[str, int], dict[str, int]]] = []
    for match in home_candidates:
        if len(home_rows) >= limit:
            break
        counts = get_counts(match)
        if counts is None:
            continue
        home = _match_team_name(match, "home")
        away = _match_team_name(match, "away")
        home_rows.append((counts[home], counts[away]))

    away_rows: list[tuple[dict[str, int], dict[str, int]]] = []
    for match in away_candidates:
        if len(away_rows) >= limit:
            break
        counts = get_counts(match)
        if counts is None:
            continue
        home = _match_team_name(match, "home")
        away = _match_team_name(match, "away")
        away_rows.append((counts[away], counts[home]))

    if len(home_rows) < 3 or len(away_rows) < 3:
        raise ValueError(
            "Muestra insuficiente de eventos StatsBomb: se necesitan al menos 3 partidos "
            "válidos del local jugando en casa y 3 del visitante jugando fuera. "
            f"Disponibles: local={len(home_rows)}, visitante={len(away_rows)}."
        )

    markets: dict[str, Any] = {}
    distributions: dict[str, tuple[list[float], str]] = {}
    for key, config in MARKETS.items():
        metric = str(config["metric"])
        home_attack = [float(own[metric]) for own, _ in home_rows]
        home_conceded = [float(opponent[metric]) for _, opponent in away_rows]
        away_attack = [float(own[metric]) for own, _ in away_rows]
        away_conceded = [float(opponent[metric]) for _, opponent in home_rows]

        home_payload, home_pmf, home_distribution = _market_side(
            home_attack, home_conceded, config["team_lines"]
        )
        away_payload, away_pmf, away_distribution = _market_side(
            away_attack, away_conceded, config["team_lines"]
        )
        total_mean = home_payload["media_esperada"] + away_payload["media_esperada"]
        total_pmf = _convolve(home_pmf, away_pmf)
        markets[key] = {
            "nombre": config["nombre"],
            "unidad": "conteo",
            "local": home_payload,
            "visitante": away_payload,
            "total_partido": {
                "media_esperada": round(total_mean, 2),
                "distribucion": f"Convolución ({home_distribution} + {away_distribution})",
                "lineas": _line_probabilities(total_pmf, config["total_lines"]),
            },
        }

    minimum_sample = min(len(home_rows), len(away_rows))
    quality = "exploratoria_muestra_pequena" if minimum_sample < 6 else "experimental_muestra_amplia"
    warnings = [
        "Solo se usan eventos de partidos finalizados anteriores a la fecha objetivo; se excluyen el mismo día y fechas futuras.",
        "La tasa esperada combina la producción reciente del equipo con lo que concede el rival en su condición local/visitante.",
        "Poisson se sustituye por binomial negativa cuando la varianza histórica supera la media.",
        "El total del partido se calcula por convolución, suponiendo independencia entre los conteos de ambos equipos.",
        "Las líneas son referencias analíticas; no representan cuotas disponibles ni recomendaciones de apuesta.",
        "No hay validación fuera de muestra de estos mercados; revisar calibración antes de considerar uso operativo.",
    ]
    if minimum_sample < 6:
        warnings.append("La muestra es pequeña; interpretar las probabilidades como exploratorias.")
    if skipped:
        warnings.append(f"Se omitieron {skipped} partidos cuyos eventos no estaban disponibles o no pudieron leerse.")

    return {
        "fuente": "StatsBomb Open Data",
        "atribucion_requerida": "StatsBomb",
        "modelo": "Poisson / Binomial negativa por momentos",
        "estado_validacion": quality,
        "fecha_objetivo": target.isoformat(),
        "regla_temporal": "Solo partidos anteriores a la fecha objetivo; el día objetivo queda excluido.",
        "partido": {"local": home_team_name, "visitante": away_team_name},
        "muestra": {
            "local_en_casa": len(home_rows),
            "visitante_fuera": len(away_rows),
            "ventana_solicitada_por_equipo": limit,
            "partidos_omitidos": skipped,
        },
        "mercados": markets,
        "advertencias": warnings,
    }
