const BYTES_PER_VALUE = 4;

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`No se pudo cargar ${url} (${response.status})`);
  return response.json();
}

async function fetchBuffer(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`No se pudo cargar ${url} (${response.status})`);
  return response.arrayBuffer();
}

function validateManifest(manifest) {
  if (manifest.schema_version !== 2 || manifest.kind !== 'grid-series') {
    throw new Error('Manifiesto de escena no compatible.');
  }
  if (manifest.time.stamps_utc.length !== manifest.time.steps) {
    throw new Error('El manifiesto tiene un número de instantes incoherente.');
  }
}

async function sha256Hex(buffer) {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) return null;
  const digest = await subtle.digest('SHA-256', buffer);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function loadSpecies(baseUrl, id, species, expectedValues) {
  const buffer = await fetchBuffer(`${baseUrl}/${species.file}`);
  if (buffer.byteLength !== expectedValues * BYTES_PER_VALUE) {
    throw new Error(`${id}: tamaño de archivo inesperado (${buffer.byteLength} bytes).`);
  }
  const hash = await sha256Hex(buffer);
  if (hash === null) {
    console.warn(`[escena] ${id}: no se pudo verificar la suma de comprobación (contexto no seguro).`);
  } else if (hash !== species.sha256) {
    throw new Error(`${id}: la suma de comprobación no coincide con el manifiesto.`);
  }
  return new Float32Array(buffer);
}

export async function loadScene(baseUrl) {
  const manifest = await fetchJson(`${baseUrl}/manifest.json`);
  validateManifest(manifest);
  const { grid, time } = manifest;
  const expected = time.steps * grid.n_lat * grid.n_lon;

  const entries = await Promise.all(
    Object.entries(manifest.species).map(async ([id, species]) => [
      id,
      await loadSpecies(baseUrl, id, species, expected),
    ])
  );
  return { manifest, grid, time, values: Object.fromEntries(entries) };
}

function bilinear(values, base, r0, r1, c0, c1, fr, fc) {
  const top = values[base + r0 + c0] * (1 - fc) + values[base + r0 + c1] * fc;
  const bottom = values[base + r1 + c0] * (1 - fc) + values[base + r1 + c1] * fc;
  return top * (1 - fr) + bottom * fr;
}

function sampleStep(values, grid, step, lat, lon) {
  const row = (lat - grid.lat_min) / grid.lat_step;
  let col = (lon - grid.lon_min) / grid.lon_step;
  if (row < 0 || row > grid.n_lat - 1) return null;
  if (grid.lon_periodic) {
    col = ((col % grid.n_lon) + grid.n_lon) % grid.n_lon;
  } else if (col < 0 || col > grid.n_lon - 1) {
    return null;
  }

  const r0 = Math.floor(row);
  const c0 = Math.floor(col);
  const r1 = Math.min(r0 + 1, grid.n_lat - 1);
  const c1 = grid.lon_periodic ? (c0 + 1) % grid.n_lon : Math.min(c0 + 1, grid.n_lon - 1);
  return bilinear(
    values, step * grid.n_lat * grid.n_lon,
    r0 * grid.n_lon, r1 * grid.n_lon, c0, c1, row - r0, col - c0
  );
}

// Valor interpolado en el espacio y en el tiempo (para el sonido).
// `step` puede ser fraccionario: 0 .. steps - 1.
export function sampleAt(scene, speciesId, step, lat, lon) {
  const values = scene.values[speciesId];
  if (!values) throw new Error(`Especie desconocida: ${speciesId}`);
  const clamped = Math.min(Math.max(step, 0), scene.time.steps - 1);
  const s0 = Math.floor(clamped);
  const s1 = Math.min(s0 + 1, scene.time.steps - 1);
  const f = clamped - s0;

  const a = sampleStep(values, scene.grid, s0, lat, lon);
  if (a === null) return null;
  if (f === 0 || s1 === s0) return a;
  return a * (1 - f) + sampleStep(values, scene.grid, s1, lat, lon) * f;
}

// Valor de la celda más cercana en un paso exacto (para la ficha: dato sin interpolar).
export function cellValueAt(scene, speciesId, stepIndex, lat, lon) {
  const { grid } = scene;
  const row = Math.round((lat - grid.lat_min) / grid.lat_step);
  let col = Math.round((lon - grid.lon_min) / grid.lon_step);
  if (grid.lon_periodic) col = ((col % grid.n_lon) + grid.n_lon) % grid.n_lon;
  if (row < 0 || row >= grid.n_lat || col < 0 || col >= grid.n_lon) return null;
  const index = (stepIndex * grid.n_lat + row) * grid.n_lon + col;
  return scene.values[speciesId][index];
}

function axisIndices(axis, min, stepSize, count, periodic = false) {
  const i0 = new Int32Array(axis.length);
  const i1 = new Int32Array(axis.length);
  const frac = new Float32Array(axis.length);
  const valid = new Uint8Array(axis.length);
  for (let k = 0; k < axis.length; k += 1) {
    let position = (axis[k] - min) / stepSize;
    if (periodic) {
      position = ((position % count) + count) % count;
    } else if (position < 0 || position > count - 1) {
      continue;
    }
    const lower = Math.floor(position);
    i0[k] = lower;
    i1[k] = periodic ? (lower + 1) % count : Math.min(lower + 1, count - 1);
    frac[k] = position - lower;
    valid[k] = 1;
  }
  return { i0, i1, frac, valid };
}

// Remuestrea una especie a una malla arbitraria (para dibujar en el mapa).
export function createResampler(scene, lats, lons) {
  const { grid, time } = scene;
  const rows = axisIndices(lats, grid.lat_min, grid.lat_step, grid.n_lat);
  const cols = axisIndices(lons, grid.lon_min, grid.lon_step, grid.n_lon, Boolean(grid.lon_periodic));  const plane = grid.n_lat * grid.n_lon;

  return function resample(speciesId, step, out) {
    const values = scene.values[speciesId];
    if (!values) throw new Error(`Especie desconocida: ${speciesId}`);
    const clamped = Math.min(Math.max(step, 0), time.steps - 1);
    const s0 = Math.floor(clamped);
    const s1 = Math.min(s0 + 1, time.steps - 1);
    const ft = clamped - s0;
    const base0 = s0 * plane;
    const base1 = s1 * plane;

    let k = 0;
    for (let r = 0; r < lats.length; r += 1) {
      const rowValid = rows.valid[r];
      const r0 = rows.i0[r] * grid.n_lon;
      const r1 = rows.i1[r] * grid.n_lon;
      const fr = rows.frac[r];
      for (let c = 0; c < lons.length; c += 1, k += 1) {
        if (!rowValid || !cols.valid[c]) {
          out[k] = Number.NaN;
          continue;
        }
        const c0 = cols.i0[c];
        const c1 = cols.i1[c];
        const fc = cols.frac[c];
        const a = bilinear(values, base0, r0, r1, c0, c1, fr, fc);
        out[k] = ft === 0 ? a : a * (1 - ft) + bilinear(values, base1, r0, r1, c0, c1, fr, fc) * ft;
      }
    }
  };
}