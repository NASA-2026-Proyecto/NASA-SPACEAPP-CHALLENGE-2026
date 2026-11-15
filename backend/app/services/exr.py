"""Lectura de imágenes OpenEXR (el formato de los fotogramas de algunas visualizaciones de SVS)."""

import tempfile
from pathlib import Path

import numpy as np
import numpy.typing as npt
import OpenEXR


def read_rgb(data: bytes) -> npt.NDArray[np.float32]:
    """Devuelve los canales RGB de un EXR con forma (alto, ancho, 3).

    Los valores son lineales (sin corrección gamma). La biblioteca solo lee de disco,
    así que los bytes pasan por un archivo temporal.

    Raises:
        ValueError: Si la imagen no tiene canales de color.
    """
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "frame.exr"
        path.write_bytes(data)
        with OpenEXR.File(str(path)) as exr:
            channels = exr.parts[0].channels
            # La biblioteca agrupa R, G, B (y A) en un solo canal cuando están los tres
            for name in ("RGBA", "RGB"):
                if name in channels:
                    return np.asarray(channels[name].pixels[..., :3], dtype=np.float32)
    raise ValueError(f"El EXR no tiene canales RGB (tiene {sorted(channels)}).")
