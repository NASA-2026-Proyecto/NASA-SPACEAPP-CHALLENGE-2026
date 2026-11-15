import { createResampler } from '../data/scene-data.js';

const GAMMA = 0.5;
const MAX_ALPHA = 0.92;
const FLOOR = 0.04;
const FEATHER_CELLS = 12;
const MERCATOR_MAX_LAT = 85.0511287798;
const MAX_CANVAS_WIDTH = 1100; // el lienzo se vuelve a subir a la GPU en cada fotograma
const RAMP_SIZE = 256;
// Escalas con rampa (posición 0..1): por debajo de `clear` es transparente y a partir de
// `solid` tiene la opacidad máxima. En la logarítmica (un campo continuo, como el PM2.5)
// el aire limpio deja ver el mapa; en la lineal (datos puntuales, como los incendios)
// cualquier valor por encima de cero se ve.
const RAMP_FADE = {
  log: { clear: 0.08, solid: 0.45 },
  linear: { clear: 0.01, solid: 0.12 },
};

const smooth = (t) => t * t * (3 - 2 * t);
const mercatorY = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
const latFromMercatorY = (y) => (Math.atan(Math.sinh(y)) * 180) / Math.PI;
const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));

function buildGeometry(grid) {
  const periodic = Boolean(grid.lon_periodic);
  const west = grid.lon_min;
  const east = periodic ? grid.lon_min + 360 : grid.lon_min + (grid.n_lon - 1) * grid.lon_step;
  const south = Math.max(grid.lat_min, -MERCATOR_MAX_LAT);
  const north = Math.min(grid.lat_min + (grid.n_lat - 1) * grid.lat_step, MERCATOR_MAX_LAT);
  const wanted = periodic ? 3 : 4;
  const pixelsPerCell = Math.max(1, Math.min(wanted, Math.round(MAX_CANVAS_WIDTH / grid.n_lon)));
  const width = grid.n_lon * pixelsPerCell;
  const spanY = mercatorY(north) - mercatorY(south);
  const spanX = ((east - west) * Math.PI) / 180;
  const height = Math.round((width * spanY) / spanX);
  return { west, east, south, north, width, height, spanY, pixelsPerCell, periodic };
}

function buildPalette(species) {
  return new Map(
    species.map((item) => {
      const base = hexToRgb(item.color);
      const dark = base.map((v) => v * 0.6);
      const light = base.map((v) => v + (255 - v) * 0.45);
      return [item.id, { base, dark, light }];
    })
  );
}

// Tabla de colores a partir de las paradas de la rampa que publica el manifiesto
// (los colores de la propia barra de la NASA), interpolando entre paradas.
function buildRampTable(stops) {
  const colors = stops.map(hexToRgb);
  const table = new Uint8ClampedArray(RAMP_SIZE * 3);
  for (let i = 0; i < RAMP_SIZE; i += 1) {
    const position = (i / (RAMP_SIZE - 1)) * (colors.length - 1);
    const low = Math.min(Math.floor(position), colors.length - 2);
    const t = position - low;
    for (let channel = 0; channel < 3; channel += 1) {
      table[i * 3 + channel] = colors[low][channel] * (1 - t) + colors[low + 1][channel] * t;
    }
  }
  return table;
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
  const geometry = buildGeometry(scene.grid);
  const { width, height } = geometry;
  const lastStep = scene.time.steps - 1;

  const canvas = document.createElement('canvas');
  canvas.id = `${id}-canvas`;
  canvas.width = width;
  canvas.height = height;
  canvas.style.cssText = 'position:absolute;left:-9999px;top:0;';
  document.body.append(canvas);

  const context = canvas.getContext('2d');
  const image = context.createImageData(width, height);
  const lats = new Float64Array(height);
  const lons = new Float64Array(width);
  const yNorth = mercatorY(geometry.north);
  for (let r = 0; r < height; r += 1) {
    lats[r] = latFromMercatorY(yNorth - ((r + 0.5) / height) * geometry.spanY);
  }
  for (let c = 0; c < width; c += 1) {
    lons[c] = geometry.west + ((c + 0.5) / width) * (geometry.east - geometry.west);
  }

  // Desvanecimiento en los bordes solo si el recorte es regional.
  const featherPx = FEATHER_CELLS * geometry.pixelsPerCell;
  const edgeFade = (index, size) =>
    smooth(Math.min(1, Math.min(index + 0.5, size - index - 0.5) / featherPx));
  const fadeRows = Float32Array.from({ length: height }, (_, r) =>
    geometry.periodic ? 1 : edgeFade(r, height));
  const fadeCols = Float32Array.from({ length: width }, (_, c) =>
    geometry.periodic ? 1 : edgeFade(c, width));

  const resample = createResampler(scene, lats, lons);
  const field = new Float32Array(width * height);
  const palette = buildPalette(species);
  const rampTables = new Map();

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

  // Un solo color por especie: más claro y más opaco cuanto mayor es el valor.
  function paintTint(id) {
    const scale = scene.manifest.species[id].display_scale_max;
    const { base, dark, light } = palette.get(id);
    const data = image.data;
    for (let r = 0; r < height; r += 1) {
      for (let c = 0; c < width; c += 1) {
        const i = r * width + c;
        const offset = i * 4;
        const normalized = field[i] / scale;
        if (!(normalized > FLOOR)) {
          data[offset + 3] = 0;
          continue;
        }
        const shaped = Math.pow(Math.min((normalized - FLOOR) / (1 - FLOOR), 1), GAMMA);
        const low = Math.min(shaped / 0.5, 1);
        const high = Math.max((shaped - 0.5) / 0.5, 0);
        for (let channel = 0; channel < 3; channel += 1) {
          data[offset + channel] =
            shaped < 0.5
              ? dark[channel] + (base[channel] - dark[channel]) * low
              : base[channel] + (light[channel] - base[channel]) * high;
        }
        data[offset + 3] = shaped * MAX_ALPHA * 255 * fadeRows[r] * fadeCols[c];
      }
    }
  }

  // Escala (logarítmica o lineal) con la rampa de colores original, la de la barra de
  // la NASA. Los huecos (NaN: donde la imagen de origen no tenía dato) quedan transparentes.
  function paintRamp(id, scale) {
    if (!rampTables.has(id)) rampTables.set(id, buildRampTable(scale.ramp));
    const table = rampTables.get(id);
    const isLog = scale.kind === 'log';
    const start = isLog ? Math.log(scale.min) : scale.min;
    const span = (isLog ? Math.log(scale.max) : scale.max) - start;
    const { clear, solid } = RAMP_FADE[scale.kind];
    const data = image.data;
    for (let r = 0; r < height; r += 1) {
      for (let c = 0; c < width; c += 1) {
        const i = r * width + c;
        const offset = i * 4;
        const position = ((isLog ? Math.log(field[i]) : field[i]) - start) / span;
        if (!(position > clear)) {
          data[offset + 3] = 0;
          continue;
        }
        const clamped = Math.min(position, 1);
        const entry = Math.round(clamped * (RAMP_SIZE - 1)) * 3;
        data[offset] = table[entry];
        data[offset + 1] = table[entry + 1];
        data[offset + 2] = table[entry + 2];
        const strength = smooth(Math.min((clamped - clear) / (solid - clear), 1));
        data[offset + 3] = strength * MAX_ALPHA * 255 * fadeRows[r] * fadeCols[c];
      }
    }
  }

  // Lienzo con un paso exacto de una especie (se pinta la primera vez y se guarda).
  function stepCanvas(id, step) {
    if (stepCache.speciesId !== id) stepCache = { speciesId: id, canvases: new Map() };
    let cached = stepCache.canvases.get(step);
    if (!cached) {
      resample(id, step, field);
      const scale = scene.manifest.species[id].scale;
      if (scale?.ramp && RAMP_FADE[scale.kind]) paintRamp(id, scale);
      else paintTint(id);
      cached = document.createElement('canvas');
      cached.width = width;
      cached.height = height;
      cached.getContext('2d').putImageData(image, 0, 0);
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
    visible = Boolean(state.layers[layerId]) && palette.has(speciesId);
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
