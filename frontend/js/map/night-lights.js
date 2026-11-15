// Modo noche: luces de las ciudades (mapa de luces nocturnas de la NASA).
// Las teselas se generan con tools/make-night-tiles.py y están en assets/tiles/nightlights/.
const NIGHT_ID = 'night-lights';
const TILES_BASE = new URL('../../assets/tiles/nightlights/', import.meta.url).href;
const FADE_MS = 900;

// Se añade una vez, justo debajo de las capas de datos y las etiquetas.
export function addNightLights(map, { beforeId, baseId }) {
  map.addSource(NIGHT_ID, {
    type: 'raster',
    tiles: [`${TILES_BASE}{z}/{x}/{y}.webp`],
    tileSize: 512,
    maxzoom: 4,
    attribution: 'Night lights: NASA Earth Observatory',
  });
  map.addLayer(
    {
      id: NIGHT_ID,
      type: 'raster',
      source: NIGHT_ID,
      paint: { 'raster-opacity': 0, 'raster-opacity-transition': { duration: FADE_MS } },
    },
    beforeId
  );
  // El mapa de día se oscurece con la misma transición
  map.setPaintProperty(baseId, 'raster-brightness-max-transition', { duration: FADE_MS });
  map.setPaintProperty(baseId, 'raster-saturation-transition', { duration: FADE_MS });
}

export function syncNight(map, { night, baseId }) {
  if (!map.getLayer(NIGHT_ID)) return;
  map.setPaintProperty(NIGHT_ID, 'raster-opacity', night ? 1 : 0);
  // De noche el continente queda como una silueta tenue bajo las luces
  map.setPaintProperty(baseId, 'raster-brightness-max', night ? 0.2 : 1);
  map.setPaintProperty(baseId, 'raster-saturation', night ? -0.4 : 0);
}
