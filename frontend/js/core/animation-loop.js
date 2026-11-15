import { reducedMotionQuery } from './motion.js';

export function createAnimationLoop({ onFrame, onStatic }) {
  let frameId = null;
  let lastTime = 0;

  function tick(now) {
    const delta = Math.min((now - lastTime) / 1000, 0.05);
    lastTime = now;
    onFrame(delta, now / 1000);
    frameId = requestAnimationFrame(tick);
  }

  function start() {
    if (frameId !== null || document.hidden) return;
    if (reducedMotionQuery.matches) {
      onStatic();
      return;
    }
    lastTime = performance.now();
    frameId = requestAnimationFrame(tick);
  }

  function stop() {
    if (frameId === null) return;
    cancelAnimationFrame(frameId);
    frameId = null;
  }

  function restart() {
    stop();
    start();
  }

  function onVisibilityChange() {
    if (document.hidden) stop();
    else start();
  }

  document.addEventListener('visibilitychange', onVisibilityChange);
  reducedMotionQuery.addEventListener('change', restart);

  function destroy() {
    stop();
    document.removeEventListener('visibilitychange', onVisibilityChange);
    reducedMotionQuery.removeEventListener('change', restart);
  }

  return { start, stop, destroy };
}