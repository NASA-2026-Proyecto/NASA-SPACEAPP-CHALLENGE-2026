"""La descripción de la malla de un episodio (solo necesita numpy: se ejecuta siempre)."""

import numpy as np
import pytest

from geosfp.grid import describe_grid, regular_step


def test_regular_step():
    assert regular_step(np.array([-10.0, -8.75, -7.5]), "lon") == pytest.approx(1.25)


@pytest.mark.parametrize(
    "axis",
    [np.array([1.0]), np.array([3.0, 2.0, 1.0]), np.array([0.0, 1.0, 3.0]), np.array([2.0, 2.0])],
    ids=["un solo valor", "descendente", "paso irregular", "paso cero"],
)
def test_irregular_axes_are_rejected(axis):
    with pytest.raises(ValueError, match="no es regular y ascendente"):
        regular_step(axis, "lat")


def test_grid_description_matches_the_api_format():
    grid = describe_grid(np.array([34.0, 35.0, 36.0]), np.array([-10.0, -8.75, -7.5, -6.25]))
    assert (grid.lat_min, grid.lat_step, grid.n_lat) == (34.0, 1.0, 3)
    assert (grid.lon_min, grid.lon_step, grid.n_lon) == (-10.0, 1.25, 4)
    assert grid.lon_periodic is False  # un recorte regional no da la vuelta al globo

    world = describe_grid(np.arange(-90.0, 91.0, 1.0), np.arange(-180.0, 180.0, 1.25))
    assert world.lon_periodic is True
