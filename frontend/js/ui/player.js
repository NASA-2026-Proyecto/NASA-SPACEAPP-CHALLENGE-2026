import { createAudioEngine } from '../audio/audio-engine.js';
import { createSimulatedSource } from '../audio/simulated-source.js';
import { store } from '../state/app-store.js';
import { formatPm25 } from './point-card.js';
import { createWaveform } from './waveform.js';

const fmt = new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const percent = new Intl.NumberFormat('es-ES', { style: 'percent', maximumFractionDigits: 0 });

const band = (v) => (v < 0.33 ? 'baja' : v < 0.66 ? 'media' : 'alta');
const TREND_WORDS = { up: 'en aumento', down: 'en descenso', flat: 'estable' };

const DEMO_TEXT = { title: 'Señal de demostración', sub: 'Índice simulado: haz clic en el globo' };
const POINT_TEXT = { title: 'Sonido del punto', sub: 'PM2.5 del EIC + composición GEOS-FP' };

// Lo que suena describe el punto seleccionado en el globo (state.reading). Hasta el
// primer clic, o si ese punto no tiene dato de PM2.5, suena la señal de demostración.
export function initPlayer(root, { demo = createSimulatedSource() } = {}) {
  const engine = createAudioEngine();
  const playBtn = root.querySelector('[data-player-play]');
  const volume = root.querySelector('[data-player-volume]');
  const title = root.querySelector('[data-player-title]');
  const sub = root.querySelector('[data-player-sub]');
  const readValue = root.querySelector('[data-readout-value]');
  const readPitch = root.querySelector('[data-readout-pitch]');
  const readLevel = root.querySelector('[data-readout-level]');
  const live = root.querySelector('[data-player-live]');
  const wave = createWaveform(root.querySelector('[data-player-wave]'), engine);

  let timer = 0;
  let lastBand = '';
  let described = null; // última lectura ya anunciada (PM2.5)
  let cued = null; // última lectura cuyo aviso de tendencia ya sonó

  const pointReading = () => {
    const { reading } = store.getState();
    return reading?.pm25.status === 'ok' ? reading : null;
  };

  function describe(reading) {
    const parts = [
      `Punto seleccionado: PM2.5 ${formatPm25(reading.pm25.value)} microgramos por metro cúbico, nivel ${reading.pm25.level}.`,
    ];
    if (reading.live.status === 'ok') {
      const [main] = reading.live.species;
      parts.push(
        `Predomina ${main.label}, ${percent.format(main.share)}.`,
        `Aerosoles ${TREND_WORDS[reading.live.trend.direction]}.`
      );
    }
    return parts.join(' ');
  }

  function updateFromPoint(reading) {
    const { pm25, live: mix } = reading;
    engine.setValue(pm25.position);
    readValue.textContent = `${formatPm25(pm25.value)} µg/m³`;
    readLevel.textContent = pm25.level;

    if (mix.status === 'ok') {
      engine.setTimbre(Object.fromEntries(mix.species.map((item) => [item.id, item.share])));
      if (cued !== reading) {
        cued = reading;
        engine.playCue(mix.trend.direction);
        live.textContent = describe(reading);
      }
    } else {
      engine.setTimbre(null);
    }
    if (described !== reading.point) {
      described = reading.point;
      live.textContent = describe(reading);
    }
  }

  function updateFromDemo() {
    const v = demo.getValue();
    engine.setValue(v);
    engine.setTimbre(null);
    readValue.textContent = fmt.format(v);
    readLevel.textContent = band(v);
    if (band(v) !== lastBand) {
      lastBand = band(v);
      live.textContent = `Señal simulada, intensidad ${lastBand}.`;
    }
  }

  function update() {
    const reading = pointReading();
    const text = reading ? POINT_TEXT : DEMO_TEXT;
    if (title && title.textContent !== text.title) title.textContent = text.title;
    if (sub && sub.textContent !== text.sub) sub.textContent = text.sub;

    if (reading) updateFromPoint(reading);
    else updateFromDemo();
    readPitch.textContent = `${Math.round(engine.getFrequency())} Hz`;
  }

  async function play() {
    try {
      engine.setVolume(Number(volume.value));
      cued = null; // al empezar a sonar, el aviso de tendencia del punto actual se oye
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

  // Con el sonido parado, los indicadores también siguen al punto seleccionado
  store.subscribe(() => {
    if (!engine.isPlaying()) update();
  });
}
