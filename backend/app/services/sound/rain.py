"""La precipitación como sonido de lluvia.

La misma lluvia, con más o menos gotas: una cortina de incontables impactos diminutos,
gotas gordas que golpean cerca, la lluvia lejana como un rumor liso, viento a ráfagas y
truenos en las tormentas. Todo cuelga de un número, `wetness`: 0 en seco y 1 con
20 mm/h o más, creciendo como log(1 + mm/h).
"""

from dataclasses import dataclass

import numpy as np

from app.services.sound import dsp
from app.services.sound.common import (
    SECONDS,
    TAIL,
    PointSample,
    compass,
    describe_stamp,
    direction_weights,
    fade_envelope,
    number,
)
from app.services.sound.dsp import SAMPLE_RATE, Signal

UNIT = "mm/h"
RATE_FULL = 20.0  # mm/h a partir de los cuales la lluvia suena con toda su fuerza
RAINING_FROM = 0.05  # mm/h por debajo de los cuales no cae ninguna gota
RMS_FULL = 0.20  # RMS de la cortina de lluvia con wetness 1 (la referencia)

# Categorías de intensidad de lluvia de la American Meteorological Society, en mm/h
# ("seco" es no llegar a la cantidad con la que aquí empieza a caer alguna gota)
CATEGORIES = (
    (RAINING_FROM, "seco"),
    (2.5, "lluvia débil"),
    (7.6, "lluvia moderada"),
    (float("inf"), "lluvia fuerte"),
)


@dataclass(frozen=True)
class RainParameters:
    """Los parámetros del sonido de la lluvia; todos salen de `intensity`.

    Attributes:
        intensity: `wetness`, de 0 (seco) a 1 (20 mm/h o más).
        drops_per_s: Impactos de gotas pequeñas por segundo (de 0 a ~25 000): pocas
            crepitan, muchas son el siseo de la lluvia.
        sheet_db: Volumen de esa cortina de lluvia (de -16 a 0 dB).
        sheet_low_hz: Límite grave de la cortina: las gotas grandes llegan más abajo.
        sheet_high_hz: Límite agudo de la cortina: la llovizna fina es la más brillante.
        taps_per_s: Gotas gordas por segundo golpeando hojas y piedras cerca (hasta ~60).
        tap_hz: Tono central de esos golpes.
        wash_ratio: Volumen de la lluvia lejana respecto a la cercana.
        wash_hz: Lo oscura que es la lluvia lejana.
        wind_rms: Nivel del viento: de una brisa a ráfagas.
        gustiness: Cuánto se hinchan el viento y la lluvia con cada ráfaga.
        wind_hz: Brillo del viento.
        thunder: Truenos en los 12 s: ninguno por debajo de wetness 0,55 (~4 mm/h), hasta 3.
    """

    intensity: float
    drops_per_s: float
    sheet_db: float
    sheet_low_hz: float
    sheet_high_hz: float
    taps_per_s: float
    tap_hz: float
    wash_ratio: float
    wash_hz: float
    wind_rms: float
    gustiness: float
    wind_hz: float
    thunder: int


def category(mm_h: float) -> str:
    """'seco', 'lluvia débil', 'lluvia moderada' o 'lluvia fuerte'."""
    return next(name for top, name in CATEGORIES if mm_h < top)


def wetness(mm_h: float) -> float:
    """0 = seco, 1 = 20 mm/h o más; crece como log(1 + mm/h)."""
    return float(np.clip(np.log1p(max(mm_h, 0.0)) / np.log1p(RATE_FULL), 0, 1))


def mapping(mm_h: float) -> RainParameters:
    """Todos los parámetros de la lluvia a partir de un solo número."""
    w = wetness(mm_h)
    raining = mm_h >= RAINING_FROM
    return RainParameters(
        intensity=w,
        drops_per_s=25_000 * w**2.5 * raining,
        sheet_db=-16 * (1 - w),
        sheet_low_hz=700 * (250 / 700) ** w,
        sheet_high_hz=11_000 - 3_000 * w,
        taps_per_s=60 * w**1.5 * raining,
        tap_hz=2200 * (600 / 2200) ** w,
        wash_ratio=0.9 * w**1.5,
        wash_hz=1500 + 2500 * w,
        wind_rms=0.012 + 0.03 * w,
        gustiness=0.2 + 0.5 * w,
        wind_hz=400 + 400 * w,
        thunder=round(3 * float(np.clip((w - 0.55) / 0.45, 0, 1))),
    )


def describe(sample: PointSample, m: RainParameters) -> str:
    """Dice con palabras de qué está hecho el sonido (también para lectores de pantalla)."""
    drops = m.drops_per_s
    if drops == 0:
        heard = "No llueve: solo se oye el viento."
    else:
        sheet = (
            "el crepitar de gotas sueltas"
            if drops < 500
            else "un repiqueteo constante"
            if drops < 5000
            else "el siseo denso de un aguacero"
        )
        heard = f"Se oye {sheet} (en torno a {number(drops, 0)} gotas pequeñas por segundo)"
        if m.taps_per_s >= 0.5:
            heard += f" y {number(m.taps_per_s, 0)} gotas gordas por segundo golpeando cerca"
        heard += "."
    text = (
        f"Precipitación de los satélites GPM del {describe_stamp(sample.stamp)}: "
        f"unos {number(sample.value)} mm por hora, {category(sample.value)}. {heard}"
    )
    if m.thunder:
        text += f" {m.thunder} trueno{'s' if m.thunder > 1 else ''}."
    peak = int(sample.around.argmax())
    if drops > 0 and sample.around[peak] > 0.3 and sample.around[peak] > 2 * np.median(sample.around):
        text += f" Llueve más hacia el {compass(float(sample.bearings[peak]))}: de ese lado llegan más gotas."
    return text


def _rms(x: Signal) -> float:
    """Nivel RMS de una señal."""
    return float(np.sqrt(np.mean(x**2)))


def _impulse_trains(times_s: Signal, amps: Signal, pans: Signal, n: int) -> Signal:
    """Impulsos estéreo, uno por gota, en esos instantes, amplitudes y posiciones (-1..1)."""
    out = np.zeros((2, n))
    pos = np.clip((times_s * SAMPLE_RATE).astype(int), 0, n - 1)
    angle = (np.clip(pans, -1, 1) + 1) * np.pi / 4
    np.add.at(out[0], pos, amps * np.cos(angle))
    np.add.at(out[1], pos, amps * np.sin(angle))
    return out


def _tame(x: Signal, level: float, crest: float = 6.0) -> Signal:
    """Lleva `x` al nivel RMS `level` y redondea los chasquidos más fuertes que `crest` veces eso."""
    x = x * level / (_rms(x) + 1e-12)
    out: Signal = crest * level * np.tanh(x / (crest * level))
    return out


def _click(tau_ms: float, rng: np.random.Generator) -> Signal:
    """El impacto de una gota diminuta: una ráfaga de ruido que se apaga en `tau_ms` milisegundos."""
    t = np.arange(int(7 * tau_ms * SAMPLE_RATE / 1000)) / SAMPLE_RATE
    out: Signal = rng.standard_normal(len(t)) * np.exp(-t / (tau_ms / 1000))
    return out


def synthesize(sample: PointSample, m: RainParameters, seed: int = 0) -> Signal:
    """Convierte la lluvia de un punto en 15 s de sonido (12 s más 3 s de cola), en estéreo."""
    rng = np.random.default_rng(seed)
    sr = SAMPLE_RATE
    n = int((SECONDS + TAIL) * sr)
    envelope = fade_envelope(n, sr)

    # Dónde llueve: la mitad de las gotas llegan de todas partes y la otra mitad del lado más lluvioso
    around = sample.around
    weights = direction_weights(around)
    east = float(np.sum(weights * np.sin(np.radians(sample.bearings))))  # > 0: llueve más al este

    def directions(count: int) -> Signal:
        bearing = rng.choice(sample.bearings, size=count, p=weights) + rng.uniform(-8, 8, count)
        out: Signal = np.sin(np.radians(bearing)) * rng.uniform(0.4, 1.0, count)
        return out  # el este suena a la derecha

    # Ráfagas: el viento y la lluvia se hinchan a la vez
    gust_curve = dsp.to_audio_rate(rng.uniform(0, 1, 14), n)
    swell = 1 - m.gustiness * 0.6 * (1 - gust_curve)
    sheet_rms = RMS_FULL * 10 ** (m.sheet_db / 20)

    # 1. La cortina: miles de impactos diminutos, de tamaños muy desiguales (muchos pequeños, pocos grandes)
    sheet = np.zeros((2, n))
    count = rng.poisson(m.drops_per_s * SECONDS)
    if count:
        times = rng.uniform(0, SECONDS, count)
        amps = (np.minimum(rng.pareto(3.0, count), 6) + 0.3) * rng.choice([-1.0, 1.0], count)
        amps *= np.interp(times * sr, np.arange(n), swell)
        pans = directions(count)
        for part, tau in zip(np.array_split(np.arange(count), 3), (0.15, 0.35, 0.8), strict=True):
            train = _impulse_trains(times[part], amps[part], pans[part], n)
            kernel = _click(tau, rng)
            sheet += np.stack([np.convolve(ch, kernel)[:n] for ch in train])
        sheet = dsp.spectral_filter(sheet, low_hz=m.sheet_low_hz, high_hz=m.sheet_high_hz)
        sheet = _tame(sheet, sheet_rms)

    # 2. Golpes: gotas más gordas y cercanas, cada una un toque corto con su propio color
    taps = np.zeros((2, n))
    for _ in range(rng.poisson(m.taps_per_s * SECONDS)):
        dur = rng.uniform(0.004, 0.015)
        length = int(6 * dur * sr)
        tt = np.arange(length) / sr
        centre = m.tap_hz * np.exp(rng.normal(0, 0.5))
        knock = dsp.spectral_filter(
            rng.standard_normal(length) * np.exp(-tt / dur), low_hz=centre / 1.6, high_hz=centre * 1.6
        )
        start = int(rng.uniform(0, SECONDS) * sr)
        end = min(start + length, n)
        taps[:, start:end] += dsp.pan(rng.uniform(0.3, 1.0) ** 2 * knock[: end - start], directions(1)[0])
    if _rms(taps) > 0:
        taps = _tame(taps, 0.5 * sheet_rms * min(1.0, m.taps_per_s / 20) ** 0.5)

    # 3. El rumor: la lluvia lejana, lisa y más oscura, más fuerte del lado más lluvioso
    a, b = (dsp.coloured_noise(n, rng, 0.8) for _ in range(2))
    wash = dsp.spectral_filter(
        np.stack([a * (1 - 0.4 * east), b * (1 + 0.4 * east)]), low_hz=200, high_hz=m.wash_hz
    )
    wash *= m.wash_ratio * sheet_rms / (_rms(wash) + 1e-12) * swell

    # 4. Viento: ruido rosa grave, a ráfagas en las tormentas
    a, b = (dsp.coloured_noise(n, rng, 1.4) for _ in range(2))
    wind = dsp.spectral_filter(np.stack([a, 0.4 * a + 0.6 * b]), low_hz=40, high_hz=m.wind_hz)
    wind *= m.wind_rms / (_rms(wind) + 1e-12) * (1 - m.gustiness * (1 - gust_curve))

    # 5. Truenos: retumbos graves desde donde más llueve, solo en las tormentas
    thunder = np.zeros((2, n))
    toward = float(np.sin(np.radians(sample.bearings[around.argmax()])))
    for start_s in np.sort(rng.uniform(1.0, SECONDS - 4.5, m.thunder)):
        length = int(rng.uniform(3.5, 5.0) * sr)
        tt = np.arange(length) / sr
        rolls = 0.4 + 0.6 * dsp.to_audio_rate(rng.uniform(0, 1, 16), length) ** 2
        shape = np.clip(tt / 0.25, 0, 1) * np.exp(-tt / 1.4) * rolls
        rumble = dsp.spectral_filter(
            dsp.coloured_noise(length, rng, 2.0), low_hz=25, high_hz=rng.uniform(150, 300)
        )
        start = int(start_s * sr)
        thunder[:, start : start + length] += dsp.pan(1.6 * rumble * shape, 0.6 * toward)

    # Al aire libre: solo un reflejo corto y tenue del entorno
    mix = (sheet + taps + wash) * envelope + (wind + thunder) * envelope
    mix = dsp.reverb(mix, rng, seconds=0.6, damping_hz=5000, wet=0.12)
    return dsp.soft_limit(mix)
