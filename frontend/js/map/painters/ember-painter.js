// Pintor de brasas, para datos puntuales como los incendios (al estilo de las
// visualizaciones del SVS de la NASA): cada celda con valor es un punto encendido, con un
// resplandor de llama alrededor y humo encima. Donde hay muchos fuegos juntos los
// resplandores se suman y el frente brilla más.
//
// Los colores son de llama (rojo → naranja → ámbar, del fuego más débil al más fuerte) y
// no la barra amarilla de la NASA, para que de noche no se confundan con las luces de las
// ciudades, que son blanco-amarillentas.
//
// Solo cambia el aspecto: los valores son los de cada celda, sin interpolar, y la ficha y
// el sonido siguen leyendo la escena original.
import { buildRampTable } from '../scene-geometry.js';
import { applyNoiseMask, noiseMaskCanvas, sharedNoise } from './noise.js';

// Ancho máximo del lienzo de una escena con brasas: más que el de un campo, porque un
// punto necesita más píxeles por celda que una mancha.
export const EMBER_CANVAS_WIDTH = 1600;

const LEVELS = 32; // brasas distintas (por intensidad); se dibujan una vez y se reutilizan
const SPRITE_SIZE = 64;
const CLEAR = 0.01; // por debajo de esta posición en la escala no hay fuego
const JITTER = 0.35; // desplazamiento máximo del centro, en celdas (rompe la cuadrícula)
// Del fuego más débil al más fuerte
const FLAME_RAMP = ['#8c1206', '#c8280c', '#ec4a12', '#ff7419', '#ff9a2e', '#ffbb55'];
const HOT_CENTRE = [255, 222, 160];
const SMOKE_GREY = [112, 104, 98];
// Tres pasadas, en este orden:
//   humo       -> nubes grises grandes y tenues, recortadas en jirones y algo desplazadas
//                 de su fuego, para que no queden centradas en él
//   resplandor -> se suma con el de sus vecinas ("lighter"), así un frente brilla más que
//                 un fuego suelto, y se recorta con crestas de ruido para que tenga
//                 lenguas como una llama y no sea un círculo
//   núcleo     -> el punto encendido, con "screen", que aclara sin quemar a blanco
// Radios en celdas: el de la brasa más débil y lo que crece la más fuerte.
const SMOKE = { radius: 3.2, growth: 3.5, alpha: 0.14, shift: 1.2, opacity: 0.85 };
const HALO = { radius: 1.3, growth: 1.8, alpha: 0.3 };
const CORE = { radius: 0.4, growth: 0.7, alpha: 0.95 };
const SMOKE_TEXTURE = { periodX: 6, periodY: 12, octaves: 5, warp: 2.4, seed: 101 };
const FLAME_TEXTURE = { periodX: 40, periodY: 40, octaves: 4, warp: 1.4, ridged: true, seed: 103 };
const DRIFT = [3, 0]; // la textura se mueve un poco entre pasos, en píxeles

const mix = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
const rgba = (rgb, alpha) => `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`;

// Número pseudoaleatorio estable en [0, 1) para una celda: el mismo en todos los pasos,
// para que las brasas no tiemblen durante la animación.
function hash(row, col, salt) {
  let h = Math.imul(row + 0x9e37, 0x85ebca6b) ^ Math.imul(col + 0x7f4a, 0xc2b2ae35) ^ salt;
  h = Math.imul(h ^ (h >>> 15), 0x2c1b3c6d);
  h = Math.imul(h ^ (h >>> 12), 0x297a2d39);
  return ((h ^ (h >>> 15)) >>> 0) / 4294967296;
}

function sprite(paintGradient) {
  const canvas = document.createElement('canvas');
  canvas.width = SPRITE_SIZE;
  canvas.height = SPRITE_SIZE;
  const context = canvas.getContext('2d');
  const half = SPRITE_SIZE / 2;
  const gradient = context.createRadialGradient(half, half, 0, half, half, half);
  paintGradient(gradient);
  context.fillStyle = gradient;
  context.fillRect(0, 0, SPRITE_SIZE, SPRITE_SIZE);
  return canvas;
}

// Resplandor: del color de la llama a un rojo oscuro que se apaga suavemente.
const haloSprite = (flame, ember) =>
  sprite((gradient) => {
    gradient.addColorStop(0, rgba(mix(ember, flame, 0.6), 1));
    gradient.addColorStop(0.35, rgba(ember, 0.45));
    gradient.addColorStop(1, rgba(ember, 0));
  });

// Núcleo de intensidad t (0..1): centro caliente, el color de la llama y un borde corto.
const coreSprite = (flame, t) =>
  sprite((gradient) => {
    gradient.addColorStop(0, rgba(mix(flame, HOT_CENTRE, 0.1 + 0.45 * t), 1));
    gradient.addColorStop(0.4, rgba(flame, 0.9));
    gradient.addColorStop(1, rgba(flame, 0));
  });

// Humo: gris, muy tenue, que se acumula donde hay muchos fuegos.
const smokeSprite = () =>
  sprite((gradient) => {
    gradient.addColorStop(0, rgba(SMOKE_GREY, 1));
    gradient.addColorStop(0.5, rgba(SMOKE_GREY, 0.5));
    gradient.addColorStop(1, rgba(SMOKE_GREY, 0));
  });

function offscreen(width, height) {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

// Crea el pintor de una especie (misma interfaz que createRasterPainter).
export function createEmberPainter(species, { scene, geometry }) {
  const { grid } = scene;
  const { width, height, pixelsPerCell, periodic, south, north, fadeRows, fadeCols } = geometry;
  const scale = scene.manifest.species[species.id].scale;
  const min = scale?.min ?? 0;
  const span = (scale?.max ?? scene.manifest.species[species.id].display_scale_max) - min;

  const table = buildRampTable(FLAME_RAMP, LEVELS);
  const colourAt = (level) => [table[level * 3], table[level * 3 + 1], table[level * 3 + 2]];
  const ember = colourAt(0);
  const halos = Array.from({ length: LEVELS }, (_, level) => haloSprite(colourAt(level), ember));
  const cores = Array.from({ length: LEVELS }, (_, level) =>
    coreSprite(colourAt(level), level / (LEVELS - 1)));
  const smoke = smokeSprite();
  const smokes = Array.from({ length: LEVELS }, () => smoke);
  const smokeMask = noiseMaskCanvas(sharedNoise(SMOKE_TEXTURE), { contrast: 1.8 });
  const flameMask = noiseMaskCanvas(sharedNoise(FLAME_TEXTURE), { contrast: 1.6, floor: 0.3 });
  const smokeLayer = offscreen(width, height);
  const glowLayer = offscreen(width, height);

  // Posición de cada fila y columna de la malla en el lienzo, calculada una sola vez
  const rowY = Float64Array.from({ length: grid.n_lat }, (_, row) =>
    geometry.yOf(grid.lat_min + row * grid.lat_step));
  const colX = Float64Array.from({ length: grid.n_lon }, (_, col) =>
    geometry.xOf(grid.lon_min + col * grid.lon_step));

  function stamp(context, sprite, x, y, radius) {
    const size = radius * 2;
    context.drawImage(sprite, x - radius, y - radius, size, size);
    if (!periodic) return;
    // Una brasa junto al antimeridiano también asoma por el otro borde del lienzo
    if (x < radius) context.drawImage(sprite, x + width - radius, y - radius, size, size);
    if (x > width - radius) context.drawImage(sprite, x - width - radius, y - radius, size, size);
  }

  // Brasas de un paso: posición en el lienzo, intensidad y opacidad de cada celda con fuego
  function embersOf(step) {
    const values = scene.values[species.id];
    const base = step * grid.n_lat * grid.n_lon;
    const embers = [];
    for (let row = 0; row < grid.n_lat; row += 1) {
      const lat = grid.lat_min + row * grid.lat_step;
      if (lat < south || lat > north) continue;
      for (let col = 0; col < grid.n_lon; col += 1) {
        const position = (values[base + row * grid.n_lon + col] - min) / span;
        if (!(position > CLEAR)) continue;
        const x = colX[col] + (hash(row, col, 1) - 0.5) * 2 * JITTER * pixelsPerCell;
        const y = rowY[row] + (hash(row, col, 2) - 0.5) * 2 * JITTER * pixelsPerCell;
        const pixelRow = Math.min(height - 1, Math.max(0, Math.round(y)));
        const pixelCol = Math.min(width - 1, Math.max(0, Math.round(x)));
        const t = Math.min(position, 1);
        embers.push({ x, y, t, fade: fadeRows[pixelRow] * fadeCols[pixelCol] });
      }
    }
    return embers;
  }

  function pass(context, embers, sprites, { radius, growth, alpha, shift = 0 }) {
    for (const { x, y, t, fade } of embers) {
      context.globalAlpha = alpha * (0.6 + 0.4 * Math.sqrt(t)) * fade;
      const size = pixelsPerCell * (radius + growth * Math.sqrt(t));
      stamp(context, sprites[Math.round(t * (LEVELS - 1))], x + shift * pixelsPerCell, y, size);
    }
  }

  // Dibuja una pasada en una capa aparte y la recorta con una máscara de ruido.
  function maskedPass(layer, embers, sprites, settings, { mask, offset, operation }) {
    const context = layer.getContext('2d');
    context.clearRect(0, 0, width, height);
    context.globalCompositeOperation = operation;
    pass(context, embers, sprites, settings);
    context.globalCompositeOperation = 'source-over';
    context.globalAlpha = 1;
    applyNoiseMask(context, mask, offset);
    return layer;
  }

  // Pinta un paso exacto en el contexto (vacío) de su lienzo.
  return function paint(context, step) {
    const embers = embersOf(step);
    const offset = DRIFT.map((pixels) => step * pixels);
    const smokeDone = maskedPass(smokeLayer, embers, smokes, SMOKE, {
      mask: smokeMask,
      offset,
      operation: 'source-over',
    });
    const glowDone = maskedPass(glowLayer, embers, halos, HALO, {
      mask: flameMask,
      offset,
      operation: 'lighter',
    });
    context.globalAlpha = SMOKE.opacity;
    context.drawImage(smokeDone, 0, 0);
    context.globalAlpha = 1;
    context.globalCompositeOperation = 'lighter';
    context.drawImage(glowDone, 0, 0);
    context.globalCompositeOperation = 'screen';
    pass(context, embers, cores, CORE);
    context.globalCompositeOperation = 'source-over';
    context.globalAlpha = 1;
  };
}
