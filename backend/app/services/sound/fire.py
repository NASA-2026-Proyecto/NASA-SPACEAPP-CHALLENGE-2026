"""Los incendios activos como el sonido de un fuego.

El mismo fuego, más grande o más pequeño: unas brasas que chasquean cuando el incendio
más fuerte de la zona es débil, un incendio alrededor del oyente cuando alcanza el
extremo de la escala. Todo cuelga de un número, `intensity`: la potencia radiativa (FRP)
del incendio más fuerte junto al punto, dividida entre los 8 MW en que acaba la barra de
color de la NASA (escala lineal). Donde no hay ningún incendio cerca no hay sonido.

En tres dimensiones (`synthesize_spatial`) cada celda que arde en el entorno es un fuego
aparte, con los parámetros de su propia potencia, que suena desde su rumbo y su distancia
y cambia con los pasos de la serie. El timbre común (el tono de los chasquidos, el aleteo)
es el del incendio que más se oye.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from app.services.sound import dsp, spatial
from app.services.sound.common import (
    SECONDS,
    TAIL,
    PointSample,
    Surroundings,
    compass,
    describe_journey,
    describe_place,
    describe_stamp,
    direction_weights,
    fade_envelope,
    number,
)
from app.services.sound.dsp import SAMPLE_RATE, Signal

UNIT = "MW"
POWER_FULL = 8.0  # MW en el extremo alto de la barra de color de la NASA (lineal)
NEAR_KM = 30.0  # en 3D, hasta esta distancia un incendio suena junto al oyente (su propia celda)
CLICK_SECONDS = (0.00045, 0.0007, 0.0011)  # en 3D, lo que tarda en apagarse cada forma de chasquido
SNAPS = ((0.005, 450.0), (0.008, 700.0))  # en 3D, formas de chascazo: lo que dura y su tono (Hz)

# Qué fuego se oye según la intensidad (límite superior, nombre)
FIRES = (
    (0.20, "unas brasas que chasquean"),
    (0.45, "una fogata pequeña"),
    (0.75, "una hoguera grande"),
    (float("inf"), "un incendio alrededor"),
)


@dataclass(frozen=True)
class FireParameters:
    """Los parámetros del sonido del fuego; todos salen de `intensity`.

    Attributes:
        intensity: FRP del incendio más fuerte de la zona entre 8 MW, de 0 a 1.
        fire: Qué fuego se oye, en palabras.
        crackles_per_s: Ráfagas de chasquidos por segundo, de media (de 1,5 a ~40).
        clicks_per_crackle: Chasquidos en cada ráfaga, de media.
        crackle_db: Volumen de los chasquidos (de -6 a 0 dB).
        crackle_hz: Tono de los chasquidos: más grave con madera más gruesa.
        snaps_per_s: Troncos que se parten por segundo (de uno cada ~20 s a varios).
        roar_hz: Hasta dónde llega el aleteo grave de la llama.
        roar_gain: Lo fuerte que es ese aleteo.
        flutter_hz: Lo rápido que tiembla el gas que arde.
        flicker_hz: Parpadeo de las llamas: rápido en las pequeñas, lento en un muro de fuego.
        flicker_depth: Cuánto sube y baja el fuego con cada parpadeo.
        width: Anchura estéreo: el fuego delante (0,25) o alrededor (1).
        reverb_s: Reverberación: más seca cuanto más fuego y más humo.
        loudness_db: Ganancia del conjunto (de 0 a +4 dB).
    """

    intensity: float
    fire: str
    crackles_per_s: float
    clicks_per_crackle: float
    crackle_db: float
    crackle_hz: float
    snaps_per_s: float
    roar_hz: float
    roar_gain: float
    flutter_hz: float
    flicker_hz: float
    flicker_depth: float
    width: float
    reverb_s: float
    loudness_db: float


def intensity(megawatts: float) -> float:
    """0 = sin potencia, 1 = 8 MW o más: la posición en la barra de color de la NASA."""
    return float(np.clip(megawatts / POWER_FULL, 0, 1))


def mapping(megawatts: float) -> FireParameters:
    """Todos los parámetros del fuego a partir de un solo número."""
    x = intensity(megawatts)
    return FireParameters(
        intensity=x,
        fire=next(name for top, name in FIRES if x < top),
        crackles_per_s=1.5 + 38 * x**1.6,
        clicks_per_crackle=1.5 + 3.5 * x,
        crackle_db=-6 * (1 - x),
        crackle_hz=3000 * (1600 / 3000) ** x,
        snaps_per_s=0.05 + 2.5 * x**2.5,
        roar_hz=120 * (450 / 120) ** x,
        roar_gain=0.05 + 0.15 * x**1.3,
        flutter_hz=12 + 13 * x,
        flicker_hz=7 * (0.8 / 7) ** x,
        flicker_depth=0.35 + 0.3 * x,
        width=0.25 + 0.75 * x,
        reverb_s=1.4 * (0.7 / 1.4) ** x,
        loudness_db=0 + 4 * x,
    )


def describe(sample: PointSample, m: FireParameters) -> str:
    """Dice con palabras de qué está hecho el sonido (también para lectores de pantalla)."""
    text = (
        f"Incendios activos vistos por el satélite VIIRS, dato del {describe_stamp(sample.stamp)}: "
        f"el más fuerte junto a este punto emite unos {number(sample.value)} MW. "
        f"Se oye {m.fire}: unas {number(m.crackles_per_s, 0)} ráfagas de chasquidos por segundo "
        f"y un aleteo grave de llama por debajo de {number(m.roar_hz, 0)} Hz."
    )
    peak = int(sample.around.argmax())
    if sample.around[peak] > 2 * np.median(sample.around) and sample.around[peak] > 0:
        text += (
            f" Hay más fuego hacia el {compass(float(sample.bearings[peak]))}: "
            "de ese lado llegan más chasquidos."
        )
    return text


def describe_absent(sample: PointSample) -> str:
    """Qué se dice donde no hay ningún incendio cerca: ahí no suena nada."""
    return (
        f"Sin incendios activos junto a este punto en el dato del {describe_stamp(sample.stamp)} "
        "(satélite VIIRS): no suena ningún fuego."
    )


def _wobble(rng: np.random.Generator, n: int, per_second: float, seconds: float) -> Signal:
    """Curva de control aleatoria entre 0 y 1 que cambia unas `per_second` veces por segundo."""
    return dsp.to_audio_rate(rng.uniform(0, 1, int(per_second * seconds) + 2), n)


def _normalised(stereo: Signal, rms: float = 0.25) -> Signal:
    """Lleva una señal a un RMS dado, para que un filtro no cambie el nivel de su capa."""
    out: Signal = stereo * rms / (float(np.sqrt(np.mean(stereo**2))) + 1e-12)
    return out


def synthesize(sample: PointSample, m: FireParameters, seed: int = 0) -> Signal:
    """Convierte los incendios junto a un punto en 15 s de fuego (12 s más 3 s de cola), en estéreo."""
    rng = np.random.default_rng(seed)
    sr = SAMPLE_RATE
    n = int((SECONDS + TAIL) * sr)
    t = np.arange(n) / sr
    envelope = fade_envelope(n, sr)

    # El parpadeo de las llamas: lo siguen el cuerpo del fuego y la frecuencia de los chasquidos
    flame = _wobble(rng, n, m.flicker_hz, SECONDS + TAIL)
    life = 1 - m.flicker_depth * flame

    # 1. Cuerpo: ruido marrón grave que tiembla deprisa y sin regularidad, como el gas al arder
    a, b = (dsp.coloured_noise(n, rng, 2.0) for _ in range(2))
    roar = np.stack([a, (1 - m.width) * a + m.width * b])  # width 0 = el mismo ruido en los dos oídos
    roar = _normalised(dsp.spectral_filter(roar, low_hz=45, high_hz=m.roar_hz))
    flutter = 0.4 + 0.6 * _wobble(rng, n, m.flutter_hz, SECONDS + TAIL) ** 2
    roar *= m.roar_gain * life * flutter * envelope

    # 2. Chasquidos: ráfagas de 1 a ~6 clics muy cortos, irregulares y agrupados (eso distingue
    #    al fuego de la lluvia), más frecuentes cuando las llamas se avivan
    tries = rng.poisson(2 * m.crackles_per_s * SECONDS)
    candidates = np.sort(rng.uniform(0.3, SECONDS - 0.4, tries))
    flare = 1 - flame[(candidates * sr).astype(int)]
    bursts = candidates[rng.uniform(0, 1, candidates.size) < flare]
    bearing = rng.choice(sample.bearings, size=bursts.size, p=direction_weights(sample.around))
    bearing = bearing + rng.uniform(-8, 8, bursts.size)
    burst_pan = m.width * np.sin(np.radians(bearing))  # el este suena a la derecha
    burst_amp = np.minimum(1 + rng.pareto(2.2, bursts.size), 6.0) / 3

    onsets_list, pans_list, amps_list = [np.zeros(0)], [np.zeros(0)], [np.zeros(0)]
    for onset, position, amp in zip(bursts, burst_pan, burst_amp, strict=True):
        clicks = 1 + rng.poisson(m.clicks_per_crackle - 1)
        onsets_list.append(onset + np.cumsum(rng.exponential(0.006, clicks)) - 0.002)
        pans_list.append(np.clip(position + rng.uniform(-0.05, 0.05, clicks), -1, 1))
        amps_list.append(amp * rng.uniform(0.25, 1.0, clicks))
    onsets, pans, amps = (np.concatenate(parts) for parts in (onsets_list, pans_list, amps_list))
    durs = 0.0007 * rng.uniform(0.6, 1.6, onsets.size)
    amps = 0.6 * amps * 10 ** (m.crackle_db / 20) * np.interp(onsets, t, envelope)
    crackle = dsp.grain_cloud(
        onsets,
        np.full(onsets.size, m.crackle_hz),
        durs,
        amps,
        pans,
        1.0,
        n,
        rng,
        attacks_s=np.full(onsets.size, 0.00005),
    )
    crackle = dsp.spectral_filter(crackle, low_hz=m.crackle_hz / 2.5, high_hz=m.crackle_hz * 2.5)

    # 3. Chascazos: un tronco o una rama que se parte. Más raros, fuertes, largos y leñosos
    count = rng.poisson(m.snaps_per_s * SECONDS)
    snap_at = np.sort(rng.uniform(0.5, SECONDS - 0.5, count))
    snap_pan = m.width * rng.uniform(-1, 1, count)
    snap_dur = 0.006 * rng.uniform(0.6, 1.6, count)
    snap_amp = 0.35 * rng.uniform(0.5, 1.0, count) * np.interp(snap_at, t, envelope)
    snaps = dsp.grain_cloud(
        snap_at,
        rng.uniform(350, 900, count),
        snap_dur,
        snap_amp,
        snap_pan,
        0.7,
        n,
        rng,
        attacks_s=np.full(count, 0.0002),
    )
    snaps = dsp.spectral_filter(snaps, low_hz=180, high_hz=4000)

    # 4. El espacio: un sitio abierto, más seco a medida que crecen el fuego y su humo
    mix = dsp.reverb(
        roar + crackle + snaps,
        rng,
        seconds=m.reverb_s,
        damping_hz=5000,
        wet=0.10 + 0.15 * (1 - m.intensity),
    )
    mix *= 10 ** (m.loudness_db / 20)
    return dsp.soft_limit(mix)


def _distances(around: Surroundings) -> Signal:
    """A cuántos metros suena cada celda del entorno."""
    return spatial.metres(around.km, NEAR_KM, around.far_km)


def _loudest(around: Surroundings) -> tuple[int, int]:
    """Paso y celda del incendio que más se oye: el más potente para lo lejos que está."""
    heard = np.clip(around.values / POWER_FULL, 0, 1) / _distances(around)
    step, cell = np.unravel_index(int(heard.argmax()), heard.shape)
    return int(step), int(cell)


def spatial_mapping(around: Surroundings) -> FireParameters:
    """Los parámetros del incendio que más se oye en el entorno: de él sale el timbre del conjunto."""
    return mapping(float(around.values[_loudest(around)]))


def describe_spatial(around: Surroundings, m: FireParameters) -> str:
    """Dice con palabras qué se oye en tres dimensiones (también para lectores de pantalla)."""
    step, cell = _loudest(around)
    burning = int(np.count_nonzero(around.values[-1] > 0))
    return (
        f"{describe_journey(around)} Incendios activos vistos por el satélite VIIRS hasta "
        f"{number(around.far_km, 0)} km del punto: cada celda que arde suena desde donde está. "
        f"El que más se oye emite unos {number(float(around.values[step, cell]))} MW y está "
        f"{describe_place(around, cell)}; suena como {m.fire}. En el paso más reciente hay fuego en "
        f"{burning} de las {around.km.size} celdas del entorno."
    )


def describe_absent_spatial(around: Surroundings) -> str:
    """Qué se dice donde no hay ningún incendio en todo el entorno: ahí no suena nada."""
    return (
        f"Sin incendios activos a menos de {number(around.far_km, 0)} km de este punto entre el "
        f"{describe_stamp(around.stamps[0])} y el {describe_stamp(around.stamps[-1])} "
        "(satélite VIIRS): no suena ningún fuego."
    )


def synthesize_spatial(around: Surroundings, m: FireParameters, seed: int = 0) -> Signal:
    """Convierte los incendios del entorno en 15 s de fuego en tres dimensiones, para auriculares."""
    rng = np.random.default_rng(seed)
    sr = SAMPLE_RATE
    n = spatial.N_SAMPLES
    t = np.arange(n) / sr
    envelope = fade_envelope(n, sr)
    space = spatial.Space(rng)
    distance = _distances(around)
    burning = around.values > 0
    fires = [[mapping(float(megawatts)) for megawatts in step] for step in around.values]

    def field(pick: Callable[[FireParameters], float]) -> Signal:
        """Un parámetro de cada celda en cada paso; cero donde no arde nada."""
        values: Signal = np.array([[pick(fire) for fire in step] for step in fires]) * burning
        return values

    # 1. Chasquidos: cada celda que arde crepita según su propia potencia
    bursts = spatial.draw_grains(rng, field(lambda fire: fire.crackles_per_s))
    here = (bursts.step, bursts.cell)
    clicks = 1 + rng.poisson(field(lambda fire: fire.clicks_per_crackle)[here] - 1)
    burst_amp = np.minimum(1 + rng.pareto(2.2, clicks.size), 6.0) / 3
    burst_amp *= 0.6 * 10 ** (field(lambda fire: fire.crackle_db)[here] / 20)
    burst_bearing = spatial.grain_bearings(rng, around, bursts.cell)
    each = np.repeat(np.arange(clicks.size), clicks)  # a qué ráfaga pertenece cada chasquido
    gaps = rng.exponential(0.006, each.size)
    run = np.cumsum(gaps)
    first = np.cumsum(clicks) - clicks
    since_burst = run - np.repeat(run[first] - gaps[first], clicks)
    onsets = np.clip(bursts.seconds[each] + since_burst - 0.002, 0, SECONDS)
    amps = burst_amp[each] * rng.uniform(0.25, 1.0, each.size) * np.interp(onsets, t, envelope)
    shapes = []
    for seconds in CLICK_SECONDS:
        tt = np.arange(int(7 * seconds * sr)) / sr
        click = rng.standard_normal(tt.size) * np.exp(-tt / seconds)
        shapes.append(spatial.grain_shape(click, m.crackle_hz / 2.5, m.crackle_hz * 2.5))
    space.add_grains(onsets, amps, burst_bearing[each], distance[bursts.cell][each], shapes)

    # 2. Chascazos: troncos que se parten, más raros, largos y leñosos
    snaps = spatial.draw_grains(rng, field(lambda fire: fire.snaps_per_s))
    amps = 0.35 * rng.uniform(0.5, 1.0, snaps.seconds.size) * np.interp(snaps.seconds, t, envelope)
    shapes = []
    for seconds, tone_hz in SNAPS:
        tt = np.arange(int(7 * seconds * sr)) / sr
        snap = 0.3 * np.sin(2 * np.pi * tone_hz * tt) + 0.7 * rng.standard_normal(tt.size)
        shapes.append(spatial.grain_shape(snap * np.exp(-tt / seconds), 180, 4000))
    space.add_grains(
        snaps.seconds, amps, spatial.grain_bearings(rng, around, snaps.cell), distance[snaps.cell], shapes
    )

    # 3. Cuerpo: el aleteo grave de la llama, desde el sector donde arde
    flame = _wobble(rng, n, m.flicker_hz, SECONDS + TAIL)
    flutter = 0.4 + 0.6 * _wobble(rng, n, m.flutter_hz, SECONDS + TAIL) ** 2
    life = (1 - m.flicker_depth * flame) * flutter * envelope
    space.add_beds(
        around,
        (field(lambda fire: fire.roar_gain) / distance) ** 2,
        lambda: 0.25 * np.sqrt(2) * spatial.unit_noise(rng, 2.0, 45, m.roar_hz),
        life,
    )

    mix = space.render(m.reverb_s) * 10 ** (m.loudness_db / 20)
    return dsp.soft_limit(mix)
