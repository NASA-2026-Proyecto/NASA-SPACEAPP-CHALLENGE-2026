"""Comprobación de los valores descargados de GEOS-FP (cálculo puro, solo numpy)."""

import numpy as np
import numpy.typing as npt

from app.services.geosfp import FILL_LIMIT


def count_invalid(values: npt.NDArray[np.floating]) -> int:
    """Cuenta las celdas sin dato: no finitas o con el valor de relleno del servidor.

    El servidor marca los huecos con 1e15; se considera hueco todo valor desde
    `FILL_LIMIT` en adelante.
    """
    return int((~np.isfinite(values) | (values >= FILL_LIMIT)).sum())


def require_valid(name: str, values: npt.NDArray[np.floating]) -> None:
    """Exige que una variable no tenga celdas sin dato.

    Args:
        name: Nombre de la variable, para el mensaje de error.
        values: Valores descargados.

    Raises:
        ValueError: Si alguna celda no es finita o trae el valor de relleno.
    """
    invalid = count_invalid(values)
    if invalid:
        raise ValueError(f"{name}: contiene valores no válidos ({invalid} de {values.size} celdas).")
