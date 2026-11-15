// Motor de sonido (Web Audio). Cada dato mueve UN parámetro, siempre con la misma regla:
//
//   valor 0..1 (PM2.5 en la escala de la NASA)  -> tono (110 Hz x 2^(3v)) e intensidad
//   reparto por especie de aerosol              -> timbre (mezcla de voces)
//   tendencia                                   -> aviso corto de tres notas
//
// Sin datos de composición suena una voz neutra: el sonido es más simple, pero correcto.
const clamp = (v, min, max) => Math.min(max, Math.max(min, v));

const MIN_HZ = 110;
const OCTAVES = 3;
const NEUTRAL = 'neutral';

// Una voz por especie. `harmonics` son las amplitudes de los armónicos 1, 2, 3...;
// `beat` añade una copia ligeramente desafinada que produce un batido.
const VOICES = {
  [NEUTRAL]: { harmonics: [1, 0.25] },
  sea_salt: { harmonics: [1] }, // pura y lisa
  sulfate: { harmonics: [1, 0.5, 0.33] }, // brillante
  brown_carbon: { harmonics: [1, 0, 0.33, 0, 0.2, 0, 0.14] }, // hueca, solo armónicos impares
  black_carbon: { harmonics: [1, 0.6, 0.45, 0.35, 0.3, 0.25, 0.2, 0.15] }, // áspera y oscura
  dust: { harmonics: [1], beat: 1.006 }, // granulada, con batido
};

const CUE_HZ = 660;
const CUE_NOTES = { up: [1, 1.19, 1.5], down: [1.5, 1.19, 1], flat: [1.19, 1.19, 1.19] };
const CUE_STEP = 0.14;

export const valueToFrequency = (v) => MIN_HZ * 2 ** (clamp(v, 0, 1) * OCTAVES);
export const valueToLevel = (v) => 0.2 + 0.8 * clamp(v, 0, 1);

export function createAudioEngine() {
  let ctx = null;
  let voices = null; // id -> { oscillators: [{ node, ratio }], gain }
  let env = null;
  let analyser = null;
  let master = null;
  let playing = false;
  let volume = 0.35;
  let value = 0;
  let timbre = null; // { especie: peso } o null (voz neutra)
  let stopTimer = 0;

  function applyValue(immediate) {
    const t = ctx.currentTime;
    const f = valueToFrequency(value);
    const level = valueToLevel(value);
    for (const voice of voices.values()) {
      for (const { node, ratio } of voice.oscillators) {
        if (immediate) node.frequency.setValueAtTime(f * ratio, t);
        else node.frequency.setTargetAtTime(f * ratio, t, 0.08);
      }
    }
    if (immediate) env.gain.setValueAtTime(level, t);
    else env.gain.setTargetAtTime(level, t, 0.08);
  }

  function applyTimbre(immediate) {
    const t = ctx.currentTime;
    const total = timbre ? Object.values(timbre).reduce((sum, weight) => sum + weight, 0) : 0;
    for (const [id, voice] of voices) {
      const weight = total > 0 ? (timbre[id] ?? 0) / total : id === NEUTRAL ? 1 : 0;
      if (immediate) voice.gain.gain.setValueAtTime(weight, t);
      else voice.gain.gain.setTargetAtTime(weight, t, 0.15);
    }
  }

  function buildVoice({ harmonics, beat }) {
    const imag = new Float32Array([0, ...harmonics]);
    const wave = ctx.createPeriodicWave(new Float32Array(imag.length), imag);
    const gain = ctx.createGain();
    gain.gain.value = 0;
    const oscillators = (beat ? [1, beat] : [1]).map((ratio) => {
      const node = ctx.createOscillator();
      node.setPeriodicWave(wave);
      const part = ctx.createGain();
      part.gain.value = beat ? 0.5 : 1;
      node.connect(part).connect(gain);
      node.start();
      return { node, ratio };
    });
    gain.connect(env);
    return { oscillators, gain };
  }

  function build() {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    ctx = new AudioCtx();

    env = ctx.createGain();
    analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    master = ctx.createGain();
    master.gain.value = 0;

    voices = new Map(Object.entries(VOICES).map(([id, spec]) => [id, buildVoice(spec)]));
    env.connect(analyser);
    analyser.connect(master);
    master.connect(ctx.destination);

    applyValue(true);
    applyTimbre(true);
  }

  return {
    async start() {
      clearTimeout(stopTimer);
      if (!ctx) build();
      await ctx.resume();
      const t = ctx.currentTime;
      master.gain.cancelScheduledValues(t);
      master.gain.setTargetAtTime(volume, t, 0.05);
      playing = true;
    },

    stop() {
      if (!ctx) return;
      playing = false;
      const t = ctx.currentTime;
      master.gain.cancelScheduledValues(t);
      master.gain.setTargetAtTime(0, t, 0.06);
      stopTimer = setTimeout(() => {
        if (!playing) ctx.suspend();
      }, 400);
    },

    setValue(v) {
      value = clamp(v, 0, 1);
      if (ctx) applyValue(false);
    },

    // weights: { especie: peso } con las especies de VOICES, o null para la voz neutra
    setTimbre(weights) {
      timbre = weights;
      if (ctx) applyTimbre(false);
    },

    // Aviso de tendencia: tres notas que suben, bajan o se repiten
    playCue(direction) {
      const notes = CUE_NOTES[direction];
      if (!ctx || !playing || !notes) return;
      const start = ctx.currentTime + 0.05;
      notes.forEach((ratio, index) => {
        const at = start + index * CUE_STEP;
        const node = ctx.createOscillator();
        node.frequency.value = CUE_HZ * ratio;
        const gain = ctx.createGain();
        gain.gain.setValueAtTime(0, at);
        gain.gain.linearRampToValueAtTime(0.5, at + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.001, at + CUE_STEP);
        node.connect(gain).connect(analyser);
        node.start(at);
        node.stop(at + CUE_STEP + 0.02);
      });
    },

    setVolume(v) {
      volume = clamp(v, 0, 1);
      if (ctx && playing) {
        master.gain.setTargetAtTime(volume, ctx.currentTime, 0.03);
      }
    },

    isPlaying: () => playing,
    getAnalyser: () => analyser,
    getFrequency: () => valueToFrequency(value),
    getSampleRate: () => (ctx ? ctx.sampleRate : 48000),
  };
}
