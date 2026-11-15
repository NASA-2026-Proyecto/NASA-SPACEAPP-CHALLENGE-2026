// Texturas de ruido para los materiales de las capas (bruma, nubes, humo, llamas...).
//
// Ruido de gradiente (Perlin) periódico, sumado en octavas (fBm) y, si se pide, deformado
// por sí mismo (domain warping), que es lo que da formas de nube o de jirón. La textura
// es periódica en los dos ejes, así que se puede repetir sobre el lienzo sin costuras.
// Solo cambia el aspecto de una capa: nunca crea ni quita datos.

export const NOISE_SIZE = 512; // lado de la textura en píxeles (potencia de 2)

const TAU = Math.PI * 2;
const fade = (t) => t * t * t * (t * (t * 6 - 15) + 10);

function hash(x, y, seed) {
  let h = Math.imul(x + 0x632b, 0x85ebca6b) ^ Math.imul(y + 0x2f1d, 0xc2b2ae35) ^ Math.imul(seed, 0x27d4eb2f);
  h = Math.imul(h ^ (h >>> 15), 0x2c1b3c6d);
  h = Math.imul(h ^ (h >>> 12), 0x297a2d39);
  return ((h ^ (h >>> 15)) >>> 0) / 4294967296;
}

// Retícula de una octava: un gradiente unitario por nudo, calculado una sola vez (así el
// bucle por píxel solo suma y multiplica). Periódica: el nudo (px, y) es el nudo (0, y).
function lattice(px, py, seed) {
  const gx = new Float32Array(px * py);
  const gy = new Float32Array(px * py);
  for (let iy = 0; iy < py; iy += 1) {
    for (let ix = 0; ix < px; ix += 1) {
      const angle = hash(ix, iy, seed) * TAU;
      gx[iy * px + ix] = Math.cos(angle);
      gy[iy * px + ix] = Math.sin(angle);
    }
  }
  return { px, py, gx, gy };
}

// Ruido de gradiente en (x, y) sobre una retícula periódica. Devuelve ~[-0.7, 0.7].
function perlin(x, y, { px, py, gx, gy }) {
  const fx0 = Math.floor(x);
  const fy0 = Math.floor(y);
  const fx = x - fx0;
  const fy = y - fy0;
  const x0 = ((fx0 % px) + px) % px;
  const y0 = ((fy0 % py) + py) % py;
  const x1 = x0 + 1 === px ? 0 : x0 + 1;
  const row0 = y0 * px;
  const row1 = (y0 + 1 === py ? 0 : y0 + 1) * px;
  const n00 = gx[row0 + x0] * fx + gy[row0 + x0] * fy;
  const n10 = gx[row0 + x1] * (fx - 1) + gy[row0 + x1] * fy;
  const n01 = gx[row1 + x0] * fx + gy[row1 + x0] * (fy - 1);
  const n11 = gx[row1 + x1] * (fx - 1) + gy[row1 + x1] * (fy - 1);
  const u = fade(fx);
  const top = n00 + (n10 - n00) * u;
  const bottom = n01 + (n11 - n01) * u;
  return top + (bottom - top) * fade(fy);
}

// Octavas de un fBm: cada una con el doble de frecuencia y `gain` veces la amplitud.
function octavesOf({ periodX, periodY, octaves, gain, seed }) {
  return Array.from({ length: octaves }, (_, octave) => ({
    lattice: lattice(periodX << octave, periodY << octave, seed + octave),
    frequency: 1 << octave,
    amplitude: gain ** octave,
  }));
}

function fbm(x, y, octaves) {
  let sum = 0;
  for (const { lattice: grid, frequency, amplitude } of octaves) {
    sum += amplitude * perlin(x * frequency, y * frequency, grid);
  }
  return sum;
}

// Crea una textura de ruido de NOISE_SIZE × NOISE_SIZE con valores en [0, 1].
//   periodX, periodY -> tamaño de las formas grandes: celdas de ruido a lo ancho y a lo alto
//                       (más celdas a lo ancho que a lo alto = formas alargadas en vertical,
//                       y al revés: jirones horizontales)
//   octaves, gain    -> detalle fino: cuántas octavas y cuánto pesa cada una
//   warp             -> deformación (0 = ruido liso; 1-3 = nubes, remolinos, jirones)
//   ridged           -> crestas finas (1 - |ruido|), para llamas y vetas
//   seed             -> semilla: texturas distintas con los mismos parámetros
export function createNoise({
  periodX = 6,
  periodY = 6,
  octaves = 5,
  gain = 0.5,
  warp = 0,
  ridged = false,
  seed = 1,
} = {}) {
  const main = octavesOf({ periodX, periodY, octaves, gain, seed });
  const warpOctaves = Math.min(octaves, 3);
  const warpX = warp > 0 ? octavesOf({ periodX, periodY, octaves: warpOctaves, gain, seed: seed + 97 }) : null;
  const warpY = warp > 0 ? octavesOf({ periodX, periodY, octaves: warpOctaves, gain, seed: seed + 131 }) : null;
  const texture = new Float32Array(NOISE_SIZE * NOISE_SIZE);
  let low = Infinity;
  let high = -Infinity;
  for (let row = 0; row < NOISE_SIZE; row += 1) {
    for (let col = 0; col < NOISE_SIZE; col += 1) {
      let x = (col / NOISE_SIZE) * periodX;
      let y = (row / NOISE_SIZE) * periodY;
      if (warp > 0) {
        // El desplazamiento también es periódico, así que la textura sigue sin costuras
        const dx = fbm(x, y, warpX);
        const dy = fbm(x, y, warpY);
        x += warp * dx;
        y += warp * dy;
      }
      let value = fbm(x, y, main);
      if (ridged) value = 1 - Math.abs(value);
      texture[row * NOISE_SIZE + col] = value;
      if (value < low) low = value;
      if (value > high) high = value;
    }
  }
  const span = high - low || 1;
  for (let i = 0; i < texture.length; i += 1) texture[i] = (texture[i] - low) / span;
  return texture;
}

// Lienzo blanco cuya opacidad sigue la textura, para usarlo como patrón de recorte
// ("destination-in"): `contrast` > 1 marca más los huecos; `floor` es la opacidad mínima.
export function noiseMaskCanvas(texture, { contrast = 1, floor = 0 } = {}) {
  const canvas = document.createElement('canvas');
  canvas.width = NOISE_SIZE;
  canvas.height = NOISE_SIZE;
  const context = canvas.getContext('2d');
  const image = context.createImageData(NOISE_SIZE, NOISE_SIZE);
  for (let i = 0; i < texture.length; i += 1) {
    const value = Math.min(1, Math.max(0, (texture[i] - 0.5) * contrast + 0.5));
    image.data[i * 4] = 255;
    image.data[i * 4 + 1] = 255;
    image.data[i * 4 + 2] = 255;
    image.data[i * 4 + 3] = (floor + (1 - floor) * value) * 255;
  }
  context.putImageData(image, 0, 0);
  return canvas;
}

// Recorta lo pintado en `context` con una máscara de ruido repetida, desplazada `offset`
// píxeles (para que la textura se mueva un poco entre pasos, como empujada por el viento).
export function applyNoiseMask(context, mask, offset = [0, 0]) {
  const pattern = context.createPattern(mask, 'repeat');
  pattern.setTransform(new DOMMatrix().translateSelf(offset[0], offset[1]));
  context.save();
  context.globalCompositeOperation = 'destination-in';
  context.globalAlpha = 1;
  context.fillStyle = pattern;
  context.fillRect(0, 0, context.canvas.width, context.canvas.height);
  context.restore();
}

// Caché de texturas: cada combinación de parámetros se genera una sola vez por página.
const cache = new Map();
export function sharedNoise(options) {
  const key = JSON.stringify(options);
  if (!cache.has(key)) cache.set(key, createNoise(options));
  return cache.get(key);
}
