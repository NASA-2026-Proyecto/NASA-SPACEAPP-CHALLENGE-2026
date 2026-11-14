import * as THREE from 'three';

export async function loadLandMask({ url, width, height }) {
  const image = new Image();
  image.src = url;
  await image.decode();

  const offscreen = document.createElement('canvas');
  offscreen.width = width;
  offscreen.height = height;
  const context = offscreen.getContext('2d', { willReadFrequently: true });
  context.drawImage(image, 0, 0, width, height);
  const { data } = context.getImageData(0, 0, width, height);

  const luminance = new Float32Array(width * height);
  let darkPixels = 0;
  for (let i = 0; i < luminance.length; i++) {
    const value = (0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2]) / 255;
    luminance[i] = value;
    if (value < 0.5) darkPixels++;
  }

  // La tierra cubre ~30 % de la superficie: si lo oscuro es minoría, la tierra es oscura
  const landIsDark = darkPixels / luminance.length < 0.5;

  // NUEVO: la misma imagen, ahora también como textura para dibujar los continentes
  const texture = new THREE.CanvasTexture(offscreen);
  texture.generateMipmaps = false;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;

  return {
    texture,
    landIsDark,
    isLand(lat, lon) {
      const x = Math.min(width - 1, Math.floor(((lon + Math.PI) / (2 * Math.PI)) * width));
      const y = Math.min(height - 1, Math.max(0, Math.floor(((Math.PI / 2 - lat) / Math.PI) * height)));
      const isDark = luminance[y * width + x] < 0.5;
      return landIsDark ? isDark : !isDark;
    },
  };
}

// Reparte puntos de forma uniforme sobre la esfera y conserva solo los de tierra
export function buildLandPositions(mask, candidateCount) {
  const golden = Math.PI * (3 - Math.sqrt(5));
  const values = [];

  for (let i = 0; i < candidateCount; i++) {
    const sinLat = 1 - (2 * (i + 0.5)) / candidateCount;
    const lat = Math.asin(sinLat);
    const lon = ((golden * i) % (2 * Math.PI)) - Math.PI;
    if (!mask.isLand(lat, lon)) continue;

    const cosLat = Math.cos(lat);
    values.push(cosLat * Math.sin(lon), sinLat, cosLat * Math.cos(lon));
  }

  return {
    positions: new Float32Array(values),
    landRatio: values.length / 3 / candidateCount,
  };
}
