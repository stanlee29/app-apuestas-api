"""Descarga manual del dataset abierto de marcadores schoChastics/football-data.

Ejecutar desde AppApuestas: python scripts/download_open_football_results.py
La descarga es voluntaria; no se ejecuta al iniciar Render.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import requests


DATA_URL = "https://raw.githubusercontent.com/schochastics/football-data/master/data/results/games.parquet"
ATTRIBUTION = """Dataset: schoChastics/football-data
Repositorio: https://github.com/schochastics/football-data
Licencia: Open Data Commons Attribution License (ODC-BY)
Cobertura publicada: resultados de 1888 a 2023.
Este conjunto contiene marcadores finales; no contiene xG, remates, eventos ni datos en vivo.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Descarga el parquet de resultados históricos de fútbol.")
    parser.add_argument(
        "--output",
        default="datos/open_football/games.parquet",
        help="Ruta destino del archivo parquet.",
    )
    args = parser.parse_args()
    destination = Path(args.output).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    response = requests.get(DATA_URL, stream=True, timeout=(15, 90))
    response.raise_for_status()
    total = 0
    try:
        with temporary.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
                    total += len(chunk)
        if total < 1_000_000:
            raise RuntimeError("La descarga es demasiado pequeña; no se reemplazó el archivo final.")
        temporary.replace(destination)
        destination.with_suffix(".ATTRIBUTION.txt").write_text(ATTRIBUTION, encoding="utf-8")
    finally:
        if temporary.exists():
            temporary.unlink()
    print(f"Dataset guardado en {destination} ({total:,} bytes)")
    print(ATTRIBUTION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
