import { reducedMotionQuery } from '../core/motion.js';

const DEGREES_PER_SECOND = 2;
const MAX_ZOOM = 3.5;

export function startAutoSpin(map) {
  if (reducedMotionQuery.matches) return () => {};

  let active = true;

  function step() {
    if (!active || map.getZoom() > MAX_ZOOM) return;
    const center = map.getCenter();
    center.lng -= DEGREES_PER_SECOND;
    map.easeTo({ center, duration: 1000, easing: (t) => t });
  }

  function stop() {
    active = false;
    map.off('moveend', step);
  }

  map.on('moveend', step);
  for (const eventName of ['mousedown', 'touchstart', 'wheel']) {
    map.once(eventName, stop);
  }

  step();
  return stop;
}