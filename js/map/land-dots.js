// Puntos sobre la tierra firme, como en la Tierra de la portada.
// Reutiliza la misma imagen en blanco y negro (assets/images/earth-water.png)
// para saber dónde hay tierra y devuelve un GeoJSON para MapLibre.
const TAU = Math.PI * 2;
const GOLDEN = Math.PI * (3 - Math.sqrt(5));

export const DOTS_SOURCE = 'ej-land-dots';
export const DOTS_LAYER = 'ej-land-dots';

async function loadMask(url, width, height) {
  const image = new Image();
  image.src = url;
  await image.decode();

  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  context.drawImage(image, 0, 0, width, height);
  const { data } = context.getImageData(0, 0, width, height);

  const dark = new Uint8Array(width * height);
  let darkCount = 0;
  for (let i = 0; i < dark.length; i++) {
    const v = (0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2]) / 255;
    dark[i] = v < 0.5 ? 1 : 0;
    darkCount += dark[i];
  }
  const landIsDark = darkCount / dark.length < 0.5; // la tierra es la minoría

  return (lat, lon) => {
    const x = Math.min(width - 1, Math.floor(((lon + Math.PI) / TAU) * width));
    const y = Math.min(height - 1, Math.max(0, Math.floor(((Math.PI / 2 - lat) / Math.PI) * height)));
    return landIsDark ? dark[y * width + x] === 1 : dark[y * width + x] === 0;
  };
}

export async function buildLandDots({
  url = new URL('../../assets/images/earth-water.png', import.meta.url).href,
  width = 720,
  height = 360,
  candidates = 16000,
} = {}) {
  const isLand = await loadMask(url, width, height);
  const features = [];

  for (let i = 0; i < candidates; i++) {
    const sinLat = 1 - (2 * (i + 0.5)) / candidates;
    const lat = Math.asin(sinLat);
    const lon = ((GOLDEN * i) % TAU) - Math.PI;
    if (!isLand(lat, lon)) continue;
    features.push({
      type: 'Feature',
      id: features.length, // necesario para feature-state
      properties: {},
      geometry: { type: 'Point', coordinates: [(lon * 180) / Math.PI, (lat * 180) / Math.PI] },
    });
  }
  return { type: 'FeatureCollection', features };
}

// Añade la fuente y la capa. El brillo de cada punto lo decide el cursor
// (feature-state "glow", de 0 a 1), ver hover-glow.js.
export async function addLandDots(map, { beforeId, color }) {
  const data = await buildLandDots();
  map.addSource(DOTS_SOURCE, { type: 'geojson', data });
  map.addLayer(
    {
      id: DOTS_LAYER,
      type: 'circle',
      source: DOTS_SOURCE,
      maxzoom: 4.5, // más cerca, la rejilla ya no tiene sentido
      paint: {
        'circle-color': color,
        'circle-radius': ['+', 1, ['*', 2.6, ['coalesce', ['feature-state', 'glow'], 0]]],
        'circle-opacity': ['+', 0.1, ['*', 0.85, ['coalesce', ['feature-state', 'glow'], 0]]],
        'circle-blur': 0.35,
        'circle-pitch-alignment': 'viewport',
      },
    },
    beforeId
  );
  return data.features.length;
}
