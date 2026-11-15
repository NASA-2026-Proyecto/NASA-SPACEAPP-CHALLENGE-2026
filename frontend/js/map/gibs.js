const GIBS_ROOT = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best';

export function buildGibsSource({ layerId, matrixSet, maxZoom, format, time = 'default' }) {
  return {
    type: 'raster',
    tiles: [`${GIBS_ROOT}/${layerId}/default/${time}/${matrixSet}/{z}/{y}/{x}.${format}`],
    tileSize: 256,
    maxzoom: maxZoom,
    attribution: 'Imagery: NASA GIBS',
  };
}