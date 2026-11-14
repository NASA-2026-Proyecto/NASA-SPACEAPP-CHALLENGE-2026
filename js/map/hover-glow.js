// Al pasar el cursor por el mapa, los puntos de tierra cercanos se iluminan
// y se apagan poco a poco (mismo efecto que la Tierra de la portada).
const RADIUS_PX = 85;
const RISE = 0.35; // rapidez al encenderse
const FALL = 0.12; // rapidez al apagarse
const VISIBLE_COS = 0.12; // solo la cara visible del globo

const toRad = (deg) => (deg * Math.PI) / 180;

export function createHoverGlow(map, { source, layer, reducedMotion = false }) {
  const glow = new Map(); // id -> brillo actual
  let target = new Map(); // id -> brillo objetivo
  let pointer = null;
  let raf = 0;

  function isFacingCamera([lng, lat]) {
    const c = map.getCenter();
    const cos =
      Math.sin(toRad(c.lat)) * Math.sin(toRad(lat)) +
      Math.cos(toRad(c.lat)) * Math.cos(toRad(lat)) * Math.cos(toRad(lng - c.lng));
    return cos > VISIBLE_COS;
  }

  function measure() {
    target = new Map();
    if (pointer) {
      const { x, y } = pointer;
      const box = [[x - RADIUS_PX, y - RADIUS_PX], [x + RADIUS_PX, y + RADIUS_PX]];
      for (const feature of map.queryRenderedFeatures(box, { layers: [layer] })) {
        const coords = feature.geometry.coordinates;
        if (!isFacingCamera(coords)) continue;
        const p = map.project(coords);
        const distance = Math.hypot(p.x - x, p.y - y);
        if (distance >= RADIUS_PX) continue;
        const t = 1 - distance / RADIUS_PX;
        target.set(feature.id, t * t * (3 - 2 * t)); // suavizado
      }
    }
    for (const id of target.keys()) if (!glow.has(id)) glow.set(id, 0);
  }

  function frame() {
    raf = 0;
    for (const [id, current] of glow) {
      const goal = target.get(id) ?? 0;
      const next = reducedMotion ? goal : current + (goal - current) * (goal > current ? RISE : FALL);
      if (goal === 0 && next < 0.01) {
        glow.delete(id);
        map.setFeatureState({ source, id }, { glow: 0 });
      } else {
        glow.set(id, next);
        map.setFeatureState({ source, id }, { glow: next });
      }
    }
    if (glow.size) raf = requestAnimationFrame(frame);
  }

  const schedule = () => {
    if (!raf) raf = requestAnimationFrame(frame);
  };

  const onMouseMove = (event) => {
    pointer = event.point;
    measure();
    schedule();
  };
  const onMouseOut = () => {
    pointer = null;
    target = new Map();
    schedule();
  };
  // El globo gira solo: hay que recalcular aunque el ratón esté quieto
  const onMapMove = () => {
    if (!pointer) return;
    measure();
    schedule();
  };

  map.on('mousemove', onMouseMove);
  map.on('mouseout', onMouseOut);
  map.on('move', onMapMove);

  return {
    destroy() {
      map.off('mousemove', onMouseMove);
      map.off('mouseout', onMouseOut);
      map.off('move', onMapMove);
      cancelAnimationFrame(raf);
    },
  };
}
