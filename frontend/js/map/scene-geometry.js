// Geometría del lienzo de una escena: la malla de datos reproyectada a Web Mercator, que
// es lo que MapLibre espera de una fuente "canvas" (luego la curva sobre el globo).

const MERCATOR_MAX_LAT = 85.0511287798;
const FEATHER_CELLS = 12;

export const mercatorY = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
const latFromMercatorY = (y) => (Math.atan(Math.sinh(y)) * 180) / Math.PI;
export const smooth = (t) => t * t * (3 - 2 * t);

// Construye la geometría del lienzo para una malla.
//   grid            -> bloque `grid` del manifiesto
//   maxCanvasWidth  -> ancho máximo en píxeles (el lienzo se sube a la GPU en cada fotograma)
//
// Devuelve el recorte (west, east, south, north), el tamaño del lienzo, los píxeles por
// celda, la latitud y longitud del centro de cada fila y columna, y el desvanecimiento
// de los bordes (solo si el recorte es regional; una malla global no tiene bordes).
export function buildGeometry(grid, maxCanvasWidth) {
  const periodic = Boolean(grid.lon_periodic);
  const west = grid.lon_min;
  const east = periodic ? grid.lon_min + 360 : grid.lon_min + (grid.n_lon - 1) * grid.lon_step;
  const south = Math.max(grid.lat_min, -MERCATOR_MAX_LAT);
  const north = Math.min(grid.lat_min + (grid.n_lat - 1) * grid.lat_step, MERCATOR_MAX_LAT);
  const wanted = periodic ? 6 : 4; // el ancho máximo del lienzo suele mandar antes
  const pixelsPerCell = Math.max(1, Math.min(wanted, Math.round(maxCanvasWidth / grid.n_lon)));
  const width = grid.n_lon * pixelsPerCell;
  const yNorth = mercatorY(north);
  const spanY = yNorth - mercatorY(south);
  const spanX = ((east - west) * Math.PI) / 180;
  const height = Math.round((width * spanY) / spanX);

  const lats = new Float64Array(height);
  const lons = new Float64Array(width);
  for (let r = 0; r < height; r += 1) {
    lats[r] = latFromMercatorY(yNorth - ((r + 0.5) / height) * spanY);
  }
  for (let c = 0; c < width; c += 1) {
    lons[c] = west + ((c + 0.5) / width) * (east - west);
  }

  const featherPx = FEATHER_CELLS * pixelsPerCell;
  const edgeFade = (index, size) =>
    smooth(Math.min(1, Math.min(index + 0.5, size - index - 0.5) / featherPx));
  const fadeRows = Float32Array.from({ length: height }, (_, r) => (periodic ? 1 : edgeFade(r, height)));
  const fadeCols = Float32Array.from({ length: width }, (_, c) => (periodic ? 1 : edgeFade(c, width)));

  return {
    west,
    east,
    south,
    north,
    width,
    height,
    pixelsPerCell,
    periodic,
    lats,
    lons,
    fadeRows,
    fadeCols,
    // Posición continua en el lienzo (en píxeles) de una longitud y una latitud
    xOf: (lon) => ((lon - west) / (east - west)) * width,
    yOf: (lat) => ((yNorth - mercatorY(lat)) / spanY) * height,
  };
}

export const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));

// Tabla de `size` colores a partir de las paradas de una rampa (los colores de la propia
// barra de la NASA, que publica el manifiesto), interpolando entre paradas.
export function buildRampTable(stops, size) {
  const colors = stops.map(hexToRgb);
  const table = new Uint8ClampedArray(size * 3);
  for (let i = 0; i < size; i += 1) {
    const position = (i / (size - 1)) * (colors.length - 1);
    const low = Math.min(Math.floor(position), colors.length - 2);
    const t = position - low;
    for (let channel = 0; channel < 3; channel += 1) {
      table[i * 3 + channel] = colors[low][channel] * (1 - t) + colors[low + 1][channel] * t;
    }
  }
  return table;
}
