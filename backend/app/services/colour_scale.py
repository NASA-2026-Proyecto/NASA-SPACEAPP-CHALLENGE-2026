"""De color a valor: lee una barra de color continua y la invierte sobre una imagen.

Las visualizaciones de la NASA son imágenes; con su barra de color se recupera, píxel a
píxel, la posición en la escala (0 = extremo bajo, 1 = extremo alto).
"""

import numpy as np
from PIL import Image

_BORDER_JUMP = 60  # salto de color (suma RGB) que delata un borde y no la rampa
_BORDER_SEARCH = 8  # píxeles de cada extremo donde se busca el marco
_CHUNK = 20_000


def gradient_from_colour_bar(colour_bar: Image.Image) -> np.ndarray:
    """Colores de la rampa, del extremo bajo al alto, como matriz (n, 3) uint8.

    Lee la fila central de la franja horizontal opaca más ancha.
    """
    rgba = np.asarray(colour_bar.convert("RGBA"))
    opaque_rows = np.nonzero((rgba[..., 3] == 255).sum(axis=1) > rgba.shape[1] // 2)[0]
    if opaque_rows.size == 0:
        raise ValueError("La barra de color no tiene una franja opaca.")
    row = rgba[(opaque_rows.min() + opaque_rows.max()) // 2]
    columns = np.nonzero(row[:, 3] == 255)[0]
    gradient = row[columns.min() : columns.max() + 1, :3].copy()

    def jump(a: np.ndarray, b: np.ndarray) -> int:
        return int(np.abs(a.astype(int) - b.astype(int)).sum())

    # Quita el marco: si cerca de un extremo hay un salto brusco de color, lo que queda
    # fuera del salto no es rampa (puede ser más de un píxel, p. ej. dos blancos seguidos)
    for offset in range(_BORDER_SEARCH, 0, -1):
        if (
            len(gradient) > 2 * _BORDER_SEARCH
            and jump(gradient[-offset], gradient[-offset - 1]) > _BORDER_JUMP
        ):
            gradient = gradient[:-offset]
            break
    for offset in range(_BORDER_SEARCH, 0, -1):
        if len(gradient) > 2 * _BORDER_SEARCH and jump(gradient[offset - 1], gradient[offset]) > _BORDER_JUMP:
            gradient = gradient[offset:]
            break
    if len(gradient) < 16:
        raise ValueError("La barra de color es demasiado corta para ser una rampa.")
    return gradient


def invert_gradient(image: Image.Image, gradient: np.ndarray, max_distance: float = 12.0) -> np.ndarray:
    """Posición de cada píxel en la rampa (0..1), con forma (alto, ancho).

    Los píxeles a más de `max_distance` (unidades RGB) de cualquier color de la rampa
    (costas, fronteras, logotipos, rótulos) quedan como NaN. El umbral es estricto a
    propósito: una línea negra suavizada sobre naranja da un marrón parecido al extremo
    alto de la rampa, y con un umbral holgado se leería como contaminación extrema.
    """
    rgb = np.asarray(image.convert("RGB")).reshape(-1, 3).astype(np.int32)
    keys = (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2]
    unique, inverse = np.unique(keys, return_inverse=True)
    colours = np.stack([(unique >> 16) & 255, (unique >> 8) & 255, unique & 255], axis=1)
    reference = gradient.astype(np.float32)
    position = np.empty(len(unique), dtype=np.float32)
    for start in range(0, len(unique), _CHUNK):  # por trozos, para acotar la memoria
        chunk = colours[start : start + _CHUNK].astype(np.float32)
        distance = np.sqrt(((chunk[:, None, :] - reference[None, :, :]) ** 2).sum(axis=-1))
        nearest = distance.argmin(axis=1)
        position[start : start + _CHUNK] = np.where(
            distance[np.arange(len(chunk)), nearest] <= max_distance,
            nearest / (len(gradient) - 1),
            np.nan,
        )
    return position[inverse].reshape(image.height, image.width)


def _valid_mean(blocks: np.ndarray, axis: tuple[int, ...]) -> np.ndarray:
    """Media ignorando NaN; NaN si no hay ningún valor válido."""
    valid = np.isfinite(blocks)
    count = valid.sum(axis=axis)
    total = np.where(valid, blocks, 0.0).sum(axis=axis)
    return np.where(count > 0, total / np.maximum(count, 1), np.nan).astype(np.float32)


def downsample(values: np.ndarray, factor: int) -> np.ndarray:
    """Reduce una matriz 2D promediando bloques de factor x factor (ignora los NaN)."""
    rows, cols = values.shape
    if rows % factor or cols % factor:
        raise ValueError(f"El tamaño {values.shape} no es divisible por {factor}.")
    blocks = values.reshape(rows // factor, factor, cols // factor, factor)
    return _valid_mean(blocks, axis=(1, 3))


def fill_small_gaps(values: np.ndarray) -> np.ndarray:
    """Rellena cada NaN con la media de sus 8 vecinos válidos (una pasada).

    Cierra líneas finas (costas, fronteras). Los huecos grandes (logotipo, rótulo de
    fecha) solo se estrechan una celda por lado: ahí no hay dato y no se inventa.
    """
    padded = np.pad(values, 1, constant_values=np.nan)
    rows, cols = values.shape
    neighbours = np.stack(
        [padded[dr : dr + rows, dc : dc + cols] for dr in range(3) for dc in range(3) if (dr, dc) != (1, 1)]
    )
    return np.where(np.isfinite(values), values, _valid_mean(neighbours, axis=(0,)))


def drop_islands(values: np.ndarray, window: int = 9, min_valid: float = 0.5) -> np.ndarray:
    """Descarta las celdas válidas rodeadas sobre todo de huecos.

    Dentro de un logotipo o de un rótulo, las letras pueden tener un color de la rampa
    por casualidad: son islas de "dato" en medio de un hueco, y no son dato.
    """
    valid = np.isfinite(values).astype(np.float32)
    half = window // 2
    padded = np.pad(valid, half, mode="edge")
    # Suma por ventana con una imagen integral
    integral = np.pad(padded.cumsum(axis=0).cumsum(axis=1), ((1, 0), (1, 0)))
    rows, cols = values.shape
    total = (
        integral[window : window + rows, window : window + cols]
        - integral[:rows, window : window + cols]
        - integral[window : window + rows, :cols]
        + integral[:rows, :cols]
    )
    return np.where(total / window**2 >= min_valid, values, np.nan).astype(np.float32)


def _window_extreme(values: np.ndarray, reducer, fill: float) -> np.ndarray:
    """Mínimo o máximo en la ventana de 3 x 3 de cada celda (los bordes se repiten)."""
    padded = np.pad(values, 1, mode="edge")
    rows, cols = values.shape
    result = np.full(values.shape, fill, dtype=np.float32)
    for dr in range(3):
        for dc in range(3):
            result = reducer(result, padded[dr : dr + rows, dc : dc + cols])
    return result


def reject_thin_features(position: np.ndarray, threshold: float = 0.08) -> np.ndarray:
    """Convierte en NaN los rasgos brillantes de menos de 3 píxeles de ancho.

    Las costas y fronteras son líneas negras semitransparentes: sobre un naranja dan un
    marrón que SÍ está en la rampa (su extremo alto es el mismo tono, más oscuro), así
    que por color no se distinguen de contaminación alta. Por forma sí: se comparan los
    valores con su "apertura" morfológica (erosión y dilatación de 3 x 3), que borra lo
    que es más estrecho que 3 píxeles y deja intacto lo demás. El campo del modelo es
    suave a esa escala; un pico real de 1-2 píxeles también se descartaría.
    """
    eroded = _window_extreme(np.where(np.isfinite(position), position, np.inf), np.minimum, np.inf)
    opened = _window_extreme(np.where(np.isfinite(eroded), eroded, -np.inf), np.maximum, -np.inf)
    return np.where(position - opened > threshold, np.nan, position).astype(np.float32)


def max_pool(values: np.ndarray, factor: int) -> np.ndarray:
    """Reduce una matriz 2D quedándose con el máximo de cada bloque de factor x factor.

    Para datos puntuales (un incendio ocupa pocos píxeles): la media los diluiría.
    """
    rows, cols = values.shape
    if rows % factor or cols % factor:
        raise ValueError(f"El tamaño {values.shape} no es divisible por {factor}.")
    return values.reshape(rows // factor, factor, cols // factor, factor).max(axis=(1, 3))
