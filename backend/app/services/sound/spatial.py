"""Sonido en tres dimensiones para auriculares: cada dato suena desde donde está.

El oyente está en el punto elegido, mirando al norte. Cada celda del entorno es una
fuente con su rumbo y su distancia reales:

- El rumbo se oye con las respuestas de una cabeza de maniquí (KEMAR, del MIT; ver
  `tools/build_head.py`): el sonido llega antes y más fuerte al oído de su lado, y la
  oreja lo colorea según venga de delante, de detrás, de arriba o de abajo. Hay 12
  rumbos, uno cada 30°, en un anillo inclinado: el norte queda delante y arriba, el sur
  detrás y abajo, para que se distingan lo más posible.
- La distancia se oye como en la calle: lo lejano llega más flojo (la mitad cada vez que
  se dobla la distancia), con menos agudos y con más sala que sonido directo.
- El tiempo: el sonido recorre los pasos de la serie, del más antiguo al más reciente, y
  se queda en el último. Lo que se mueve en el mapa se mueve en los oídos.

Para que cueste poco, las fuentes se suman en el dominio de la frecuencia: cada rumbo es
una señal a la que se aplica su respuesta una sola vez, y al final hay dos transformadas
inversas, una por oído. Todo va en precisión simple, de sobra para un WAV de 16 bits.
"""

import functools
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from app.services.sound import dsp
from app.services.sound.common import SECONDS, TAIL, Surroundings
from app.services.sound.dsp import SAMPLE_RATE, Signal

type Spectrum = npt.NDArray[np.complex64]
type Indices = npt.NDArray[np.intp]

N_SAMPLES = int((SECONDS + TAIL) * SAMPLE_RATE)
SWEEP_SECONDS = 9.0  # lo que tarda el sonido en recorrer la serie; luego se queda en el último paso
FAR_METRES = 8.0  # distancia a la que suena lo más lejano que se lee; lo cercano, a 1 m
DULL_HZ = 2500.0  # corte del filtro que apaga lo lejano
DULL_MIX = 0.8  # cuánto de lo más lejano pasa por ese filtro
ROOM_LEVEL = 0.2  # nivel de la sala respecto al sonido directo a 1 m; no cambia con la distancia
ROOM_DELAY_S = 0.01  # la sala llega después del sonido directo
BEARING_JITTER = 8.0  # grados que se mueve cada grano alrededor del rumbo de su celda
HEAD_FILE = Path(__file__).with_name("kemar_ring.npz")


@dataclass(frozen=True)
class Head:
    """La cabeza que escucha: su respuesta a cada rumbo del anillo.

    Attributes:
        bearings: Rumbos del anillo, en grados desde el norte y en sentido horario.
        spectra: Respuesta en frecuencia de cada rumbo en cada oído, con forma
            [rumbo, oído, frecuencia]; el oído 0 es el izquierdo.
    """

    bearings: Signal
    spectra: Spectrum


@functools.cache
def head() -> Head:
    """La cabeza KEMAR, lista para sonidos de `N_SAMPLES` muestras.

    Se prepara la primera vez que se pide y se queda en memoria (unos 64 MB): calcularla
    cuesta tanto como generar medio sonido.
    """
    with np.load(HEAD_FILE) as data:
        responses, bearings = data["hrir"], data["bearings"].astype(np.float64)
    spectra = np.fft.rfft(responses.astype(np.float32), N_SAMPLES, axis=-1)
    return Head(bearings, spectra.astype(np.complex64, copy=False))


@functools.cache
def _frequencies() -> Signal:
    """Las frecuencias de la transformada de un sonido completo."""
    return np.fft.rfftfreq(N_SAMPLES, 1 / SAMPLE_RATE)


def _spectrum(signal: Signal) -> Spectrum:
    """Transformada de una señal, rellenada con ceros hasta la duración del sonido."""
    return np.fft.rfft(signal.astype(np.float32), N_SAMPLES).astype(np.complex64, copy=False)


def grain_shape(grain: Signal, low_hz: float, high_hz: float) -> Spectrum:
    """La forma de un grano (una gota, un chasquido) filtrada entre dos cortes, en frecuencia."""
    return _spectrum(grain) * dsp.band_gain(_frequencies(), low_hz, high_hz).astype(np.float32)


def unit_noise(rng: np.random.Generator, exponent: float, low_hz: float, high_hz: float) -> Signal:
    """Ruido de potencia 1/f**exponent entre dos cortes, con RMS 1 y la duración del sonido.

    Sale con su color y su filtro de una sola transformada: el espectro se sortea ya con forma.
    """
    freqs = _frequencies()
    drawn = rng.standard_normal(freqs.size) + 1j * rng.standard_normal(freqs.size)
    shaped = drawn * dsp.band_gain(freqs, low_hz, high_hz) / np.maximum(freqs, freqs[1]) ** (exponent / 2)
    noise: Signal = np.fft.irfft(shaped.astype(np.complex64), N_SAMPLES).astype(np.float64)
    return noise / float(np.sqrt(np.mean(noise**2)))


def metres(km: Signal, near_km: float, far_km: float) -> Signal:
    """De kilómetros en el mapa a metros en los oídos: 1 m hasta `near_km`, `FAR_METRES` en `far_km`.

    Crece como el logaritmo de la distancia: cada vez que esta se multiplica, la fuente se
    aleja los mismos pasos.
    """
    along = np.clip(np.log(np.maximum(km, near_km) / near_km) / np.log(far_km / near_km), 0, 1)
    out: Signal = np.exp(along * np.log(FAR_METRES))
    return out


def position(seconds: Signal, steps: int) -> Signal:
    """En qué paso de la serie está el sonido en cada instante (con decimales entre dos pasos)."""
    out: Signal = np.clip(seconds / SWEEP_SECONDS, 0, 1) * (steps - 1)
    return out


def follow(per_step: Signal) -> Signal:
    """Un valor por paso de la serie, llevado con suavidad a cada muestra del sonido."""
    at = position(np.arange(N_SAMPLES) / SAMPLE_RATE, per_step.size)
    out: Signal = np.interp(at, np.arange(per_step.size), per_step)
    return out


@dataclass(frozen=True)
class Grains:
    """Granos sorteados: cuándo suena cada uno y de qué celda y qué paso de la serie sale."""

    seconds: Signal
    cell: Indices
    step: Indices


def draw_grains(rng: np.random.Generator, rate: Signal) -> Grains:
    """Sortea granos de un campo de ritmos [paso, celda], en granos por segundo.

    El ritmo de cada celda cambia con suavidad de un paso al siguiente a lo largo del
    sonido, así que los granos llegan de donde está el dato en cada momento.
    """
    total = rate.sum(axis=1)
    peak = float(total.max())
    if peak <= 0:
        nothing = np.zeros(0, dtype=np.intp)
        return Grains(np.zeros(0), nothing, nothing)
    seconds = np.sort(rng.uniform(0, SECONDS, rng.poisson(peak * SECONDS)))
    at = position(seconds, total.size)
    before = np.minimum(at.astype(np.intp), max(total.size - 2, 0))
    after = np.minimum(before + 1, total.size - 1)
    mix = at - before
    now = total[before] * (1 - mix) + total[after] * mix
    kept = rng.uniform(0, 1, seconds.size) < now / peak
    seconds, before, after, mix, now = seconds[kept], before[kept], after[kept], mix[kept], now[kept]
    late = rng.uniform(0, 1, seconds.size) * now < mix * total[after]
    step = np.where(late, after, before)
    cell = np.zeros(seconds.size, dtype=np.intp)
    for one in np.unique(step):
        chosen = step == one
        cell[chosen] = rng.choice(rate.shape[1], int(chosen.sum()), p=rate[one] / total[one])
    return Grains(seconds, cell, step)


def grain_bearings(rng: np.random.Generator, around: Surroundings, cells: Indices) -> Signal:
    """El rumbo desde el que llega cada grano: el de su celda, movido unos grados.

    La celda del propio punto no tiene rumbo: sus granos rodean al oyente.
    """
    bearing = around.bearing[cells].copy()
    own = around.km[cells] == 0
    bearing[own] = rng.uniform(0, 360, int(own.sum()))
    out: Signal = bearing + rng.uniform(-BEARING_JITTER, BEARING_JITTER, cells.size)
    return out


class Space:
    """El espacio alrededor del oyente: se le añaden fuentes y devuelve lo que oye cada oído."""

    def __init__(self, rng: np.random.Generator) -> None:
        """Prepara un espacio vacío; `rng` sortea la sala y el reparto de las formas de grano."""
        self._rng = rng
        self._head = head()
        self._ring = self._head.bearings.size
        self._ears = np.zeros(self._head.spectra.shape[1:], dtype=np.complex64)
        self._room = np.zeros(self._ears.shape[1], dtype=np.complex64)
        self._dull = dsp.band_gain(_frequencies(), high_hz=DULL_HZ).astype(np.float32)

    def add_grains(
        self,
        seconds: Signal,
        amplitudes: Signal,
        bearings: Signal,
        distance_m: Signal,
        shapes: Sequence[Spectrum],
        *,
        dull_far: bool = True,
    ) -> None:
        """Añade granos: cada uno es un impulso con la forma que toca a su rumbo.

        Args:
            seconds: Cuándo suena cada grano.
            amplitudes: Su amplitud a 1 m.
            bearings: De dónde llega, en grados desde el norte.
            distance_m: A qué distancia suena, en metros.
            shapes: Formas de grano (`grain_shape`); los rumbos se las reparten por turno.
            dull_far: Si los lejanos pierden agudos. Se puede ahorrar en granos que solo
                suenan cerca.
        """
        if seconds.size == 0:
            return
        sample = np.minimum((seconds * SAMPLE_RATE).astype(np.intp), N_SAMPLES - 1)
        bus = np.round(bearings / (360 / self._ring)).astype(np.intp) % self._ring
        direct = amplitudes / distance_m  # -6 dB cada vez que se dobla la distancia
        dull = DULL_MIX * np.clip(np.log(distance_m) / np.log(FAR_METRES), 0, 1) * dull_far
        dry = np.zeros((len(shapes), N_SAMPLES))
        for one in np.unique(bus):
            chosen = bus == one
            shape = int(one) % len(shapes)
            dry[shape] += np.bincount(sample[chosen], amplitudes[chosen], N_SAMPLES)
            heard = _spectrum(np.bincount(sample[chosen], direct[chosen] * (1 - dull[chosen]), N_SAMPLES))
            if dull_far:
                far = np.bincount(sample[chosen], direct[chosen] * dull[chosen], N_SAMPLES)
                heard = heard + self._dull * _spectrum(far)
            self._ears += self._head.spectra[one] * (shapes[shape] * heard)
        for form, impulses in zip(shapes, dry, strict=True):
            self._room += form * _spectrum(impulses)  # a la sala va sin atenuar: es lo que da la distancia

    def add_beds(
        self,
        around: Surroundings,
        power: Signal,
        noise: Callable[[], Signal],
        envelope: Signal,
    ) -> None:
        """Añade un fondo continuo repartido en sectores: en cada uno, un ruido propio.

        Args:
            around: El entorno, para saber en qué sector cae cada celda.
            power: Potencia que aporta cada celda en cada paso, con forma [paso, celda].
                La celda del propio punto se reparte entre todos los sectores.
            noise: Da un ruido nuevo de RMS 1 cada vez que se llama.
            envelope: Forma del fondo a lo largo del sonido, muestra a muestra.
        """
        sectors = self._ring // 2
        sector = np.round(around.bearing / (360 / sectors)).astype(np.intp) % sectors
        own = around.km == 0
        everywhere = power[:, own].sum(axis=1) / sectors
        for one in range(sectors):
            heard = power[:, (sector == one) & ~own].sum(axis=1) + everywhere
            if heard.max() > 0:
                self.add_bed(one * 360 / sectors, noise() * np.sqrt(follow(heard)) * envelope)

    def add_bed(self, bearing: float, signal: Signal) -> None:
        """Añade una señal continua que llega desde un rumbo, tal cual (sin distancia ni sala)."""
        bus = round(bearing / (360 / self._ring)) % self._ring
        self._ears += self._head.spectra[bus] * _spectrum(signal)

    def render(self, reverb_s: float, damping_hz: float = 5000.0) -> Signal:
        """Lo que oye cada oído, con forma (2, `N_SAMPLES`): las fuentes más la sala.

        La sala es ruido que se apaga en `reverb_s` segundos (T60), distinto en cada oído
        y sin agudos por encima de `damping_hz`. Su nivel no depende de la distancia de
        las fuentes: por eso lo lejano, que llega flojo, suena con más sala que lo cercano.
        """
        out: Signal = np.fft.irfft(self._ears, N_SAMPLES, axis=-1).astype(np.float64)
        t = np.arange(int(reverb_s * SAMPLE_RATE)) / SAMPLE_RATE
        for ear in range(2):
            tail = self._rng.standard_normal(t.size) * 10 ** (-3 * t / reverb_s)
            tail[: int(ROOM_DELAY_S * SAMPLE_RATE)] = 0
            tail = dsp.spectral_filter(tail, high_hz=damping_hz)
            tail *= ROOM_LEVEL * np.sqrt(0.5) / float(np.sqrt(np.sum(tail**2)))
            out[ear] += np.fft.irfft(self._room * _spectrum(tail), N_SAMPLES)
        return out
