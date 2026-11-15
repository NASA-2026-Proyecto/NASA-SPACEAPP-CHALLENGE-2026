"""Un servidor GEOS-FP de mentira: los tests no tocan la red."""

import re
import struct
from urllib.parse import unquote

import numpy as np

from app.services.geosfp import GeosFpClient

URL = "https://example.test/geosfp/aer"

# Malla pequeña con la misma forma que la real (0,25° x 0,3125°), recortada
DAS = """Attributes {
    lon {
        String grads_dim "x";
        String grads_size "16";
        Float64 minimum -180.00000000000;
        Float32 resolution 22.5;
    }
    lat {
        String grads_dim "y";
        String grads_size "9";
        Float64 minimum -90.00000000000;
        Float32 resolution 22.5;
    }
    time {
        String grads_dim "t";
        String grads_size "%(n_times)d";
        String grads_min "01:30z27feb2026";
        String grads_step "180mn";
        Float32 resolution 0.125;
    }
    duexttau {
        Float32 _FillValue 1.0E15;
    }
}
"""


def dods(values: np.ndarray) -> bytes:
    header = b"Dataset {\n    Grid { ... } var;\n} /fake;\nData:\n"
    count = values.size
    return header + struct.pack(">II", count, count) + values.astype(">f4").tobytes() + b"maps"


class FakeGeosFp:
    """Responde a .das y .dods. Cada valor codifica su variable, paso, fila y columna."""

    def __init__(self, n_times: int = 10) -> None:
        self.n_times = n_times
        self.fail = False
        self.bad_value: float | None = None
        self.requests: list[str] = []

    def get(self, url: str) -> bytes:
        self.requests.append(url)
        if self.fail:
            raise TimeoutError("NASA no responde")
        if url.endswith(".das"):
            return (DAS % {"n_times": self.n_times}).encode()
        query = unquote(url.split(".dods?", 1)[1])
        name, t0, t1, y_step, y_last, x_step, x_last = re.fullmatch(
            r"(\w+)\[(\d+):(\d+)\]\[0:(\d+):(\d+)\]\[0:(\d+):(\d+)\]", query
        ).groups()
        steps = np.arange(int(t0), int(t1) + 1)[:, None, None]
        rows = np.arange(0, int(y_last) + 1, int(y_step))[None, :, None]
        cols = np.arange(0, int(x_last) + 1, int(x_step))[None, None, :]
        values = (len(name) + steps * 0.1 + rows * 0.01 + cols * 0.0001).astype("float32")
        if self.bad_value is not None:
            values[0, 0, 0] = self.bad_value
        return dods(values)

    def client(self) -> GeosFpClient:
        return GeosFpClient(url=URL, get=self.get)
