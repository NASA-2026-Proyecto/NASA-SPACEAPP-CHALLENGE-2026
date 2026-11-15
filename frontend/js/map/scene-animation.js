// Reloj de la animación de las escenas: recorre en bucle del paso más antiguo al más
// reciente, se detiene un momento en el último (el dato actual) y vuelve a empezar.
// Entrega un avance de 0 a 1; cada capa lo traduce a sus propios pasos.
const TRAVEL_MS = 9000;
const HOLD_MS = 2200;
const FRAME_MS = 1000 / 20; // 20 fotogramas por segundo bastan para un fundido

export function createSceneAnimation(onProgress) {
  let frame = 0;
  let startedAt = 0;
  let lastTick = 0;

  function tick(now) {
    frame = requestAnimationFrame(tick);
    if (now - lastTick < FRAME_MS) return;
    lastTick = now;
    const elapsed = (now - startedAt) % (TRAVEL_MS + HOLD_MS);
    onProgress(Math.min(elapsed / TRAVEL_MS, 1));
  }

  return {
    isRunning: () => frame !== 0,
    start() {
      if (frame) return;
      startedAt = performance.now();
      lastTick = 0;
      frame = requestAnimationFrame(tick);
    },
    // Al parar se vuelve al dato más reciente
    stop() {
      if (!frame) return;
      cancelAnimationFrame(frame);
      frame = 0;
      onProgress(1);
    },
  };
}
