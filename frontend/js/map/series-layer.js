import { createResampler } from '../data/scene-data.js';

const GAMMA = 0.5;
const MAX_ALPHA = 0.92;
const FLOOR = 0.04;
const FEATHER_CELLS = 12;
const MERCATOR_MAX_LAT = 85.0511287798;

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
  const pixelsPerCell = periodic ? 3 : 4;
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

export function createSeriesLayer(map, { layerId, scene, species, beforeId }) {
  const geometry = buildGeometry(scene.grid);
  const { width, height } = geometry;

  const canvas = document.createElement('canvas');
  canvas.id = `${layerId}-canvas`;
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
  let current = { speciesId: null, step: null };

  map.addSource(layerId, {
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
      id: layerId,
      type: 'raster',
      source: layerId,
      layout: { visibility: 'none' },
      paint: { 'raster-opacity': 0.85, 'raster-fade-duration': 0 },
    },
    beforeId
  );

  function paint(speciesId, step) {
    const scale = scene.manifest.species[speciesId].display_scale_max;
    const { base, dark, light } = palette.get(speciesId);
    resample(speciesId, step, field);

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
    context.putImageData(image, 0, 0);
  }

  function sync(state) {
    const visible = Boolean(state.layers[layerId]);
    map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
    map.setPaintProperty(layerId, 'raster-opacity', state.opacity[layerId]);
    if (!visible) return;

    const speciesId = state.species[layerId];
    const step = state.sceneStep;
    if (speciesId === current.speciesId && step === current.step) return;
    current = { speciesId, step };
    paint(speciesId, step);
  }

  function destroy() {
    if (map.getLayer(layerId)) map.removeLayer(layerId);
    if (map.getSource(layerId)) map.removeSource(layerId);
    canvas.remove();
  }

  return { sync, destroy };
}