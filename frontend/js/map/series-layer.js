import { createResampler } from '../data/scene-data.js';
import { buildGeometry } from './scene-geometry.js';
import { createRasterPainter } from './painters/raster-painter.js';
import { createEmberPainter, EMBER_CANVAS_WIDTH } from './painters/ember-painter.js';
import { FIELD_MATERIALS } from './painters/materials.js';

// Ancho máximo del lienzo (se vuelve a subir a la GPU en cada fotograma): un campo liso
// no gana nada con más píxeles que celdas; una textura sí.
const FIELD_CANVAS_WIDTH = 1100;
const TEXTURED_CANVAS_WIDTH = 1440;

// Cómo se pinta cada especie, según su `material` en el catálogo (js/catalog/scenes.js):
// brasas (incendios) o un campo, liso o con la textura de js/map/painters/materials.js.
function painterKind(species) {
  if (species.material === 'embers') {
    return { create: createEmberPainter, canvasWidth: EMBER_CANVAS_WIDTH, usesWorkspace: false };
  }
  if (species.material && !FIELD_MATERIALS[species.material]) {
    throw new Error(`Material desconocido: ${species.material}`);
  }
  const canvasWidth = species.material ? TEXTURED_CANVAS_WIDTH : FIELD_CANVAS_WIDTH;
  return { create: createRasterPainter, canvasWidth, usesWorkspace: true };
}

// Dibuja una escena (serie de mallas) como capa ráster sobre el globo.
//   id       -> id de la fuente y la capa en el mapa
//   layerId  -> capa del panel a la que pertenece (visibilidad, opacidad y especie elegida)
//   species  -> especies de esta escena; la capa solo se ve si la elegida es una de ellas
//
// La escena se recorre en el tiempo con setProgress(0..1): 0 es el paso más antiguo y 1
// el más reciente. Cada paso se pinta una sola vez en su propio lienzo; entre dos pasos
// se funden esos dos lienzos, que es barato y permite animar con fluidez.
export function createSeriesLayer(map, { id, layerId, scene, species, beforeId }) {
  const canvasWidth = Math.max(...species.map((item) => painterKind(item).canvasWidth));
  const geometry = buildGeometry(scene.grid, canvasWidth);
  const { width, height } = geometry;
  const lastStep = scene.time.steps - 1;

  const canvas = document.createElement('canvas');
  canvas.id = `${id}-canvas`;
  canvas.width = width;
  canvas.height = height;
  canvas.style.cssText = 'position:absolute;left:-9999px;top:0;';
  document.body.append(canvas);
  const context = canvas.getContext('2d');

  // Búferes de los pintores de campo: se crean la primera vez que alguno los necesita
  const offscreen = () => {
    const extra = document.createElement('canvas');
    extra.width = width;
    extra.height = height;
    return extra;
  };
  let workspace = null;
  const getWorkspace = () => {
    workspace ??= {
      field: new Float32Array(width * height),
      density: new Float32Array(width * height),
      image: context.createImageData(width, height),
      layer: offscreen(), // el dato pintado, para dibujarlo encima de su nube
      cloud: offscreen(),
      resample: createResampler(scene, geometry.lats, geometry.lons),
    };
    return workspace;
  };
  const speciesById = new Map(species.map((item) => [item.id, item]));
  const painters = new Map();
  function painterOf(speciesId) {
    if (!painters.has(speciesId)) {
      const item = speciesById.get(speciesId);
      const kind = painterKind(item);
      painters.set(
        speciesId,
        kind.create(item, { scene, geometry, workspace: kind.usesWorkspace ? getWorkspace() : null })
      );
    }
    return painters.get(speciesId);
  }

  // Pasos ya pintados de la especie que se está viendo: índice de paso -> lienzo
  let stepCache = { speciesId: null, canvases: new Map() };
  let visible = false;
  let speciesId = null;
  let progress = 1;
  let drawn = { speciesId: null, position: null };

  map.addSource(id, {
    type: 'canvas',
    canvas: canvas.id,
    animate: true,
    coordinates: [
      [geometry.west, geometry.north],
      [geometry.east, geometry.north],
      [geometry.east, geometry.south],
      [geometry.west, geometry.south],
    ],
  });
  map.addLayer(
    {
      id,
      type: 'raster',
      source: id,
      layout: { visibility: 'none' },
      paint: { 'raster-opacity': 0.85, 'raster-fade-duration': 0 },
    },
    beforeId
  );

  // Lienzo con un paso exacto de una especie (se pinta la primera vez y se guarda).
  function stepCanvas(id, step) {
    if (stepCache.speciesId !== id) stepCache = { speciesId: id, canvases: new Map() };
    let cached = stepCache.canvases.get(step);
    if (!cached) {
      cached = document.createElement('canvas');
      cached.width = width;
      cached.height = height;
      painterOf(id)(cached.getContext('2d'), step);
      stepCache.canvases.set(step, cached);
    }
    return cached;
  }

  function draw() {
    if (!visible) return;
    const position = progress * lastStep;
    if (drawn.speciesId === speciesId && drawn.position === position) return;
    drawn = { speciesId, position };

    const s0 = Math.floor(position);
    const s1 = Math.min(s0 + 1, lastStep);
    const mix = position - s0;
    context.clearRect(0, 0, width, height);
    if (mix === 0 || s1 === s0) {
      context.globalCompositeOperation = 'source-over';
      context.globalAlpha = 1;
      context.drawImage(stepCanvas(speciesId, s0), 0, 0);
      return;
    }
    // "lighter" suma los dos pasos con sus pesos: es la interpolación lineal exacta
    context.globalCompositeOperation = 'lighter';
    context.globalAlpha = 1 - mix;
    context.drawImage(stepCanvas(speciesId, s0), 0, 0);
    context.globalAlpha = mix;
    context.drawImage(stepCanvas(speciesId, s1), 0, 0);
  }

  function sync(state) {
    speciesId = state.species[layerId];
    visible = Boolean(state.layers[layerId]) && speciesById.has(speciesId);
    map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
    map.setPaintProperty(id, 'raster-opacity', state.opacity[layerId]);
    draw();
  }

  // 0 = paso más antiguo de la escena, 1 = el más reciente
  function setProgress(value) {
    progress = Math.min(1, Math.max(0, value));
    draw();
  }

  function destroy() {
    if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource(id)) map.removeSource(id);
    canvas.remove();
  }

  return { sync, setProgress, isVisible: () => visible, destroy };
}
