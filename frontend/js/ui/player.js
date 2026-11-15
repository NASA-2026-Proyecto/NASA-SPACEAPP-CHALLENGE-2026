import { createClipPlayer } from '../audio/clip-player.js';
import { activeLayer } from '../core/layers.js';
import { fetchSoundClip, fetchSoundReading } from '../data/sound-api.js';
import { store } from '../state/app-store.js';
import { createWaveform } from './waveform.js';

const number = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1 });
const percent = new Intl.NumberFormat('es-ES', { style: 'percent', maximumFractionDigits: 0 });

const TEXT = {
  noLayer: 'Sin capa activa: no suena nada. Activa una capa de datos.',
  noPoint: (label) => `Haz clic en el globo para oír ${label.toLowerCase()} en ese punto.`,
  samePoint: (label) => `Pulsa reproducir para oír ${label.toLowerCase()} en el punto seleccionado.`,
  reading: 'Leyendo el punto…',
  rendering: 'Generando el sonido…',
  playing: 'Sonando',
  ready: 'Sonido listo: pulsa reproducir para oírlo otra vez.',
  silent: 'En este punto no suena nada.',
  notReady: 'Los datos de la NASA aún se están preparando. Inténtalo en unos segundos.',
  failed: 'No se pudo obtener el sonido. Inténtalo de nuevo.',
};

// El sonido del punto seleccionado. Qué suena lo decide la capa activa (solo puede haber
// una): sin capa, nada. Un clic en el globo pide el sonido a la API y lo reproduce; el
// botón lo para o lo repite.
export function initPlayer(root) {
  const engine = createClipPlayer();
  const playBtn = root.querySelector('[data-player-play]');
  const volume = root.querySelector('[data-player-volume]');
  const sub = root.querySelector('[data-player-sub]');
  const readLayer = root.querySelector('[data-readout-layer]');
  const readValue = root.querySelector('[data-readout-value]');
  const readLevel = root.querySelector('[data-readout-level]');
  const description = root.querySelector('[data-player-description]');
  const wave = createWaveform(root.querySelector('[data-player-wave]'), engine);

  let layer = activeLayer(store.getState());
  let point = null; // último punto en el que se hizo clic
  let clip = null; // sonido ya descargado de ese punto con esa capa: { buffer }
  let pending = null; // AbortController de la petición en curso

  function setPlaying(playing) {
    playBtn.setAttribute('aria-pressed', String(playing));
    playBtn.setAttribute('aria-label', playing ? 'Parar' : 'Reproducir');
    wave.wake();
  }

  function showReading(reading) {
    const audible = reading?.status === 'ok';
    readValue.textContent =
      reading?.value === undefined ? '—' : `${number.format(reading.value)} ${reading.unit}`;
    readLevel.textContent = audible ? percent.format(reading.intensity) : '—';
    description.textContent = reading?.description ?? '';
  }

  // Texto de reposo: qué hace falta para que suene algo
  const hint = () => {
    if (!layer) return TEXT.noLayer;
    return point ? TEXT.samePoint(layer.label) : TEXT.noPoint(layer.label);
  };

  function idle() {
    readLayer.textContent = layer?.label ?? '—';
    sub.textContent = hint();
    playBtn.disabled = !layer || !point;
    showReading(null);
  }

  function stop() {
    pending?.abort();
    pending = null;
    engine.stop();
    setPlaying(false);
  }

  function play() {
    engine.play(clip.buffer, () => {
      setPlaying(false);
      sub.textContent = TEXT.ready;
    });
    sub.textContent = TEXT.playing;
    setPlaying(true);
  }

  // Pide el sonido del punto con la capa activa y lo reproduce en cuanto llega
  async function load() {
    stop();
    clip = null;
    const controller = new AbortController();
    pending = controller;
    const current = () => pending === controller;

    engine.unlock(); // dentro del clic: después el navegador ya deja sonar
    engine.setVolume(Number(volume.value));
    playBtn.disabled = false;
    sub.textContent = TEXT.reading;
    showReading(null);
    try {
      const reading = await fetchSoundReading(layer.sound, point, controller.signal);
      if (!current()) return;
      showReading(reading);
      if (reading.status !== 'ok') {
        sub.textContent = TEXT.silent;
        return;
      }
      sub.textContent = TEXT.rendering;
      const buffer = await engine.decode(await fetchSoundClip(reading.audio, controller.signal));
      if (!current()) return;
      clip = { buffer };
      play();
    } catch (error) {
      if (!current()) return; // lo sustituyó otro clic o un cambio de capa
      console.warn('[sonido] Sin sonido para el punto:', error);
      sub.textContent = error.status === 503 ? TEXT.notReady : TEXT.failed;
    } finally {
      if (current()) pending = null;
    }
  }

  playBtn.addEventListener('click', () => {
    if (engine.isPlaying() || pending) {
      stop();
      sub.textContent = clip ? TEXT.ready : hint();
    } else if (clip) play();
    else load();
  });
  volume.addEventListener('input', () => engine.setVolume(Number(volume.value)));
  window.addEventListener('pagehide', stop);

  store.subscribe((state) => {
    const nextLayer = activeLayer(state);
    const nextPoint = state.reading?.point ?? null;

    if (nextLayer !== layer) {
      // Cambió la capa activa: lo que sonaba ya no corresponde a lo que se ve
      layer = nextLayer;
      stop();
      clip = null;
      idle();
    }
    if (nextPoint !== point) {
      point = nextPoint;
      if (layer) load();
      else idle();
    }
  });

  idle();
}
