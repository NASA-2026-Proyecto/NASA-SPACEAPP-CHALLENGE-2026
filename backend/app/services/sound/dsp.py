"""Bloques de síntesis de sonido con numpy: ruido, filtros, granos, reverberación y WAV.

Convenciones: el audio es float64 entre -1 y 1; el estéreo tiene forma (2, n_muestras),
con el canal izquierdo en la fila 0; una "curva de control" es un parámetro que cambia
despacio, muestreado muy por debajo de la frecuencia de audio y estirado con
`to_audio_rate`.
"""

import io
import wave

import numpy as np
import numpy.typing as npt

type Signal = npt.NDArray[np.float64]

SAMPLE_RATE = 44_100  # los chasquidos y la llovizna fina llegan hasta varios kHz


def to_audio_rate(control: npt.ArrayLike, n_samples: int) -> Signal:
    """Estira una curva de control a `n_samples` muestras por interpolación lineal."""
    values = np.asarray(control, dtype=np.float64)
    if values.size == 1:
        return np.full(n_samples, float(values.item()))
    return np.interp(np.linspace(0, values.size - 1, n_samples), np.arange(values.size), values)


def phase(frequency_hz: float, n_samples: int, sr: int = SAMPLE_RATE) -> Signal:
    """Fase acumulada (radianes) de un oscilador de frecuencia fija."""
    freq = np.broadcast_to(np.asarray(frequency_hz, dtype=np.float64), (n_samples,))
    return 2 * np.pi * np.cumsum(freq) / sr


def pan(signal: Signal, position: float | Signal) -> Signal:
    """Coloca una señal mono en estéreo: -1 todo a la izquierda, +1 todo a la derecha.

    Reparte a potencia constante, así que el volumen no cambia con la posición.
    """
    angle = (np.clip(position, -1.0, 1.0) + 1.0) * np.pi / 4
    return np.stack([signal * np.cos(angle), signal * np.sin(angle)])


def soft_limit(signal: Signal, ceiling: float = 0.95) -> Signal:
    """Redondea los picos en vez de recortarlos; lo que suena flojo queda casi igual.

    No normaliza, a propósito: un sitio tranquilo tiene que seguir sonando flojo.
    """
    limited: Signal = ceiling * np.tanh(signal / ceiling)
    return limited


def _biquad_response(
    b: tuple[float, float, float], a: tuple[float, float, float], freqs: Signal, sr: int
) -> Signal:
    """Respuesta en magnitud de un filtro digital de segundo orden en esas frecuencias."""
    z = np.exp(-1j * 2 * np.pi * freqs / sr)
    num = b[0] + b[1] * z + b[2] * z**2
    den = a[0] + a[1] * z + a[2] * z**2
    out: Signal = np.abs(num / den)
    return out


def k_weighting(n_samples: int, sr: int = SAMPLE_RATE) -> Signal:
    """Magnitud del filtro K de la norma ITU-R BS.1770 en la rejilla rfft de `n_samples`.

    Dos etapas, como en la norma: un realce de unos +4 dB por encima de ~1,5 kHz (el efecto
    de la cabeza) y un paso alto a ~38 Hz (los graves profundos pesan poco en el volumen
    percibido). La norma solo da coeficientes para 48 kHz; estos son la derivación analógica
    de B. De Man ("Evaluation of implementations of the EBU R128 loudness measurement",
    2018), que los reproduce y vale para cualquier frecuencia de muestreo.
    """
    freqs = np.fft.rfftfreq(n_samples, 1 / sr)
    # Etapa 1: realce de agudos
    gain_db, q, fc = 3.999843853973347, 0.7071752369554196, 1681.974450955533
    k = np.tan(np.pi * fc / sr)
    vh = 10 ** (gain_db / 20)
    vb = vh**0.4996667741545416
    a0 = 1 + k / q + k * k
    shelf = _biquad_response(
        ((vh + vb * k / q + k * k) / a0, 2 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0),
        (1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0),
        freqs,
        sr,
    )
    # Etapa 2: paso alto
    q, fc = 0.5003270373238773, 38.13547087602444
    k = np.tan(np.pi * fc / sr)
    a0 = 1 + k / q + k * k
    highpass = _biquad_response(
        (1.0, -2.0, 1.0), (1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0), freqs, sr
    )
    return shelf * highpass


def loudness_lufs(stereo: Signal, sr: int = SAMPLE_RATE) -> float:
    """Volumen integrado (LUFS) según ITU-R BS.1770: lo fuerte que *parece* un sonido.

    A diferencia del nivel RMS, pondera las frecuencias como el oído (los graves cuentan
    menos; la zona de 2 a 4 kHz, más) e ignora los tramos en silencio (bloques de 400 ms,
    umbral absoluto de -70 LUFS y relativo de 10 LU por debajo del nivel sin umbral).
    """
    n = stereo.shape[-1]
    weighted = np.fft.irfft(np.fft.rfft(stereo, axis=-1) * k_weighting(n, sr), n=n, axis=-1)
    block, step = int(0.4 * sr), int(0.1 * sr)
    starts = range(0, max(n - block, 0) + 1, step)
    powers = np.array([float(np.sum(np.mean(weighted[:, s : s + block] ** 2, axis=1))) for s in starts])
    level = -0.691 + 10 * np.log10(np.maximum(powers, 1e-12))
    kept = powers[level > -70]
    if kept.size == 0:
        return -70.0
    relative = -0.691 + 10 * np.log10(np.mean(kept)) - 10
    kept = powers[(level > -70) & (level > relative)]
    return float(-0.691 + 10 * np.log10(np.mean(kept)))


def wav_bytes(stereo: Signal, sr: int = SAMPLE_RATE) -> bytes:
    """Codifica una señal (2, n) como archivo WAV PCM de 16 bits, en memoria.

    Es el formato que abre cualquier reproductor. Lo que se salga de -1..1 se recorta y un
    valor que no sea un número se escribe como silencio: al archivo nunca llega nada inválido.
    """
    safe = np.nan_to_num(stereo.T, nan=0.0, posinf=1.0, neginf=-1.0)
    pcm = (np.clip(safe, -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(stereo.shape[0])
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


def band_gain(
    freqs: Signal, low_hz: float | None = None, high_hz: float | None = None, order: int = 2
) -> Signal:
    """Ganancia con forma de Butterworth en esas frecuencias: paso alto en `low_hz`, bajo en `high_hz`."""
    gain = np.ones_like(freqs)
    if high_hz is not None:
        gain /= np.sqrt(1 + (freqs / high_hz) ** (2 * order))
    if low_hz is not None:
        gain /= np.sqrt(1 + (low_hz / np.maximum(freqs, 1e-9)) ** (2 * order))
    return gain


def spectral_filter(
    signal: Signal,
    low_hz: float | None = None,
    high_hz: float | None = None,
    order: int = 2,
    sr: int = SAMPLE_RATE,
) -> Signal:
    """Filtro con forma de Butterworth y fase cero, aplicado en frecuencia sobre el último eje.

    `high_hz` es el corte del paso bajo (se queda lo que está por debajo) y `low_hz` el del
    paso alto. `order` es la pendiente: 2 es suave (12 dB por octava), como la distancia.
    """
    n = signal.shape[-1]
    gain = band_gain(np.fft.rfftfreq(n, 1 / sr), low_hz, high_hz, order)
    out: Signal = np.fft.irfft(np.fft.rfft(signal, axis=-1) * gain, n=n, axis=-1)
    return out


def coloured_noise(n_samples: int, rng: np.random.Generator, exponent: float = 1.0) -> Signal:
    """Ruido cuya potencia cae como 1/f**exponent: 0 blanco, 1 rosa (viento), 2 marrón (retumbo).

    Sale con un RMS de 0,25, para que los distintos colores suenen más o menos igual de fuerte.
    """
    spectrum = np.fft.rfft(rng.standard_normal(n_samples))
    freqs = np.fft.rfftfreq(n_samples)
    freqs[0] = freqs[1]
    noise: Signal = np.fft.irfft(spectrum / freqs ** (exponent / 2), n=n_samples)
    return 0.25 * noise / (float(np.sqrt(np.mean(noise**2))) + 1e-12)


def fft_convolve(a: Signal, b: Signal) -> Signal:
    """Convolución lineal de dos señales 1D con la FFT (rápida con respuestas largas)."""
    size = a.size + b.size - 1
    n_fft = 1 << (size - 1).bit_length()
    out: Signal = np.fft.irfft(np.fft.rfft(a, n_fft) * np.fft.rfft(b, n_fft), n_fft)[:size]
    return out


def reverb(
    stereo: Signal,
    rng: np.random.Generator,
    seconds: float = 2.0,
    damping_hz: float = 6000.0,
    wet: float = 0.3,
    sr: int = SAMPLE_RATE,
) -> Signal:
    """Añade un espacio sintético: la respuesta al impulso es ruido que se apaga.

    `seconds` es el tiempo de caída (T60, hasta -60 dB). `damping_hz` oscurece la cola,
    porque el aire y las superficies blandas absorben antes los agudos. Cada canal tiene
    su propia cola, y eso da anchura. La salida mide lo mismo que la entrada: hay que
    dejar silencio al final para que la cola se oiga.
    """
    n_ir = int(seconds * sr)
    t = np.arange(n_ir) / sr
    decay = np.exp(-6.9 * t / seconds)
    out = np.empty_like(stereo)
    for ch in range(stereo.shape[0]):
        ir = spectral_filter(rng.standard_normal(n_ir) * decay, high_hz=damping_hz, sr=sr)
        ir /= float(np.sqrt(np.sum(ir**2))) + 1e-12
        tail = fft_convolve(stereo[ch], ir)[: stereo.shape[1]]
        out[ch] = (1 - wet) * stereo[ch] + wet * tail
    return out


def additive(
    frequency_hz: float,
    n_samples: int,
    harmonics: int = 6,
    rolloff: float = 1.5,
    sr: int = SAMPLE_RATE,
) -> Signal:
    """Tono armónico suave: el armónico k tiene amplitud 1/k**rolloff (más alto = más dulce).

    Los armónicos por encima de la frecuencia de Nyquist se omiten, así que no hay aliasing.
    """
    p = phase(frequency_hz, n_samples, sr)
    out = np.zeros(n_samples)
    for k in range(1, harmonics + 1):
        if k * frequency_hz < sr / 2:
            out += np.sin(k * p) / k**rolloff
    return out


def grain_cloud(
    onsets_s: Signal,
    frequencies_hz: Signal,
    durations_s: Signal,
    amplitudes: Signal,
    pans: Signal,
    noisiness: float,
    n_samples: int,
    rng: np.random.Generator,
    sr: int = SAMPLE_RATE,
    attacks_s: Signal | None = None,
) -> Signal:
    """Síntesis granular: muchos sonidos diminutos ("granos") repartidos en el tiempo y el espacio.

    Cada grano es una ráfaga corta que se apaga, con su tono y su posición estéreo.
    `noisiness` mezcla cada grano entre un seno puro (0: un destello) y una ráfaga de ruido
    blanco (1: un chasquido). Los granos de ruido son de banda ancha: se les da color
    filtrando el resultado con `spectral_filter`. `attacks_s` es el tiempo de subida de
    cada grano: corto es un chasquido, largo un soplo. Por defecto son 0,4 ms, más unos
    tres ciclos en los tonos para que no hagan clic.
    """
    out = np.zeros((2, n_samples))
    if attacks_s is None:
        attacks_s = 0.0004 + (1 - noisiness) * 3 / np.asarray(frequencies_hz)
    for onset, freq, dur, amp, position, attack in zip(
        onsets_s, frequencies_hz, durations_s, amplitudes, pans, attacks_s, strict=True
    ):
        start = int(onset * sr)
        if start >= n_samples:
            continue
        length = min(max(int(7 * dur * sr), 16), n_samples - start)  # cae hasta -60 dB
        t = np.arange(length) / sr
        envelope = np.exp(-t / dur) * (1 - np.exp(-t / attack))
        envelope *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, length))  # sin clic al final
        grain = np.zeros(length)
        if noisiness < 1:
            grain += (1 - noisiness) * np.sin(2 * np.pi * freq * t + rng.uniform(0, 2 * np.pi))
        if noisiness > 0:
            grain += noisiness * rng.standard_normal(length)
        out[:, start : start + length] += pan(amp * envelope * grain, float(position))
    return out
