"""Descripción de la malla de un recorte de GEOS-FP a partir de sus ejes de coordenadas."""

import numpy as np
import numpy.typing as npt

from app.schemas import GridBlock
from app.services.scenes import grid_block

AXIS_TOLERANCE = 1e-6  # diferencia admitida entre pasos consecutivos de un eje regular


def regular_step(axis: npt.NDArray[np.floating], name: str) -> float:
    """Paso de un eje de coordenadas regular y ascendente.

    Args:
        axis: Coordenadas del eje (latitudes o longitudes).
        name: Nombre del eje, para el mensaje de error.

    Raises:
        ValueError: Si el eje tiene menos de dos valores, no asciende o su paso no es constante.
    """
    steps = np.diff(axis.astype("float64"))
    regular = steps.size > 0 and steps[0] > 0 and np.allclose(steps, steps[0], rtol=0, atol=AXIS_TOLERANCE)
    if not regular:
        raise ValueError(f"El eje '{name}' no es regular y ascendente.")
    return float(steps[0])


def describe_grid(lat: npt.NDArray[np.floating], lon: npt.NDArray[np.floating]) -> GridBlock:
    """Malla de una escena a partir de sus latitudes (sur a norte) y longitudes (oeste a este).

    Raises:
        ValueError: Si alguno de los ejes no es regular y ascendente.
    """
    return grid_block(
        lat_min=float(lat[0]),
        lat_step=regular_step(lat, "lat"),
        lon_min=float(lon[0]),
        lon_step=regular_step(lon, "lon"),
        n_lat=int(lat.size),
        n_lon=int(lon.size),
    )
