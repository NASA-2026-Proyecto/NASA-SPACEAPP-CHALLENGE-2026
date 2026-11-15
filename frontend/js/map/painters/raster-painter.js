// Pintor de campo: cada píxel del lienzo toma el valor interpolado de la malla y se pinta
// con la rampa de la NASA (si el manifiesto la trae) o con un solo color por especie.
// Con un material (js/map/painters/materials.js) se añade textura, relieve y nube.
import { buildRampTable, hexToRgb, smooth } from '../scene-geometry.js';
import { FIELD_MATERIALS } from './materials.js';
import { NOISE_SIZE, applyNoiseMask, noiseMaskCanvas, sharedNoise } from './noise.js';

const GAMMA = 0.5;
const MAX_ALPHA = 0.92;
const FLOOR = 0.04;
const RAMP_SIZE = 256;
const NOISE_MASK = NOISE_SIZE - 1;
const SHADE_REACH = 2; // distancia en píxeles a la que se mide el relieve
const SHADE_LIMIT = 0.35; // aclarado u oscurecido máximo
// Escalas con rampa (posición 0..1): por debajo de `clear` es transparente y a partir de
// `solid` tiene la opacidad máxima. En la logarítmica (un campo continuo, como el PM2.5)
// el aire limpio deja ver el mapa; en la lineal (datos puntuales) cualquier valor por
// encima de cero se ve. `sparse` es para una escala logarítmica cuyo dato solo cubre
// parte del mapa (la precipitación): se ve desde el extremo bajo de la escala. La
// especie lo pide en el catálogo con `fade: 'sparse'`.
const RAMP_FADE = {
  log: { clear: 0.08, solid: 0.45 },
  linear: { clear: 0.01, solid: 0.12 },
  sparse: { clear: 0, solid: 0.2 },
};

// Texturas de un material, ya generadas (las comparten todas las capas que lo usan).
function prepareMaterial(material) {
  if (!material) return null;
  const contrasted = (texture, contrast) =>
    Float32Array.from(texture, (v) => Math.min(1, Math.max(0, (v - 0.5) * contrast + 0.5)));
  return {
    ...material,
    noise: contrasted(sharedNoise(material.texture), material.contrast ?? 1),
    grainNoise: material.grain ? sharedNoise(material.grain.texture) : null,
    cloudMask: material.cloud
      ? noiseMaskCanvas(sharedNoise(material.cloud.texture), {
          contrast: material.cloud.contrast,
          floor: material.cloud.floor ?? 0,
        })
      : null,
  };
}

// Crea el pintor de una especie.
//   species    -> entrada del catálogo (id, color, fade, material)
//   scene      -> escena cargada (manifiesto y valores)
//   geometry   -> geometría del lienzo (js/map/scene-geometry.js)
//   workspace  -> { field, density, image, layer, cloud, resample }: búferes y lienzos
//                 compartidos por los pintores de campo de una escena
export function createRasterPainter(species, { scene, geometry, workspace }) {
  const { width, height, fadeRows, fadeCols } = geometry;
  const { field, density, image, resample } = workspace;
  const meta = scene.manifest.species[species.id];
  const scale = meta.scale;
  const fade = RAMP_FADE[species.fade ?? scale?.kind];
  const useRamp = Boolean(scale?.ramp && RAMP_FADE[scale.kind]);
  const table = useRamp ? buildRampTable(scale.ramp, RAMP_SIZE) : null;
  const material = prepareMaterial(FIELD_MATERIALS[species.material]);

  // Un solo color por especie: más claro y más opaco cuanto mayor es el valor. Con un
  // material el color varía menos (`tint`), para que la especie se reconozca por su tono.
  function paintTint() {
    const max = meta.display_scale_max;
    const base = hexToRgb(species.color);
    const { dark: darken, light: lighten } = material?.tint ?? { dark: 0.6, light: 0.45 };
    const dark = base.map((v) => v * darken);
    const light = base.map((v) => v + (255 - v) * lighten);
    const data = image.data;
    for (let r = 0; r < height; r += 1) {
      for (let c = 0; c < width; c += 1) {
        const i = r * width + c;
        const offset = i * 4;
        const normalized = field[i] / max;
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

  // Escala (logarítmica o lineal) con la rampa de la barra de la NASA. Los huecos (NaN:
  // donde la imagen de origen no tenía dato) quedan transparentes.
  function paintRamp() {
    const isLog = scale.kind === 'log';
    const start = isLog ? Math.log(scale.min) : scale.min;
    const span = (isLog ? Math.log(scale.max) : scale.max) - start;
    const { clear, solid } = fade;
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

  // Textura y relieve del material sobre lo ya pintado en `image`.
  function applyTexture([offsetX, offsetY]) {
    const { noise, strength, grainNoise, grain, shade = 0, whiten = 0 } = material;
    const data = image.data;
    // 1. Densidad: la opacidad modulada por el ruido (y el grano). La modulación va de
    //    1 - strength a 1 + strength, así la capa conserva su opacidad media.
    for (let r = 0; r < height; r += 1) {
      const noiseRow = ((r + offsetY) & NOISE_MASK) * NOISE_SIZE;
      for (let c = 0; c < width; c += 1) {
        const i = r * width + c;
        const alpha = data[i * 4 + 3];
        if (alpha === 0) {
          density[i] = 0;
          continue;
        }
        const n = noiseRow + ((c + offsetX) & NOISE_MASK);
        let modulation = 1 + strength * (2 * noise[n] - 1);
        if (grainNoise) modulation *= 1 + grain.strength * (2 * grainNoise[n] - 1);
        density[i] = Math.min(1, (alpha / 255) * modulation);
      }
    }
    // 2. Color con relieve (luz del noroeste) y opacidad final
    const reach = SHADE_REACH * width + SHADE_REACH;
    for (let i = 0; i < density.length; i += 1) {
      const offset = i * 4;
      if (density[i] === 0) {
        data[offset + 3] = 0;
        continue;
      }
      const lit = (density[i + reach] ?? 0) - (density[i - reach] ?? 0);
      const light = 1 + Math.max(-SHADE_LIMIT, Math.min(SHADE_LIMIT, lit * shade));
      for (let channel = 0; channel < 3; channel += 1) {
        const value = data[offset + channel];
        data[offset + channel] = (value + (255 - value) * whiten) * light;
      }
      data[offset + 3] = density[i] * 255;
    }
  }

  // Nube bajo el dato: la silueta del dato, difuminada, blanca y recortada con ruido.
  function paintCloud(target, offset) {
    const { blur, colour, alpha } = material.cloud;
    const cloud = workspace.cloud.getContext('2d');
    cloud.clearRect(0, 0, width, height);
    cloud.filter = `blur(${blur}px)`;
    cloud.drawImage(workspace.layer, 0, 0);
    cloud.drawImage(workspace.layer, 0, 0); // dos veces: la nube cubre algo más que el dato
    cloud.filter = 'none';
    cloud.globalCompositeOperation = 'source-in';
    cloud.fillStyle = `rgb(${colour.join(', ')})`;
    cloud.fillRect(0, 0, width, height);
    cloud.globalCompositeOperation = 'source-over';
    applyNoiseMask(cloud, material.cloudMask, offset);
    target.globalAlpha = alpha;
    target.drawImage(workspace.cloud, 0, 0);
    target.globalAlpha = 1;
  }

  // Pinta un paso exacto en el contexto (vacío) de su lienzo.
  return function paint(context, step) {
    resample(species.id, step, field);
    if (useRamp) paintRamp();
    else paintTint();
    if (!material) {
      context.putImageData(image, 0, 0);
      return;
    }
    const offset = (material.drift ?? [0, 0]).map((pixels) => Math.round(step * pixels));
    applyTexture(offset);
    if (!material.cloud) {
      context.putImageData(image, 0, 0);
      return;
    }
    workspace.layer.getContext('2d').putImageData(image, 0, 0);
    paintCloud(context, offset);
    // Un desenfoque mínimo quita el escalón entre celdas y entre clases de color
    if (material.soften) context.filter = `blur(${material.soften}px)`;
    context.drawImage(workspace.layer, 0, 0);
    context.filter = 'none';
  };
}
