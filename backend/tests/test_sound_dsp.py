import io
import wave

import numpy as np
import pytest

from app.services.sound import dsp
from app.services.sound.common import (
    compass,
    describe_stamp,
    direction_weights,
    fade_envelope,
    great_circle,
    number,
)

SR = dsp.SAMPLE_RATE


def tone(hz: float, seconds: float = 1.0, amplitude: float = 0.5) -> np.ndarray:
    return amplitude * np.sin(2 * np.pi * hz * np.arange(int(seconds * SR)) / SR)


def band_power(signal: np.ndarray, low: float, high: float) -> float:
    spectrum = np.abs(np.fft.rfft(signal)) ** 2
    freqs = np.fft.rfftfreq(signal.shape[-1], 1 / SR)
    return float(spectrum[..., (freqs >= low) & (freqs < high)].sum())


# --- Curvas, fase y posición -------------------------------------------------------


def test_control_curve_is_stretched_linearly():
    assert dsp.to_audio_rate([0.0, 1.0], 5).tolist() == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert dsp.to_audio_rate(0.3, 4).tolist() == [0.3] * 4


def test_phase_advances_one_turn_per_cycle():
    assert dsp.phase(100.0, SR)[-1] == pytest.approx(2 * np.pi * 100)


def test_pan_keeps_the_power_and_moves_the_sound():
    mono = np.ones(8)
    left, centre, right = dsp.pan(mono, -1.0), dsp.pan(mono, 0.0), dsp.pan(mono, 1.0)
    assert left[0].tolist() == [1.0] * 8 and np.allclose(left[1], 0)
    assert np.allclose(right[0], 0) and np.allclose(right[1], 1)
    assert np.allclose(centre[0], centre[1])
    assert np.allclose((centre**2).sum(axis=0), 1.0)
    assert np.allclose(dsp.pan(mono, 5.0), right)  # fuera de rango: se queda en el extremo


def test_soft_limit_rounds_peaks_and_leaves_quiet_sound_alone():
    signal = np.array([0.01, -0.01, 3.0, -3.0])
    limited = dsp.soft_limit(signal)
    assert limited[:2] == pytest.approx(signal[:2], rel=1e-3)
    assert np.abs(limited).max() < 0.95


# --- Filtros y ruido ---------------------------------------------------------------


def test_spectral_filter_keeps_only_the_band_asked_for():
    signal = tone(100) + tone(1000) + tone(8000)
    low = dsp.spectral_filter(signal, high_hz=300, order=4)
    high = dsp.spectral_filter(signal, low_hz=3000, order=4)
    assert band_power(low, 50, 200) > 100 * band_power(low, 500, 10000)
    assert band_power(high, 6000, 10000) > 100 * band_power(high, 50, 2000)
    assert np.allclose(dsp.spectral_filter(signal), signal)  # sin cortes no cambia nada


def test_coloured_noise_has_a_fixed_level_and_darker_colours_have_more_bass():
    rng = np.random.default_rng(0)
    white, brown = dsp.coloured_noise(SR, rng, 0.0), dsp.coloured_noise(SR, rng, 2.0)
    assert np.sqrt(np.mean(white**2)) == pytest.approx(0.25)
    assert np.sqrt(np.mean(brown**2)) == pytest.approx(0.25)
    bass_share = [band_power(x, 0, 200) / band_power(x, 0, SR / 2) for x in (white, brown)]
    assert bass_share[0] < 0.05 and bass_share[1] > 0.9


def test_fft_convolution_matches_the_direct_one():
    rng = np.random.default_rng(1)
    a, b = rng.standard_normal(200), rng.standard_normal(31)
    assert np.allclose(dsp.fft_convolve(a, b), np.convolve(a, b))


def test_reverb_adds_a_tail_and_keeps_the_length():
    click = np.zeros((2, SR))
    click[:, 100] = 1.0
    wet = dsp.reverb(click, np.random.default_rng(0), seconds=0.5, wet=0.5)
    assert wet.shape == click.shape
    assert np.abs(wet[:, 2000:10000]).max() > 0  # hay cola donde antes había silencio
    assert not np.allclose(wet[0], wet[1])  # cada oído tiene la suya
    assert np.abs(wet[:, SR // 2 + 2000 :]).max() < 0.01 * np.abs(wet).max()  # y se apaga


def test_additive_tone_leaves_out_harmonics_above_nyquist():
    low = dsp.additive(1000.0, SR, harmonics=4)
    assert band_power(low, 3900, 4100) > 0.001 * band_power(low, 900, 1100)
    high = dsp.additive(8000.0, SR, harmonics=4)  # el 3.º y el 4.º quedarían por encima de 22 kHz
    assert band_power(high, 15900, 16100) > 0.001 * band_power(high, 7900, 8100)
    assert band_power(high, 0, 7000) < 1e-6 * band_power(high, 7900, 8100)  # sin aliasing


# --- Granos ------------------------------------------------------------------------


def grains(noisiness: float, attacks: np.ndarray | None = None) -> np.ndarray:
    return dsp.grain_cloud(
        onsets_s=np.array([0.1, 0.5, 5.0]),  # el último cae fuera del sonido
        frequencies_hz=np.array([1000.0, 1000.0, 1000.0]),
        durations_s=np.array([0.01, 0.01, 0.01]),
        amplitudes=np.array([1.0, 1.0, 1.0]),
        pans=np.array([-1.0, 1.0, 0.0]),
        noisiness=noisiness,
        n_samples=SR,
        rng=np.random.default_rng(0),
        attacks_s=attacks,
    )


@pytest.mark.parametrize("noisiness", [0.0, 0.5, 1.0])
def test_grains_sound_where_and_when_they_are_placed(noisiness):
    cloud = grains(noisiness)
    first, second = slice(int(0.1 * SR), int(0.2 * SR)), slice(int(0.5 * SR), int(0.6 * SR))
    assert np.abs(cloud[0, first]).max() > 0.1 and np.allclose(cloud[1, first], 0)  # a la izquierda
    assert np.abs(cloud[1, second]).max() > 0.1 and np.allclose(cloud[0, second], 0, atol=1e-12)
    assert np.allclose(cloud[:, : int(0.09 * SR)], 0)  # nada antes del primero


def test_pure_grains_are_tones_and_noisy_ones_are_broadband():
    pure, noisy = grains(0.0), grains(1.0)
    in_tune = [band_power(x, 800, 1250) / band_power(x, 0, SR / 2) for x in (pure, noisy)]
    assert in_tune[0] > 0.9 and in_tune[1] < 0.2


def test_a_long_attack_softens_the_start_of_a_grain():
    sharp = grains(1.0, np.full(3, 0.00005))
    soft = grains(1.0, np.full(3, 0.005))
    start = slice(int(0.1 * SR), int(0.1 * SR) + 20)
    assert np.abs(soft[0, start]).max() < 0.5 * np.abs(sharp[0, start]).max()


# --- Volumen percibido y WAV -------------------------------------------------------


def test_loudness_follows_the_level_and_the_ear():
    mid = np.stack([tone(1000, 2.0)] * 2)
    assert dsp.loudness_lufs(mid) == pytest.approx(-6.0, abs=0.5)  # seno a -6 dBFS en los dos canales
    assert dsp.loudness_lufs(mid / 10) == pytest.approx(dsp.loudness_lufs(mid) - 20, abs=0.01)
    # Con el mismo nivel, un grave profundo parece más flojo
    assert dsp.loudness_lufs(np.stack([tone(30, 2.0)] * 2)) < dsp.loudness_lufs(mid) - 6


def test_loudness_ignores_silence():
    sound = np.stack([tone(1000, 2.0)] * 2)
    padded = np.concatenate([sound, np.zeros((2, 4 * SR))], axis=1)
    assert dsp.loudness_lufs(padded) == pytest.approx(dsp.loudness_lufs(sound), abs=0.5)
    assert dsp.loudness_lufs(np.zeros((2, SR))) == -70.0


def test_wav_is_16_bit_stereo_and_clips_instead_of_wrapping():
    stereo = np.array([[0.0, 0.5, 2.0], [0.0, -0.5, -2.0]])
    with wave.open(io.BytesIO(dsp.wav_bytes(stereo))) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (2, 2, SR)
        pcm = np.frombuffer(wav.readframes(3), dtype="<i2").reshape(3, 2)
    assert pcm.tolist() == [[0, 0], [16383, -16383], [32767, -32767]]


# --- Direcciones y textos ----------------------------------------------------------


def test_compass_names_the_nearest_of_eight_points():
    assert [compass(b) for b in (0, 44, 90, 180, 270, 350)] == [
        "norte",
        "noreste",
        "este",
        "sur",
        "oeste",
        "norte",
    ]


def test_great_circle_reaches_the_expected_points():
    lats, lons = great_circle(0.0, 0.0, [0, 90, 180, 270], 111.195)  # 1° de círculo máximo
    assert lats.tolist() == pytest.approx([1, 0, -1, 0], abs=1e-3)
    assert lons.tolist() == pytest.approx([0, 1, 0, -1], abs=1e-3)
    # Cruza la línea de cambio de fecha sin salirse de -180..180
    _, lon = great_circle(0.0, 179.5, 90, 111.195)
    assert float(lon) == pytest.approx(-179.5, abs=1e-3)


def test_direction_weights_lean_towards_the_data_but_surround_the_listener():
    weights = direction_weights(np.array([0.0, 0.0, 6.0, 2.0]))
    assert weights.sum() == pytest.approx(1.0)
    assert weights.tolist() == pytest.approx([0.125, 0.125, 0.5, 0.25])
    assert direction_weights(np.zeros(4)).tolist() == [0.25] * 4  # sin dato: de todas partes por igual


def test_fade_envelope_starts_and_ends_in_silence():
    envelope = fade_envelope(15 * SR, SR)
    assert envelope[0] == 0 and envelope[5 * SR] == 1
    assert np.all(envelope[12 * SR :] == 0)  # la cola queda para la reverberación


def test_numbers_and_dates_are_written_in_spanish():
    assert number(3.14159) == "3,1"
    assert number(25000.4, 0) == "25000"
    assert number(-0.04) == "0,0"
    assert number(-2.5) == "-2,5"
    assert describe_stamp("2026-11-14T21:30Z") == "14 nov 2026, 21:30 UTC"
    assert describe_stamp("2026-01-02T00:00Z") == "2 ene 2026, 00:00 UTC"
