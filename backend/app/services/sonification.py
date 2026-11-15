"""Del clic al sonido: lee un punto en una escena y lo convierte en audio.

Cada sonido (`SOUNDS`) pertenece a una especie de una escena. `Sonifier.read()` lee el
dato del punto en el paso más reciente y dice qué se va a oír, sin generar nada;
`Sonifier.render()` genera el WAV. El audio es determinista (misma escena, mismo punto =
mismo archivo), así que su URL lleva la versión de la escena y se puede cachear.

Hay dos modos. En estéreo suena el dato del punto, en el paso más reciente. En binaural
(tres dimensiones, para auriculares) suena todo el entorno del punto (`survey`), cada
celda desde su rumbo y su distancia, a lo largo de todos los pasos de la serie.

Generar un sonido cuesta en torno a un segundo de CPU y más de 100 MB de memoria, y la
API es una sola instancia: por eso solo se generan unos pocos a la vez.
"""

import dataclasses
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any, Protocol

import numpy as np

from app.schemas import GridBlock, SoundMode, SoundParameter, SoundReading
from app.services.fire_scene import FireSource
from app.services.pm25_scene import Pm25Source
from app.services.precipitation_scene import PrecipitationSource
from app.services.scenes import Scene, SceneStores
from app.services.sound import air, fire, rain
from app.services.sound.common import (
    EARTH_RADIUS_KM,
    SECONDS,
    TAIL,
    PointSample,
    Surroundings,
    great_circle,
)
from app.services.sound.dsp import Signal, wav_bytes

BEARINGS = 32  # direcciones alrededor del punto: una cada 11,25°
RING_SAMPLES = 12  # puntos que se leen en cada dirección, entre la distancia cercana y la lejana
COORDINATE_DECIMALS = 4  # ~10 m: de sobra para volver a caer en la misma celda
NO_DATA_TEXT = "La imagen de la NASA no tiene dato en este punto: lo tapa un logotipo o un rótulo."


class UnknownSoundError(LookupError):
    """No existe un sonido con ese identificador."""


class SceneNotReadyError(RuntimeError):
    """La escena del sonido aún se está preparando."""


class NoAudioError(LookupError):
    """No hay audio para esa versión o ese punto."""


class BusyError(RuntimeError):
    """Ya se están generando todos los sonidos que caben a la vez."""


class SoundParameters(Protocol):
    """Los parámetros de un sonido: un dataclass con, al menos, la intensidad."""

    @property
    def intensity(self) -> float:
        """De 0 a 1: el número del que cuelgan los demás parámetros."""
        ...


@dataclass(frozen=True)
class Spatial[P: SoundParameters]:
    """La versión en tres dimensiones de un sonido: suena el entorno del punto, no solo el punto.

    Attributes:
        mapping: Del entorno a los parámetros que dan el timbre del conjunto.
        describe: Qué se oye, en palabras.
        synthesize: El audio.
        describe_absent: Qué se dice donde el dato es cero en todo el entorno y en todos
            los pasos, y por tanto no suena nada; None si el sonido existe también así.
    """

    mapping: Callable[[Surroundings], P]
    describe: Callable[[Surroundings, P], str]
    synthesize: Callable[[Surroundings, P, int], Signal]
    describe_absent: Callable[[Surroundings], str] | None = None


@dataclass(frozen=True)
class Sound[P: SoundParameters]:
    """Un sonido: de qué dato sale y cómo se convierte en audio.

    Attributes:
        id: Identificador en la URL ("air").
        scene_id: Escena de la que se lee el dato.
        species: Especie de esa escena.
        unit: Unidad del dato, para mostrarlo.
        reach: Celdas a cada lado del punto que cuentan como "el punto"; se toma el
            valor más alto. 0 = solo su celda.
        near_km: Distancia a la que empieza a leerse el entorno, en cada dirección.
        far_km: Distancia hasta la que se lee; en tres dimensiones, el radio del entorno.
        mapping: Del dato a los parámetros del sonido.
        describe: Qué se oye, en palabras.
        synthesize: El audio.
        describe_absent: Qué se dice donde el dato es cero y por tanto no suena nada;
            None si el sonido también existe con el dato a cero.
        spatial: Su versión en tres dimensiones; None si aún no la tiene.
    """

    id: str
    scene_id: str
    species: str
    unit: str
    reach: int
    near_km: float
    far_km: float
    mapping: Callable[[float], P]
    describe: Callable[[PointSample, P], str]
    synthesize: Callable[[PointSample, P, int], Signal]
    describe_absent: Callable[[PointSample], str] | None = None
    spatial: Spatial[P] | None = None


SOUNDS: Mapping[str, Sound[Any]] = {
    sound.id: sound
    for sound in (
        Sound(
            id="air",
            scene_id=Pm25Source.scene_id,
            species="pm25",
            unit=air.UNIT,
            reach=0,
            near_km=60,
            far_km=400,
            mapping=air.mapping,
            describe=air.describe,
            synthesize=air.synthesize,
        ),
        Sound(
            id="rain",
            scene_id=PrecipitationSource.scene_id,
            species="rain",
            unit=rain.UNIT,
            reach=0,
            near_km=40,
            far_km=300,
            mapping=rain.mapping,
            describe=rain.describe,
            synthesize=rain.synthesize,
            spatial=Spatial(rain.spatial_mapping, rain.describe_spatial, rain.synthesize_spatial),
        ),
        Sound(
            id="fire",
            scene_id=FireSource.scene_id,
            species="frp",
            unit=fire.UNIT,
            reach=1,  # el incendio más fuerte en las 3 x 3 celdas alrededor del punto
            near_km=60,
            far_km=400,
            mapping=fire.mapping,
            describe=fire.describe,
            synthesize=fire.synthesize,
            describe_absent=fire.describe_absent,
            spatial=Spatial(
                fire.spatial_mapping,
                fire.describe_spatial,
                fire.synthesize_spatial,
                fire.describe_absent_spatial,
            ),
        ),
    )
}


def cell_of(grid: GridBlock, lat: float, lon: float) -> tuple[int, int]:
    """Fila y columna de la celda de la malla que contiene un punto."""
    row = int(np.clip(round((lat - grid.lat_min) / grid.lat_step), 0, grid.n_lat - 1))
    col = round((lon - grid.lon_min) / grid.lon_step) % grid.n_lon
    return row, col


def sample_point(sound: Sound[Any], scene: Scene, lat: float, lon: float) -> PointSample:
    """Lee en el paso más reciente de la escena lo que el sonido necesita de un punto.

    El punto se lleva al centro de su celda. El entorno se lee en `BEARINGS` direcciones,
    sin contar la celda del propio punto; en una dirección sin ningún dato (un logotipo)
    cuenta el valor del punto.
    """
    manifest = scene.manifest
    grid = manifest.grid
    field = np.frombuffer(scene.files[f"{sound.species}.f32"], dtype="<f4").reshape(
        manifest.time.steps, grid.n_lat, grid.n_lon
    )[-1]
    row, col = cell_of(grid, lat, lon)
    centre_lat = grid.lat_min + row * grid.lat_step
    centre_lon = grid.lon_min + col * grid.lon_step

    rows = np.clip(np.arange(row - sound.reach, row + sound.reach + 1), 0, grid.n_lat - 1)
    cols = np.arange(col - sound.reach, col + sound.reach + 1) % grid.n_lon
    here = float(field[np.ix_(rows, cols)].max())

    bearings = np.arange(BEARINGS) * 360 / BEARINGS  # 0 = norte, en sentido horario
    distances = np.linspace(sound.near_km, sound.far_km, RING_SAMPLES)
    lats, lons = great_circle(centre_lat, centre_lon, bearings[:, None], distances[None, :])
    ring_rows = np.clip(np.round((lats - grid.lat_min) / grid.lat_step).astype(int), 0, grid.n_lat - 1)
    ring_cols = np.round((lons - grid.lon_min) / grid.lon_step).astype(int) % grid.n_lon
    ring = field[ring_rows, ring_cols].astype(np.float64)
    # La celda del propio punto es "el punto", no su entorno
    known = np.isfinite(ring) & ~((ring_rows == row) & (ring_cols == col))
    around = np.where(known, ring, 0.0).sum(axis=1) / np.maximum(known.sum(axis=1), 1)
    around = np.where(known.any(axis=1), around, here)

    return PointSample(
        lat=round(centre_lat, COORDINATE_DECIMALS),
        lon=round(centre_lon, COORDINATE_DECIMALS),
        value=here,
        bearings=bearings,
        around=around,
        stamp=manifest.time.stamps_utc[-1],
    )


def survey(sound: Sound[Any], scene: Scene, lat: float, lon: float) -> Surroundings:
    """Lee el entorno de un punto en todos los pasos de la escena: cada celda hasta `far_km`.

    De cada celda se guarda su rumbo y su distancia desde el centro de la celda del
    punto (por el círculo máximo) y su valor en cada paso; lo que no tiene dato cuenta
    como cero.
    """
    manifest = scene.manifest
    grid = manifest.grid
    field = np.frombuffer(scene.files[f"{sound.species}.f32"], dtype="<f4").reshape(
        manifest.time.steps, grid.n_lat, grid.n_lon
    )
    row, col = cell_of(grid, lat, lon)
    centre_lat = grid.lat_min + row * grid.lat_step
    centre_lon = grid.lon_min + col * grid.lon_step

    # La ventana de celdas que puede caer dentro del radio. Los meridianos se juntan hacia
    # los polos: el radio abarca más columnas cuanto más alta es la latitud, y todas si
    # alcanza el polo
    angle = sound.far_km / EARTH_RADIUS_KM
    reach_rows = int(np.ceil(np.degrees(angle) / grid.lat_step))
    widening = np.sin(angle) / max(float(np.cos(np.radians(centre_lat))), 1e-9)
    spread = 180.0 if widening >= 1 else float(np.degrees(np.arcsin(widening)))
    columns = min(2 * int(np.ceil(spread / grid.lon_step)) + 1, grid.n_lon)
    rows = np.arange(max(row - reach_rows, 0), min(row + reach_rows, grid.n_lat - 1) + 1)
    offsets = np.arange(columns) - columns // 2

    here = np.radians(centre_lat)
    there = np.radians(grid.lat_min + rows * grid.lat_step)[:, None]
    east = np.radians(offsets * grid.lon_step)[None, :]
    half_chord = np.sin((there - here) / 2) ** 2 + np.cos(here) * np.cos(there) * np.sin(east / 2) ** 2
    km = 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(half_chord))
    bearing = np.degrees(
        np.arctan2(
            np.sin(east) * np.cos(there),
            np.cos(here) * np.sin(there) - np.sin(here) * np.cos(there) * np.cos(east),
        )
    )
    near = km <= sound.far_km
    values = field[:, rows][:, :, (col + offsets) % grid.n_lon][:, near]

    return Surroundings(
        lat=round(centre_lat, COORDINATE_DECIMALS),
        lon=round(centre_lon, COORDINATE_DECIMALS),
        bearing=bearing[near] % 360,
        km=km[near],
        values=np.nan_to_num(values.astype(np.float64)),
        stamps=tuple(manifest.time.stamps_utc),
        far_km=sound.far_km,
    )


def _plain(value: float | int | str | tuple[int, ...]) -> SoundParameter:
    """Un parámetro en tipos de JSON, con los decimales justos."""
    if isinstance(value, tuple):
        return [float(item) for item in value]
    return round(value, 4) if isinstance(value, float) else value


class Sonifier:
    """Convierte puntos de las escenas en sonido, con un tope de sonidos generándose a la vez."""

    def __init__(
        self, scenes: SceneStores, *, max_renders: int = 2, sounds: Mapping[str, Sound[Any]] = SOUNDS
    ) -> None:
        """Prepara el sonificador.

        Args:
            scenes: Almacenes de escenas de la aplicación.
            max_renders: Cuántos sonidos se pueden generar a la vez.
            sounds: Los sonidos que existen; solo se ofrecen los que tienen su escena.
        """
        self._scenes = scenes
        self._sounds = {key: sound for key, sound in sounds.items() if sound.scene_id in scenes}
        self._slots = threading.BoundedSemaphore(max_renders)

    def ids(self) -> list[str]:
        """Identificadores de los sonidos disponibles, en orden alfabético."""
        return sorted(self._sounds)

    def _sound(self, sound_id: str) -> Sound[Any]:
        """El sonido con ese identificador.

        Raises:
            UnknownSoundError: Si no existe.
        """
        try:
            return self._sounds[sound_id]
        except KeyError:
            raise UnknownSoundError(sound_id) from None

    def _reading(
        self, sound: Sound[Any], scene: Scene, lat: float, lon: float, mode: SoundMode
    ) -> tuple[SoundReading, Callable[[int], Signal] | None]:
        """Lo que se sabe del sonido de un punto y, si suena, la función que lo genera con una semilla."""
        sample = sample_point(sound, scene, lat, lon)
        spatial = sound.spatial if mode == "binaural" else None
        reading = partial(
            SoundReading,
            sound=sound.id,
            scene_id=sound.scene_id,
            version=scene.version,
            mode="stereo" if spatial is None else "binaural",
            stamp_utc=sample.stamp,
            lat=sample.lat,
            lon=sample.lon,
            unit=sound.unit,
        )
        if not np.isfinite(sample.value):
            return reading(status="no_data", description=NO_DATA_TEXT), None
        value = round(sample.value, 4)
        audio = f"{sound.id}/{scene.version}.wav?lat={sample.lat}&lon={sample.lon}"

        parameters: Any  # un dataclass de parámetros: cada sonido tiene el suyo
        if spatial is None:
            if sound.describe_absent is not None and sample.value <= 0:
                return reading(status="absent", value=value, description=sound.describe_absent(sample)), None
            parameters = sound.mapping(sample.value)
            description = sound.describe(sample, parameters)
            render = partial(sound.synthesize, sample, parameters)
        else:
            around = survey(sound, scene, lat, lon)
            if spatial.describe_absent is not None and around.values.max() <= 0:
                return reading(
                    status="absent", value=value, description=spatial.describe_absent(around)
                ), None
            parameters = spatial.mapping(around)
            description = spatial.describe(around, parameters)
            render = partial(spatial.synthesize, around, parameters)
            audio += "&mode=binaural"

        audible = reading(
            status="ok",
            value=value,
            intensity=round(parameters.intensity, 4),
            description=description,
            parameters={key: _plain(item) for key, item in dataclasses.asdict(parameters).items()},
            audio=audio,
            duration_s=SECONDS + TAIL,
        )
        return audible, render

    def read(self, sound_id: str, lat: float, lon: float, mode: SoundMode = "stereo") -> SoundReading:
        """Qué suena en un punto, sin generar el audio.

        Si se pide binaural y el sonido aún no lo tiene, la lectura es la del estéreo (y lo dice
        en `mode`).

        Raises:
            UnknownSoundError: Si el sonido no existe.
            SceneNotReadyError: Si su escena aún no está lista.
        """
        sound = self._sound(sound_id)
        scene = self._scenes[sound.scene_id].get()
        if scene is None:
            raise SceneNotReadyError(sound.scene_id)
        return self._reading(sound, scene, lat, lon, mode)[0]

    def render(
        self,
        sound_id: str,
        version: str,
        lat: float,
        lon: float,
        seed: int = 0,
        mode: SoundMode = "stereo",
    ) -> bytes:
        """El audio de un punto como archivo WAV (PCM de 16 bits, dos canales).

        Args:
            sound_id: Identificador del sonido.
            version: Versión de la escena con la que se genera (la actual o la anterior).
            lat: Latitud del punto.
            lon: Longitud del punto.
            seed: Semilla aleatoria; con la misma, el audio es idéntico.
            mode: stereo o binaural (el estéreo, si el sonido aún no tiene binaural).

        Raises:
            UnknownSoundError: Si el sonido no existe.
            NoAudioError: Si esa versión ya no está o en ese punto no suena nada.
            BusyError: Si ya se están generando todos los sonidos que caben a la vez.
        """
        sound = self._sound(sound_id)
        scene = self._scenes[sound.scene_id].scene(version)
        if scene is None:
            raise NoAudioError(f"versión {version} no disponible")
        _, synthesize = self._reading(sound, scene, lat, lon, mode)
        if synthesize is None:
            raise NoAudioError("en ese punto no suena nada")
        if not self._slots.acquire(blocking=False):
            raise BusyError(sound_id)
        try:
            return wav_bytes(synthesize(seed))
        finally:
            self._slots.release()
