// Lectura de un punto del globo a partir de las escenas ya descargadas (sin ir al servidor).
//
// Cada fuente tiene un papel y no se mezclan:
//   - Visualización diaria del EIC (PM2.5): CUÁNTO hay en ese punto.
//   - Modelo casi en tiempo real (GEOS-FP): DE QUÉ está hecho y HACIA DÓNDE va.
import { findScene } from '../catalog/scenes.js';
import { cellValueAt } from './scene-data.js';

export const PM25_SCENE = 'pm25-latest';
export const LIVE_SCENE = 'aerosol-latest';

const TREND_THRESHOLD = 0.1; // cambio relativo a partir del cual ya no es "estable"
const LEVELS = ['muy bajo', 'bajo', 'moderado', 'alto', 'muy alto'];

// Posición 0..1 en la escala de la NASA -> palabra. Es relativa a esa escala, no un
// índice de calidad del aire.
export const levelOf = (position) =>
  LEVELS[Math.min(LEVELS.length - 1, Math.floor(Math.max(position, 0) * LEVELS.length))];

export function emptyReading(point) {
  return { point, pm25: { status: 'loading' }, live: { status: 'loading' } };
}

// PM2.5 en µg/m³ y su posición en la escala logarítmica de la barra de color.
export function readPm25(scene, { lat, lon }) {
  const stamp = scene.time.stamps_utc.at(-1);
  const value = cellValueAt(scene, 'pm25', scene.time.steps - 1, lat, lon);
  if (value === null || !Number.isFinite(value)) return { status: 'empty', stamp };

  const { min, max } = scene.manifest.species.pm25.scale;
  const position = Math.min(1, Math.max(0, Math.log(value / min) / Math.log(max / min)));
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
