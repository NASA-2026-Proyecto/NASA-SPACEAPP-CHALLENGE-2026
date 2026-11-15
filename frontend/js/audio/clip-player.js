// Reproductor de clips (Web Audio). El sonido lo genera la API a partir del dato del punto;
// aquí solo se descodifica y se reproduce, pasando por un analizador para dibujar la onda.
const clamp = (v, min, max) => Math.min(max, Math.max(min, v));

export function createClipPlayer() {
  let ctx = null;
  let analyser = null;
  let master = null;
  let source = null; // el clip que está sonando
  let volume = 0.35;

  function build() {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    ctx = new AudioCtx();
    analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    master = ctx.createGain();
    master.gain.value = volume;
    analyser.connect(master);
    master.connect(ctx.destination);
  }

  function stop() {
    if (!source) return;
    source.onended = null;
    source.stop();
    source.disconnect();
    source = null;
  }

  return {
    // Hay que llamarlo dentro de un gesto del usuario (un clic): el navegador no deja
    // sonar nada hasta entonces.
    unlock() {
      if (!ctx) build();
      return ctx.resume();
    },

    // WAV (ArrayBuffer) -> AudioBuffer, que se puede reproducir las veces que haga falta
    decode(bytes) {
      if (!ctx) build();
      return ctx.decodeAudioData(bytes);
    },

    // Reproduce un clip desde el principio; `onEnded` solo se llama si llega al final
    play(buffer, onEnded) {
      stop();
      source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(analyser);
      source.onended = () => {
        source = null;
        onEnded?.();
      };
      source.start();
    },

    stop,

    setVolume(v) {
      volume = clamp(v, 0, 1);
      if (master) master.gain.setTargetAtTime(volume, ctx.currentTime, 0.03);
    },

    isPlaying: () => source !== null,
    getAnalyser: () => analyser,
  };
}
