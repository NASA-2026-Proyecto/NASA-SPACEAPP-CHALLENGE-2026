const clamp = (v, min, max) => Math.min(max, Math.max(min, v));

const MIN_HZ = 110;
const OCTAVES = 3;

export const valueToFrequency = (v) => MIN_HZ * 2 ** (clamp(v, 0, 1) * OCTAVES);
export const valueToLevel = (v) => 0.2 + 0.8 * clamp(v, 0, 1);

export function createAudioEngine() {
  let ctx = null;
  let osc1 = null;
  let osc2 = null;
  let env = null;
  let analyser = null;
  let master = null;
  let playing = false;
  let volume = 0.35;
  let value = 0;
  let stopTimer = 0;

  function applyValue(immediate) {
    const t = ctx.currentTime;
    const f = valueToFrequency(value);
    const level = valueToLevel(value);
    if (immediate) {
      osc1.frequency.setValueAtTime(f, t);
      osc2.frequency.setValueAtTime(f * 2, t);
      env.gain.setValueAtTime(level, t);
    } else {
      osc1.frequency.setTargetAtTime(f, t, 0.08);
      osc2.frequency.setTargetAtTime(f * 2, t, 0.08);
      env.gain.setTargetAtTime(level, t, 0.08);
    }
  }

  function build() {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    ctx = new AudioCtx();

    osc1 = ctx.createOscillator();
    osc1.type = 'sine';
    osc2 = ctx.createOscillator();
    osc2.type = 'triangle';

    const g1 = ctx.createGain();
    g1.gain.value = 0.7;
    const g2 = ctx.createGain();
    g2.gain.value = 0.2;

    env = ctx.createGain();
    analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    master = ctx.createGain();
    master.gain.value = 0;

    osc1.connect(g1).connect(env);
    osc2.connect(g2).connect(env);
    env.connect(analyser);
    analyser.connect(master);
    master.connect(ctx.destination);

    osc1.start();
    osc2.start();
    applyValue(true);
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