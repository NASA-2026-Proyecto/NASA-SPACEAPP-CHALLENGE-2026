# /// script
# requires-python = ">=3.13"
# dependencies = ["h5py", "numpy"]
# ///
"""Prepara la cabeza del sonido 3D: las direcciones de KEMAR que usa la API.

    uv run tools/build_head.py <mit_kemar_normal_pinna.sofa>

El archivo SOFA son las respuestas al impulso de una cabeza de maniquí (KEMAR) medidas en
710 direcciones por el MIT Media Lab: W. G. Gardner y K. D. Martin, "HRTF measurements of
a KEMAR", J. Acoust. Soc. Am. 97, 1995. Se distribuye sin restricciones de uso, con el
ruego de citar ese trabajo: https://sofacoustics.org/data/database/mit/

De ahí se guardan solo las direcciones de un anillo alrededor del oyente, inclinado: el
norte queda delante y arriba, el sur detrás y abajo, el este a la derecha. La API lee ese
anillo de `app/services/sound/kemar_ring.npz` (unos 50 kB) y no necesita ni el SOFA ni h5py.
"""

import sys
from pathlib import Path

import h5py
import numpy as np

RING = 12  # direcciones alrededor del oyente: una cada 30°
TILT = 40.0  # grados que sube el norte y baja el sur (KEMAR no tiene medidas por debajo de -40°)
OUTPUT = Path(__file__).parent.parent / "app" / "services" / "sound" / "kemar_ring.npz"


def unit(azimuth: np.ndarray, elevation: np.ndarray) -> np.ndarray:
    """Vector unitario de una dirección SOFA (azimut 0 = delante, 90 = izquierda; elevación 90 = arriba)."""
    az, el = np.radians(azimuth), np.radians(elevation)
    return np.stack([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)], axis=-1)


def main(sofa: Path) -> None:
    """Lee el SOFA, elige la medida más cercana a cada dirección del anillo y guarda el resultado."""
    with h5py.File(sofa, "r") as file:
        hrir = file["Data.IR"][:]  # (direcciones, 2 oídos, muestras); oído 0 = izquierdo
        position = file["SourcePosition"][:]  # azimut, elevación, radio
        sample_rate = int(np.ravel(file["Data.SamplingRate"][:])[0])

    # Nivel de referencia: una fuente de potencia 1 llega a los dos oídos con potencia 1, de media
    hrir = hrir / np.sqrt((hrir**2).sum(axis=(1, 2)).mean())

    bearings = np.arange(RING) * 360 / RING  # 0 = norte, en sentido horario
    wanted = unit((360 - bearings) % 360, TILT * np.cos(np.radians(bearings)))
    nearest = np.argmax(unit(position[:, 0], position[:, 1]) @ wanted.T, axis=0)

    np.savez_compressed(
        OUTPUT,
        hrir=hrir[nearest].astype(np.float32),
        bearings=bearings.astype(np.float32),
        azimuths=position[nearest, 0].astype(np.float32),
        elevations=position[nearest, 1].astype(np.float32),
        sample_rate=sample_rate,
    )
    for bearing, (azimuth, elevation, _) in zip(bearings, position[nearest], strict=True):
        print(f"rumbo {bearing:5.1f}° -> medida en azimut {azimuth:5.1f}°, elevación {elevation:+5.1f}°")
    print(f"{OUTPUT} ({OUTPUT.stat().st_size / 1000:.0f} kB, {sample_rate} Hz, {hrir.shape[-1]} muestras)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
