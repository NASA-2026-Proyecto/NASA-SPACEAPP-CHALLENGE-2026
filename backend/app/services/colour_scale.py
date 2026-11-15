"""De color a valor: lee una barra de color y la invierte sobre una imagen.

Las visualizaciones de la NASA son imágenes; con su barra de color se recupera, píxel a
píxel, la posición en la escala (0 = extremo bajo, 1 = extremo alto) si la barra es
continua, o la clase si va por tramos de color uniforme. El resto de las funciones
limpian y reducen la matriz resultante.
"""

import numpy as np
import numpy.typing as npt
from PIL import Image

type FloatArray = npt.NDArray[np.float32]
type Ramp = npt.NDArray[np.uint8]  # colores de la barra, forma (n, 3)

_BORDER_JUMP = 60  # salto de color (suma RGB) que delata un borde y no la rampa
_BORDER_SEARCH = 8  # píxeles de cada extremo donde se busca el marco
# Colores que se comparan a la vez con la rampa. Cada tanda crea una matriz temporal de
# tanda x colores de la rampa x 3: con 2.000 son unos 10 MB (con 20.000 pasaba de 250 MB).
_CHUNK = 2_000
_MIN_RUN = 3  # píxeles seguidos del mismo color para contar como tramo de una barra
_BLACK = 30  # suma RGB por debajo de la cual un tramo es un separador negro


def _colour_jump(a: npt.NDArray[np.uint8], b: npt.NDArray[np.uint8]) -> int:
    """Diferencia entre dos colores: suma de las diferencias de sus tres canales."""
    return int(np.abs(a.astype(int) - b.astype(int)).sum())


def _bar_row(colour_bar: Image.Image) -> Ramp:
    """Colores de la fila central de la franja horizontal opaca más ancha de la imagen.

    Raises:
        ValueError: Si la imagen no tiene una franja opaca.
    """
    rgba = np.asarray(colour_bar.convert("RGBA"))
    opaque_rows = np.nonzero((rgba[..., 3] == 255).sum(axis=1) > rgba.shape[1] // 2)[0]
    if opaque_rows.size == 0:
        raise ValueError("La barra de color no tiene una franja opaca.")
    row = rgba[(opaque_rows.min() + opaque_rows.max()) // 2]
    columns = np.nonzero(row[:, 3] == 255)[0]
    colours: Ramp = row[columns.min() : columns.max() + 1, :3].copy()
    return colours


def classes_from_colour_bar(colour_bar: Image.Image) -> Ramp:
    """Colores de una barra por tramos (cada clase, un color uniforme), del bajo al alto.

    Incluye las flechas de los extremos ("por debajo" y "por encima" de la escala) cuando
    tienen color propio. Los separadores negros y los tramos de menos de 3 píxeles se
    descartan, y dos tramos seguidos del mismo color cuentan como uno.

    Raises:
        ValueError: Si la imagen no tiene una franja opaca.
    """
    row = _bar_row(colour_bar)
    # Inicio de cada tramo de color uniforme, y el final del último
    starts = np.concatenate([[0], np.nonzero((row[1:] != row[:-1]).any(axis=1))[0] + 1, [len(row)]])
    classes: list[npt.NDArray[np.uint8]] = []
    for start, end in zip(starts[:-1], starts[1:], strict=True):
        colour = row[start]
        if end - start < _MIN_RUN or int(colour.sum()) <= _BLACK:
            continue
        if not classes or (classes[-1] != colour).any():
            classes.append(colour)
    return np.array(classes, dtype=np.uint8).reshape(-1, 3)


def gradient_from_colour_bar(colour_bar: Image.Image) -> Ramp:
    """Colores de la rampa, del extremo bajo al alto.

    Lee la fila central de la franja horizontal opaca más ancha y le quita el marco.

    Raises:
        ValueError: Si la imagen no tiene una franja opaca o la rampa es demasiado corta.
    """
    gradient = _bar_row(colour_bar)

    # Quita el marco: si cerca de un extremo hay un salto brusco de color, lo que queda
    # fuera del salto no es rampa (puede ser más de un píxel, p. ej. dos blancos seguidos)
    for offset in range(_BORDER_SEARCH, 0, -1):
        long_enough = len(gradient) > 2 * _BORDER_SEARCH
        if long_enough and _colour_jump(gradient[-offset], gradient[-offset - 1]) > _BORDER_JUMP:
            gradient = gradient[:-offset]
            break
    for offset in range(_BORDER_SEARCH, 0, -1):
        long_enough = len(gradient) > 2 * _BORDER_SEARCH
        if long_enough and _colour_jump(gradient[offset - 1], gradient[offset]) > _BORDER_JUMP:
            gradient = gradient[offset:]
            break
    if len(gradient) < 16:
        raise ValueError("La barra de color es demasiado corta para ser una rampa.")
    return gradient


def invert_gradient(image: Image.Image, gradient: Ramp, max_distance: float = 12.0) -> FloatArray:
    """Posición de cada píxel en la rampa (0..1), con forma (alto, ancho).

    Los píxeles a más de `max_distance` (unidades RGB) de cualquier color de la rampa
    (costas, fronteras, logotipos, rótulos) quedan como NaN. El umbral es estricto a
    propósito: una línea negra suavizada sobre naranja da un marrón parecido al extremo
    alto de la rampa, y con un umbral holgado se leería como contaminación extrema.
    """
    rgb = np.asarray(image.convert("RGB")).reshape(-1, 3).astype(np.int32)
    keys = (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2]
    # Se compara cada color distinto una sola vez (una imagen repite mucho sus colores)
    unique, inverse = np.unique(keys, return_inverse=True)
    colours = np.stack([(unique >> 16) & 255, (unique >> 8) & 255, unique & 255], axis=1)
    reference = gradient.astype(np.float32)
    position = np.empty(len(unique), dtype=np.float32)
    for start in range(0, len(unique), _CHUNK):
        chunk = colours[start : start + _CHUNK].astype(np.float32)
        distance = np.sqrt(((chunk[:, None, :] - reference[None, :, :]) ** 2).sum(axis=-1))
        nearest = distance.argmin(axis=1)
        position[start : start + _CHUNK] = np.where(
            distance[np.arange(len(chunk)), nearest] <= max_distance,
            nearest / (len(gradient) - 1),
            np.nan,
        )
    return position[inverse].reshape(image.height, image.width)


def _valid_mean(blocks: FloatArray, axis: tuple[int, ...]) -> FloatArray:
    """Media ignorando NaN; NaN si no hay ningún valor válido."""
    valid = np.isfinite(blocks)
    count = valid.sum(axis=axis)
    total = np.where(valid, blocks, 0.0).sum(axis=axis)
    return np.where(count > 0, total / np.maximum(count, 1), np.nan).astype(np.float32)


def _blocks(values: FloatArray, factor: int) -> FloatArray:
    """Reordena una matriz 2D en bloques de factor x factor: forma (filas, factor, columnas, factor)."""
    rows, cols = values.shape
    if rows % factor or cols % factor:
        raise ValueError(f"El tamaño {values.shape} no es divisible por {factor}.")
    return values.reshape(rows // factor, factor, cols // factor, factor)


def downsample(values: FloatArray, factor: int) -> FloatArray:
    """Reduce una matriz 2D promediando bloques de factor x factor (ignora los NaN).

    Raises:
        ValueError: Si el tamaño de la matriz no es divisible por `factor`.
    """
    return _valid_mean(_blocks(values, factor), axis=(1, 3))


def max_pool(values: FloatArray, factor: int) -> FloatArray:
    """Reduce una matriz 2D quedándose con el máximo de cada bloque de factor x factor.

    Para datos puntuales (un incendio ocupa pocos píxeles): la media los diluiría.

    Raises:
        ValueError: Si el tamaño de la matriz no es divisible por `factor`.
    """
    pooled: FloatArray = _blocks(values, factor).max(axis=(1, 3))
    return pooled


def fill_small_gaps(values: FloatArray) -> FloatArray:
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


def drop_islands(values: FloatArray, window: int = 9, min_valid: float = 0.5) -> FloatArray:
    """Descarta las celdas válidas rodeadas sobre todo de huecos.

    Dentro de un logotipo o de un rótulo, las letras pueden tener un color de la rampa
    por casualidad: son islas de "dato" en medio de un hueco, y no son dato.

    Args:
        values: Matriz 2D con NaN en los huecos.
        window: Lado de la ventana cuadrada que se mira alrededor de cada celda.
        min_valid: Fracción mínima de celdas válidas en la ventana para conservar la celda.
    """
    valid = np.isfinite(values).astype(np.float32)
    padded = np.pad(valid, window // 2, mode="edge")
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


def _window_extreme(values: FloatArray, *, largest: bool) -> FloatArray:
    """Máximo (o mínimo) en la ventana de 3 x 3 de cada celda; los bordes se repiten."""
    padded = np.pad(values, 1, mode="edge")
    rows, cols = values.shape
    result: FloatArray = padded[1 : 1 + rows, 1 : 1 + cols]
    for dr in range(3):
        for dc in range(3):
            window = padded[dr : dr + rows, dc : dc + cols]
            result = np.maximum(result, window) if largest else np.minimum(result, window)
    return result


def reject_thin_features(position: FloatArray, threshold: float = 0.08) -> FloatArray:
    """Convierte en NaN los rasgos brillantes de menos de 3 píxeles de ancho.

    Las costas y fronteras son líneas negras semitransparentes: sobre un naranja dan un
    marrón que SÍ está en la rampa (su extremo alto es el mismo tono, más oscuro), así
    que por color no se distinguen de contaminación alta. Por forma sí: se comparan los
    valores con su "apertura" morfológica (erosión y dilatación de 3 x 3), que borra lo
    que es más estrecho que 3 píxeles y deja intacto lo demás. El campo del modelo es
    suave a esa escala; un pico real de 1-2 píxeles también se descartaría.
    """
    # Los NaN no cuentan: valen +inf al buscar mínimos y -inf al buscar máximos
    eroded = _window_extreme(np.where(np.isfinite(position), position, np.inf), largest=False)
    opened = _window_extreme(np.where(np.isfinite(eroded), eroded, -np.inf), largest=True)
    return np.where(position - opened > threshold, np.nan, position).astype(np.float32)
