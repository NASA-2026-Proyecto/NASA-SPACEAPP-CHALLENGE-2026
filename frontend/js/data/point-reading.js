// Lectura de un punto del globo a partir de las escenas ya descargadas (sin ir al servidor).
// Qué se lee depende de la capa activa (LAYER_READERS): la ficha enseña lo mismo que se ve
// y se oye. Sin capa activa no se lee nada.
//
// En la capa de aerosoles cada fuente tiene un papel y no se mezclan:
//   - Visualización diaria del EIC (PM2.5): CUÁNTO hay en ese punto.
//   - Modelo casi en tiempo real (GEOS-FP): DE QUÉ está hecho y HACIA DÓNDE va.
import { findScene } from '../catalog/scenes.js';
import { cellValueAt } from './scene-data.js';

const PM25_SCENE = 'pm25-latest';
const LIVE_SCENE = 'aerosol-latest';
const FIRE_SCENE = 'fires-latest';
const RAIN_SCENE = 'precipitation-latest';

const TREND_THRESHOLD = 0.1; // cambio relativo a partir del cual ya no es "estable"
const LEVELS = ['muy bajo', 'bajo', 'moderado', 'alto', 'muy alto'];
const FIRE_REACH = 1; // celdas a cada lado que cuentan como "junto al punto" (3 x 3), como en el sonido
const WET_FROM = 0.05; // mm/h a partir de los cuales cae algo, como en el sonido
// Intensidad de lluvia (American Meteorological Society), en mm/h: límite superior y nombre
const RAIN_CATEGORIES = [
  [2.5, 'lluvia débil'],
  [7.6, 'lluvia moderada'],
  [Infinity, 'lluvia fuerte'],
];

// Posición 0..1 en la escala de la NASA -> palabra. Es relativa a esa escala, no un
// índice de calidad del aire.
export const levelOf = (position) =>
  LEVELS[Math.min(LEVELS.length - 1, Math.floor(Math.max(position, 0) * LEVELS.length))];

// Posición 0..1 de un valor en la escala de color del manifiesto (logarítmica o lineal)
function scalePosition({ kind, min, max }, value) {
  const position =
    kind === 'log' ? Math.log(value / min) / Math.log(max / min) : (value - min) / (max - min);
  return Math.min(1, Math.max(0, position || 0));
}

// PM2.5 en µg/m³ y su posición en la escala logarítmica de la barra de color.
export function readPm25(scene, { lat, lon }) {
  const stamp = scene.time.stamps_utc.at(-1);
  const value = cellValueAt(scene, 'pm25', scene.time.steps - 1, lat, lon);
  if (value === null || !Number.isFinite(value)) return { status: 'empty', stamp };

  const position = scalePosition(scene.manifest.species.pm25.scale, value);
  return { status: 'ok', value, position, level: levelOf(position), stamp };
}

// Reparto por especie en el último paso y tendencia del total en los pasos disponibles.
export function readAerosols(scene, { lat, lon }) {
  const catalog = findScene(LIVE_SCENE).species;
  const steps = scene.time.steps;
  const stamp = scene.time.stamps_utc.at(-1);
  const totals = new Array(steps).fill(0);

  const species = catalog.map(({ id, label, color }) => {
    let latest = 0;
    for (let step = 0; step < steps; step += 1) {
      const value = cellValueAt(scene, id, step, lat, lon) ?? 0;
      totals[step] += value;
      latest = value;
    }
    return { id, label, color, value: latest };
  });

  const total = totals[steps - 1];
  if (!(total > 0)) return { status: 'empty', stamp };
  for (const item of species) item.share = item.value / total;
  species.sort((a, b) => b.share - a.share);

  const change = totals[0] > 0 ? (total - totals[0]) / totals[0] : 0;
  const direction = change > TREND_THRESHOLD ? 'up' : change < -TREND_THRESHOLD ? 'down' : 'flat';
  const hours = ((steps - 1) * scene.time.step_minutes) / 60;

  return { status: 'ok', species, total, trend: { direction, change, hours }, stamp };
}

// Incendios junto al punto: la potencia radiativa (MW) del más fuerte en las 3 x 3 celdas
// de alrededor, en cuántas de ellas hay fuego y cómo ha ido cada día de la serie.
export function readFires(scene, { lat, lon }) {
  const { grid, time } = scene;
  const { scale } = scene.manifest.species.frp;
  const around = (step) => {
    const values = [];
    for (let dr = -FIRE_REACH; dr <= FIRE_REACH; dr += 1) {
      for (let dc = -FIRE_REACH; dc <= FIRE_REACH; dc += 1) {
        const cellLat = lat + dr * grid.lat_step;
        values.push(cellValueAt(scene, 'frp', step, cellLat, lon + dc * grid.lon_step) ?? 0);
      }
    }
    return values;
  };

  const series = time.stamps_utc.map((stamp, step) => {
    const value = Math.max(...around(step));
    return { stamp, value, position: scalePosition(scale, value) };
  });
  const newest = around(time.steps - 1);
  const value = series.at(-1).value;
  return {
    status: value > 0 ? 'ok' : 'empty',
    value,
    burning: newest.filter((cell) => cell > 0).length,
    cells: newest.length,
    series,
    stamp: time.stamps_utc.at(-1),
  };
}

// Precipitación en el punto: lluvia y nieve (mm/h) en el último paso y en cada paso de la serie.
export function readPrecipitation(scene, { lat, lon }) {
  const { time } = scene;
  const { scale } = scene.manifest.species.rain;
  const series = time.stamps_utc.map((stamp, step) => {
    const rain = cellValueAt(scene, 'rain', step, lat, lon) ?? 0;
    const snow = cellValueAt(scene, 'snow', step, lat, lon) ?? 0;
    const value = rain + snow;
    return { stamp, rain, snow, value, wet: value >= WET_FROM, position: scalePosition(scale, value) };
  });
  const { rain, snow } = series.at(-1);
  const wet = rain >= WET_FROM || snow >= WET_FROM;
  return {
    status: wet ? 'ok' : 'empty',
    rain,
    snow,
    snowing: snow >= WET_FROM,
    category: rain >= WET_FROM ? RAIN_CATEGORIES.find(([top]) => rain < top)[1] : null,
    series,
    stamp: time.stamps_utc.at(-1),
  };
}

// Qué partes tiene la lectura con cada capa activa: parte -> escena de la que sale y lector.
// Las claves de fuera son los ids de las capas de js/config.js.
export const LAYER_READERS = {
  aerosol: {
    pm25: { sceneId: PM25_SCENE, read: readPm25 },
    live: { sceneId: LIVE_SCENE, read: readAerosols },
  },
  fire: { fires: { sceneId: FIRE_SCENE, read: readFires } },
  rain: { precipitation: { sceneId: RAIN_SCENE, read: readPrecipitation } },
};

// Lectura recién pedida: todas las partes de la capa, aún cargando (ninguna si no hay capa)
export function emptyReading(point, layerId) {
  const parts = Object.keys(LAYER_READERS[layerId] ?? {});
  return { point, layerId, parts: Object.fromEntries(parts.map((key) => [key, { status: 'loading' }])) };
}
