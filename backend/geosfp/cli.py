"""Piezas comunes de los scripts de `tools/`: tipos de argumento de argparse y logging."""

import argparse
import logging
from collections.abc import Sequence
from datetime import UTC, datetime

REGION_METAVAR = ("LAT_MIN", "LAT_MAX", "LON_MIN", "LON_MAX")

# Errores previstos (datos, argumentos, red, archivos): un script los muestra sin traza
EXPECTED_ERRORS = (ValueError, RuntimeError, OSError)


def utc_datetime(text: str) -> datetime:
    """Convierte un argumento de fecha ISO 8601 en un instante UTC.

    Sirve como `type=` de argparse. Sin zona horaria se entiende que es UTC.

    Args:
        text: Fecha y, opcionalmente, hora: "2026-07-24", "2026-07-24T01:00",
            "2026-07-24T01:00Z" o con desfase ("2026-07-24T03:00+02:00").

    Returns:
        El instante, con zona horaria UTC.

    Raises:
        argparse.ArgumentTypeError: Si el texto no es una fecha ISO 8601.
    """
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"fecha no válida: {text!r} (se esperaba p. ej. 2026-07-24T01:00)"
        ) from exc
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def region_from_bounds(bounds: Sequence[float]) -> dict[str, slice]:
    """Convierte los límites de un rectángulo en un recorte por coordenadas.

    Args:
        bounds: Cuatro grados decimales: latitud mínima, latitud máxima, longitud
            mínima y longitud máxima (longitudes de -180 a 180).

    Returns:
        El recorte `{"lat": slice(mín, máx), "lon": slice(mín, máx)}`, con los
        extremos incluidos.

    Raises:
        ValueError: Si no son cuatro números o algún mínimo no es menor que su máximo.
    """
    if len(bounds) != 4:
        raise ValueError(f"Una región son cuatro números ({' '.join(REGION_METAVAR)}), no {len(bounds)}.")
    lat_min, lat_max, lon_min, lon_max = bounds
    if lat_min >= lat_max or lon_min >= lon_max:
        raise ValueError(f"Región vacía: {list(bounds)} (el orden es {' '.join(REGION_METAVAR)}).")
    return {"lat": slice(lat_min, lat_max), "lon": slice(lon_min, lon_max)}


def configure_logging(level: int = logging.INFO) -> None:
    """Muestra por la consola los mensajes de progreso de `geosfp` (solo el texto).

    Del resto de bibliotecas solo se muestran los avisos y los errores.
    """
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logging.getLogger("geosfp").setLevel(level)
