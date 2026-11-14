import { createAudioEngine } from '../audio/audio-engine.js';
import { createSimulatedSource } from '../audio/simulated-source.js';
import { createWaveform } from './waveform.js';

const fmt = new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const band = (v) => (v < 0.33 ? 'baja' : v < 0.66 ? 'media' : 'alta');

export function initPlayer(root, { source = createSimulatedSource() } = {}) {
  const engine = createAudioEngine();
  const playBtn = root.querySelector('[data-player-play]');
  const volume = root.querySelector('[data-player-volume]');
  const readValue = root.querySelector('[data-readout-value]');
  const readPitch = root.querySelector('[data-readout-pitch]');
  const readLevel = root.querySelector('[data-readout-level]');
  const live = root.querySelector('[data-player-live]');
  const wave = createWaveform(root.querySelector('[data-player-wave]'), engine);

  let timer = 0;
  let lastBand = '';

  function update() {
    const v = source.getValue();
    engine.setValue(v);
    readValue.textContent = fmt.format(v);
    readPitch.textContent = `${Math.round(engine.getFrequency())} Hz`;
    readLevel.textContent = band(v);

    if (band(v) !== lastBand) {
      lastBand = band(v);
      live.textContent = `Señal simulada, intensidad ${lastBand}.`;
    }
  }

  async function play() {
    try {
      engine.setVolume(Number(volume.value));
      update();
      await engine.start();
      timer = setInterval(update, 100);
      playBtn.setAttribute('aria-pressed', 'true');
      playBtn.setAttribute('aria-label', 'Pausar');
      wave.wake();
    } catch (error) {
      console.error(error);
      live.textContent = 'No se pudo iniciar el audio en este navegador.';
    }
  }

  function pause() {
    clearInterval(timer);
    engine.stop();
    playBtn.setAttribute('aria-pressed', 'false');
    playBtn.setAttribute('aria-label', 'Reproducir');
    wave.wake();
  }

  playBtn.addEventListener('click', () => (engine.isPlaying() ? pause() : play()));
  volume.addEventListener('input', () => engine.setVolume(Number(volume.value)));
  window.addEventListener('pagehide', pause);
}