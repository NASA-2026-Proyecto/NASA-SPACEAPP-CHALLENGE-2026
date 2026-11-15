"""El PM2.5 como sonido del aire.

Todos los sitios suenan como el aire peligroso de referencia: un zumbido grave que bate,
un retumbo de viento cercano y un siseo arenoso de polvo, en un espacio pequeño y seco.
El aire más limpio es ese mismo sonido con menos intensidad: el zumbido y el viento se
retiran mucho más que el polvo, y el conjunto se ajusta a un volumen percibido exacto
(LUFS), 9 LU más bajo en el aire más limpio. Todo cuelga de un número, la calima
(`haze`): 0 con 1 µg/m³ o menos y 1 con 350 µg/m³ o más, en escala logarítmica.
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

UNIT = "µg/m³"
HAZE_FULL = 350.0  # µg/m³ a partir de los cuales el sonido es el de referencia
ROOT_HZ = 146.83  # re3: la nota de la que cuelga el zumbido

# Extremos de la barra de color de la NASA (escala logarítmica) y las palabras con las que
# el front nombra la posición en ella. Es relativo a esa escala, no un índice de calidad
# del aire.
SCALE_MIN, SCALE_MAX = 0.4, 409.6
LEVELS = ("muy bajo", "bajo", "moderado", "alto", "muy alto")


@dataclass(frozen=True)
class AirParameters:
    """Los parámetros del sonido del aire. Solo los cinco primeros cambian con el dato.

    Attributes:
        intensity: La calima, de 0 a 1: el número del que cuelga todo.
        dust_per_s: Granos de polvo por segundo (de 200 a ~350).
        dust_db: Volumen del siseo de polvo (de -7 a 0 dB).
        drone_db: Volumen del zumbido grave, el sonido principal (de -14 a 0 dB).
        wind_db: Volumen del viento grave que hay debajo (de -6 a 0 dB).
        loudness_lufs: Volumen percibido del conjunto (de -26,8 a -17,8 LUFS).
        semitones: Notas del zumbido, en semitonos sobre re3: un racimo grave y áspero.
        detune_cents: Cuánto se separan las dos copias de cada voz, que baten entre sí.
        brightness_hz: Corte del paso bajo del zumbido: suena apagado.
        dust_hz: Zona de tono del polvo (arena, alrededor de 1 kHz).
        gustiness: Cuánto se agita el viento (0 = aire quieto).
        width: Anchura estéreo (0 = mono): un espacio cercano.
        reverb_s: Duración de la reverberación: un espacio pequeño y seco.
        reverb_wet: Cuánta reverberación se mezcla.
        wind_hz: Corte del paso bajo del viento: un retumbo grave.
        wind_gain: Nivel base del viento.
    """

    intensity: float
    dust_per_s: float
    dust_db: float
    drone_db: float
    wind_db: float
    loudness_lufs: float
    semitones: tuple[int, ...] = (-12, 0, 1, 6, 13, 15)
    detune_cents: float = 30.0
    brightness_hz: float = 450.0
    dust_hz: float = 900.0
    gustiness: float = 0.0
    width: float = 0.3
    reverb_s: float = 0.5
    reverb_wet: float = 0.15
    wind_hz: float = 350.0
    wind_gain: float = 0.30


def haze(ugm3: float) -> float:
    """0 = aire limpísimo (1 µg/m³ o menos), 1 = peligroso (350 o más), en escala logarítmica."""
    return float(np.clip(np.log(max(ugm3, 1e-3)) / np.log(HAZE_FULL), 0, 1))


def level(ugm3: float) -> str:
    """Palabra para la posición del valor en la barra de color de la NASA."""
    position = np.log(max(ugm3, SCALE_MIN) / SCALE_MIN) / np.log(SCALE_MAX / SCALE_MIN)
    return LEVELS[min(len(LEVELS) - 1, int(position * len(LEVELS)))]


def mapping(ugm3: float) -> AirParameters:
    """El sonido de referencia, con la intensidad que pide este PM2.5."""
    h = haze(ugm3)
    return AirParameters(
        intensity=h,
        dust_per_s=200 * (350.8 / 200) ** h,
        dust_db=-7 * (1 - h),
        drone_db=-14 * (1 - h),
        wind_db=-6 * (1 - h),
        # Volumen percibido (LUFS, ITU-R BS.1770): 9 LU desde el aire más limpio hasta el
        # nivel propio del sonido de referencia (-17,84 LUFS)
        loudness_lufs=-26.84 + 9.0 * h,
    )


def describe(sample: PointSample, m: AirParameters) -> str:
    """Dice con palabras de qué está hecho el sonido (también para lectores de pantalla)."""
    strength = (
        "con toda su fuerza" if m.drone_db > -0.5 else f"{number(-m.drone_db, 0)} dB por debajo de su máximo"
    )
    text = (
        f"PM2.5 en la visualización de la NASA del {describe_stamp(sample.stamp)}: "
        f"unos {number(sample.value)} µg/m³, nivel {level(sample.value)} en la escala de la NASA. "
        f"Se oye el siseo del polvo ({number(m.dust_per_s, 0)} granos por segundo) sobre el "
        f"zumbido grave del aire peligroso, {strength}."
    )
    peak = int(sample.around.argmax())
    typical = float(np.median(sample.around))
    if sample.around[peak] > 1.5 * typical and sample.around[peak] - typical > 3:  # µg/m³
        text += (
            f" El aire está más sucio hacia el {compass(float(sample.bearings[peak]))}: "
            "de ese lado llegan más partículas."
        )
    return text


def synthesize(sample: PointSample, m: AirParameters, seed: int = 0) -> Signal:
    """Convierte el PM2.5 de un punto en 15 s de "aire" (12 s más 3 s de cola), en estéreo."""
    rng = np.random.default_rng(seed)
    sr = SAMPLE_RATE
    n = int((SECONDS + TAIL) * sr)
    t = np.arange(n) / sr
    envelope = fade_envelope(n, sr)

    # 1. Viento: ruido rosa grave, un retumbo cercano
    gust = 1 - m.gustiness * (0.5 + 0.5 * dsp.to_audio_rate(rng.uniform(-1, 1, 8), n))
    a, b = (dsp.coloured_noise(n, rng, 1.2) for _ in range(2))
    wind = np.stack([a, (1 - m.width) * a + m.width * b])  # width 0 = el mismo ruido en los dos oídos
    wind = dsp.spectral_filter(wind, low_hz=60, high_hz=m.wind_hz)
    wind *= m.wind_gain * gust * envelope * 10 ** (m.wind_db / 20)

    # 2. Cielo: un racimo grave que respira despacio; las voces entran una a una, apagadas
    pad = np.zeros((2, n))
    for i, semis in enumerate(m.semitones):
        f = ROOT_HZ * 2 ** (semis / 12)
        low, high = (f * 2 ** (sign * m.detune_cents / 1200) for sign in (-1, 1))
        voice = (dsp.additive(low, n, harmonics=8, rolloff=1.6) + dsp.additive(high, n, 8, 1.6)) / 2
        enter = np.clip((t - 0.35 * i) / 2.0, 0, 1)
        breath = 0.75 + 0.25 * np.sin(2 * np.pi * (0.11 + 0.013 * i) * t + rng.uniform(0, 2 * np.pi))
        gain = 0.09 if semis == -12 else 0.06
        pad += dsp.pan(gain * voice * enter * breath, m.width * rng.uniform(-0.6, 0.6))
    pad = dsp.spectral_filter(pad, high_hz=m.brightness_hz) * envelope
    pad *= 10 ** (m.drone_db / 20)  # el sonido principal se retira en el aire más limpio

    # 3. Polvo: chasquidos diminutos de ruido, como arena al viento, desde donde hay partículas
    count = rng.poisson(m.dust_per_s * SECONDS)
    onsets = np.sort(rng.uniform(0.3, SECONDS - 0.5, count))
    bearing = rng.choice(sample.bearings, size=count, p=direction_weights(sample.around))
    bearing = bearing + rng.uniform(-5, 5, count)
    pans = m.width * np.sin(np.radians(bearing))  # el este suena a la derecha
    rng.uniform(-0.7, 0.7, count)  # no se usa: mantiene la secuencia aleatoria del sonido de referencia
    durs = 0.0025 * rng.uniform(0.6, 1.4, count)
    amps = (
        0.66
        * m.dust_per_s**-0.2
        / np.sqrt(durs / 0.01)
        * rng.uniform(0.4, 1.0, count)
        * 10 ** (m.dust_db / 20)
        * np.interp(onsets, t, envelope)
    )
    dust = dsp.grain_cloud(onsets, np.full(count, m.dust_hz), durs, amps, pans, 1.0, n, rng)
    dust = dsp.spectral_filter(dust, low_hz=m.dust_hz / 3, high_hz=m.dust_hz * 1.2, order=4)

    # 4. El espacio, pequeño y cercano. Después, el volumen percibido exacto para esta calima
    #    (LUFS y no RMS: el oído oye el zumbido grave menos de lo que cuenta el RMS)
    mix = dsp.reverb(
        wind + pad + dust, rng, seconds=m.reverb_s, damping_hz=1.2 * m.brightness_hz, wet=m.reverb_wet
    )
    mix *= 10 ** ((m.loudness_lufs - dsp.loudness_lufs(mix)) / 20)
    return dsp.soft_limit(mix)
