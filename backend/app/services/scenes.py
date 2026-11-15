"""Escenas: el formato común con el que los datos en malla llegan al front.

Una escena es un manifiesto (`app.schemas.Manifest`) más un .f32 por especie: float32
little-endian en orden [paso][lat][lon], de sur a norte y de oeste a este.

Cada fuente (GEOS-FP, visualizaciones diarias del EIC...) sabe comprobar si hay datos
nuevos y construir su escena (`SceneSource`). `SceneStore` guarda la escena en memoria
y la renueva en segundo plano: ningún clic del usuario espera a la NASA.

La escena vive en la memoria de este proceso. Con varias réplicas, cada una tendría la
suya (y podrían no coincidir durante una actualización): hoy la API está pensada para
una sola instancia.
"""

import hashlib
import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from app.schemas import GridBlock, Manifest, ProvenanceValue, Scale, SpeciesEntry, TimeAxis

logger = logging.getLogger(__name__)

type FloatArray = npt.NDArray[np.float32]

GRID_REFERENCE = "values at the listed grid coordinates"
GRID_ORDER = "[step][lat][lon], row-major; lat south to north, lon west to east"


@dataclass(frozen=True)
class Scene:
    """Una escena lista para servir."""

    version: str  # forma parte de la URL de los .f32, que así se pueden cachear
    manifest: Manifest
    files: dict[str, bytes]  # "<especie>.f32" -> valores


class SceneSource[ContextT](Protocol):
    """Origen de una escena: sabe si hay datos nuevos y cómo construirla.

    `ContextT` es lo que `check()` averigua y `build()` necesita (por ejemplo, la malla
    y el eje de tiempo actuales), para no pedirlo dos veces.
    """

    @property
    def scene_id(self) -> str:
        """Identificador de la escena en la URL (p. ej. "aerosol-latest")."""
        ...

    def check(self) -> tuple[str, ContextT]:
        """Consulta barata: versión disponible en origen y lo necesario para construirla."""
        ...

    def build(self, version: str, context: ContextT) -> Scene:
        """Descarga los datos y construye la escena. Puede tardar decenas de segundos."""
        ...


def stamp(moment: datetime) -> str:
    """Instante en el formato de los manifiestos: 2026-11-14T13:30Z."""
    return f"{moment:%Y-%m-%dT%H:%M}Z"


def version_of(moment: datetime) -> str:
    """Versión de una escena a partir del instante de sus datos: 20261114T1330Z."""
    return f"{moment:%Y%m%dT%H%MZ}"


def grid_block(
    lat_min: float, lat_step: float, lon_min: float, lon_step: float, n_lat: int, n_lon: int
) -> GridBlock:
    """Describe una malla regular a partir de su primera celda, sus pasos y su tamaño."""
    return GridBlock(
        lat_min=lat_min,
        lat_step=lat_step,
        lon_min=lon_min,
        lon_step=lon_step,
        n_lat=n_lat,
        n_lon=n_lon,
        lon_periodic=bool(np.isclose(lon_step * n_lon, 360.0)),
        reference=GRID_REFERENCE,
        order=GRID_ORDER,
    )


def whole_globe_grid(n_lat: int, n_lon: int) -> GridBlock:
    """Malla de una imagen que cubre todo el globo (de -90 a 90 y de -180 a 180).

    Los valores están en el centro de cada celda, así que la primera latitud y la
    primera longitud quedan media celda dentro del borde.
    """
    lat_step, lon_step = 180.0 / n_lat, 360.0 / n_lon
    return grid_block(-90.0 + lat_step / 2, lat_step, -180.0 + lon_step / 2, lon_step, n_lat, n_lon)


def time_axis(moments: Sequence[datetime], step_minutes: int, note: str) -> TimeAxis:
    """Eje de tiempo de una escena a partir de los instantes de sus pasos, en orden."""
    return TimeAxis(
        steps=len(moments),
        step_minutes=step_minutes,
        stamps_utc=[stamp(moment) for moment in moments],
        note=note,
    )


def encode_species(
    version: str,
    key: str,
    values: FloatArray,
    *,
    source_variable: str,
    unit: str,
    display_scale_max: float,
    display_scale_method: str,
    long_name: str | None = None,
    missing: str | None = None,
    scale: Scale | None = None,
) -> tuple[bytes, SpeciesEntry]:
    """Serializa una especie y devuelve (bytes del .f32, su entrada del manifiesto).

    Args:
        version: Versión de la escena; va en la ruta del archivo.
        key: Identificador de la especie (p. ej. "dust").
        values: Valores con forma (pasos, latitudes, longitudes).
        source_variable: Nombre de la variable en origen.
        unit: Unidad de los valores.
        display_scale_max: Valor con el que el front satura el color.
        display_scale_method: Cómo se eligió ese valor.
        long_name: Descripción larga, si la hay.
        missing: Cómo se marcan los huecos, si puede haberlos.
        scale: Escala de color original, si el front debe pintar con ella.
    """
    data = np.ascontiguousarray(values, dtype="<f4").tobytes()
    entry = SpeciesEntry(
        source_variable=source_variable,
        long_name=long_name,
        unit=unit,
        missing=missing,
        file=f"{version}/{key}.f32",
        sha256=hashlib.sha256(data).hexdigest(),
        min=float(np.nanmin(values)),
        max=float(np.nanmax(values)),
        scale=scale,
        display_scale_max=display_scale_max,
        display_scale_method=display_scale_method,
    )
    return data, entry


def build_manifest(
    *,
    scene_id: str,
    version: str,
    layer: str,
    provenance: dict[str, ProvenanceValue],
    time: TimeAxis,
    grid: GridBlock,
    species: dict[str, SpeciesEntry],
) -> Manifest:
    """Monta el manifiesto de una escena; es el único sitio donde se construye."""
    return Manifest(
        scene_id=scene_id,
        version=version,
        generated_utc=stamp(datetime.now(UTC)),
        layer=layer,
        provenance=provenance,
        time=time,
        grid=grid,
        species=species,
    )


def _spawn_thread(task: Callable[[], None]) -> None:
    """Ejecuta `task` en un hilo que no impide cerrar el proceso."""
    threading.Thread(target=task, name="scene-refresh", daemon=True).start()


class SceneStore[ContextT]:
    """Guarda la escena actual de una fuente y la renueva cuando en origen hay una versión nueva.

    La renovación es perezosa: se lanza en segundo plano cuando alguien pide la escena y
    ha pasado el intervalo de comprobación. Nunca hay dos renovaciones a la vez.

    Conserva también la escena anterior: un navegador que ya tenía el manifiesto viejo
    puede terminar de descargar sus .f32 aunque haya habido una actualización entre medias.
    """

    def __init__(
        self,
        source: SceneSource[ContextT],
        *,
        check_seconds: float = 900.0,
        retry_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        spawn: Callable[[Callable[[], None]], None] = _spawn_thread,
    ) -> None:
        """Crea el almacén, aún sin escena.

        Args:
            source: De dónde sale la escena.
            check_seconds: Cada cuánto se comprueba si hay una versión nueva.
            retry_seconds: Cuánto se espera para reintentar tras un fallo.
            clock: Reloj monótono, en segundos (se sustituye en los tests).
            spawn: Cómo ejecutar la renovación en segundo plano (se sustituye en los tests).
        """
        self._source = source
        self._check_seconds = check_seconds
        self._retry_seconds = retry_seconds
        self._clock = clock
        self._spawn = spawn
        self._lock = threading.Lock()
        self._refreshing = False
        self._next_check = 0.0
        self._current: Scene | None = None
        self._previous: Scene | None = None
        self._error: str | None = None

    @property
    def scene_id(self) -> str:
        """Identificador de la escena que guarda."""
        return self._source.scene_id

    @property
    def error(self) -> str | None:
        """Motivo del último fallo al renovar, o None si la última renovación fue bien."""
        with self._lock:
            return self._error

    def get(self) -> Scene | None:
        """Devuelve la escena disponible (o None) sin esperar; lanza la renovación si toca."""
        if self._claim(only_if_due=True):
            try:
                self._spawn(self._run)
            except Exception:
                logger.exception("No se pudo lanzar la renovación de la escena %s", self.scene_id)
                self._release(self._retry_seconds)
        with self._lock:
            return self._current

    def scene(self, version: str) -> Scene | None:
        """La escena de esa versión, si es la actual o la anterior; None si no."""
        with self._lock:
            scenes = (self._current, self._previous)
        for scene in scenes:
            if scene is not None and scene.version == version:
                return scene
        return None

    def file(self, version: str, name: str) -> bytes | None:
        """Bytes de un archivo de la escena actual o de la anterior; None si no existe."""
        scene = self.scene(version)
        return None if scene is None else scene.files.get(name)

    def refresh(self) -> bool:
        """Renueva la escena ahora mismo, esperando a que termine.

        Returns:
            False si ya había una renovación en marcha (y por tanto no se ha hecho otra).
        """
        if not self._claim(only_if_due=False):
            return False
        self._run()
        return True

    def _claim(self, *, only_if_due: bool) -> bool:
        """Reserva el turno de renovación; False si está ocupado o aún no toca."""
        with self._lock:
            if self._refreshing or (only_if_due and self._clock() < self._next_check):
                return False
            self._refreshing = True
            return True

    def _release(self, delay: float) -> None:
        """Libera el turno y fija cuándo se vuelve a comprobar."""
        with self._lock:
            self._next_check = self._clock() + delay
            self._refreshing = False

    def _run(self) -> None:
        """Comprueba si hay una versión nueva y, si la hay, construye la escena."""
        delay = self._retry_seconds
        try:
            version, context = self._source.check()
            with self._lock:
                current = self._current
            if current is None or current.version != version:
                scene = self._source.build(version, context)
                with self._lock:
                    self._previous, self._current = current, scene
                logger.info("Escena %s lista: %s", self.scene_id, scene.version)
            with self._lock:
                self._error = None
            delay = self._check_seconds
        except Exception as error:  # la NASA falla a ratos: se conserva la escena anterior
            logger.warning("No se pudo renovar la escena %s: %r", self.scene_id, error)
            with self._lock:
                self._error = f"{type(error).__name__}: {error}"
        finally:
            self._release(delay)


# Almacenes de la aplicación, por identificador de escena (cada uno con su tipo de contexto)
type SceneStores = dict[str, SceneStore[Any]]
