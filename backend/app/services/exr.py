"""Lectura de imágenes OpenEXR (el formato de los fotogramas de algunas visualizaciones de SVS)."""

import tempfile
from pathlib import Path

import numpy as np
import OpenEXR


def read_rgb(data: bytes) -> np.ndarray:
    """Devuelve los canales RGB de un EXR como float32 con forma (alto, ancho, 3).

    Los valores son lineales (sin corrección gamma). La biblioteca solo lee de disco,
    así que los bytes pasan por un archivo temporal.
    """
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "frame.exr"
        path.write_bytes(data)
        with OpenEXR.File(str(path)) as exr:
            channels = exr.parts[0].channels
            if "RGBA" in channels:
                pixels = channels["RGBA"].pixels[..., :3]
            elif "RGB" in channels:
                pixels = channels["RGB"].pixels
            else:
                pixels = np.stack([channels[name].pixels for name in ("R", "G", "B")], axis=-1)
            return np.asarray(pixels, dtype=np.float32)
