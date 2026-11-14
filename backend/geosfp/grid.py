import numpy as np


def regular_step(axis: np.ndarray, name: str) -> float:
    steps = np.diff(axis.astype("float64"))
    if steps.size == 0 or steps[0] <= 0 or not np.allclose(steps, steps[0], rtol=0, atol=1e-6):
        raise ValueError(f"El eje '{name}' no es regular y ascendente.")
    return float(steps[0])


def describe_grid(lat: np.ndarray, lon: np.ndarray) -> dict:
    lat_step = regular_step(lat, "lat")
    lon_step = regular_step(lon, "lon")
    return {
        "lat_min": float(lat[0]), "lat_step": lat_step,
        "lon_min": float(lon[0]), "lon_step": lon_step,
        "n_lat": int(lat.size), "n_lon": int(lon.size),
        "lon_periodic": bool(np.isclose(lon_step * lon.size, 360.0)),
        "reference": "values at the listed grid coordinates",
        "order": "[step][lat][lon], row-major; lat south to north, lon west to east",
    }