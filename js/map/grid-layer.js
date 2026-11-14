function cellPolygon(lat, lon, halfLat, halfLon) {
    return [[
      [lon - halfLon, lat - halfLat],
      [lon + halfLon, lat - halfLat],
      [lon + halfLon, lat + halfLat],
      [lon - halfLon, lat + halfLat],
      [lon - halfLon, lat - halfLat],
    ]];
  }
  
  function assertValid(payload) {
    const { grid, species } = payload;
    if (payload.schema_version !== 1) {
      throw new Error(`Versión de esquema no soportada: ${payload.schema_version}`);
    }
    const expected = grid.n_lat * grid.n_lon;
    for (const [id, item] of Object.entries(species)) {
      if (item.values.length !== expected) {
        throw new Error(`${id}: ${item.values.length} valores, se esperaban ${expected}`);
      }
    }
  }
  
  export function buildGridGeoJson(payload) {
    assertValid(payload);
    const { grid, species } = payload;
    const halfLat = grid.lat_step / 2;
    const halfLon = grid.lon_step / 2;
    const ids = Object.keys(species);
    const features = [];
  
    for (let row = 0; row < grid.n_lat; row += 1) {
      const lat = grid.lat_min + row * grid.lat_step;
      for (let col = 0; col < grid.n_lon; col += 1) {
        const lon = grid.lon_min + col * grid.lon_step;
        const index = row * grid.n_lon + col;
        const properties = {};
        for (const id of ids) properties[id] = species[id].values[index];
        features.push({
          type: 'Feature',
          properties,
          geometry: { type: 'Polygon', coordinates: cellPolygon(lat, lon, halfLat, halfLon) },
        });
      }
    }
    return { type: 'FeatureCollection', features };
  }
  
  export async function addGridLayer(map, layer, beforeId) {
    const response = await fetch(layer.data.url);
    if (!response.ok) {
      throw new Error(`No se pudo cargar ${layer.data.url} (${response.status})`);
    }
    const payload = await response.json();
  
    map.addSource(layer.id, {
      type: 'geojson',
      data: buildGridGeoJson(payload),
      attribution: 'Data: NASA GMAO GEOS-FP',
    });
    map.addLayer(
      {
        id: layer.id,
        type: 'fill',
        source: layer.id,
        layout: { visibility: 'none' },
        paint: { 'fill-color': layer.species[0].color, 'fill-opacity': 0, 'fill-antialias': false },
      },
      beforeId
    );
  }
  
  export function syncGridLayer(map, layer, state) {
    if (!map.getLayer(layer.id)) return;
    const species =
      layer.species.find((item) => item.id === state.species[layer.id]) ?? layer.species[0];
  
    map.setLayoutProperty(layer.id, 'visibility', state.layers[layer.id] ? 'visible' : 'none');
    map.setPaintProperty(layer.id, 'fill-color', species.color);
    map.setPaintProperty(layer.id, 'fill-opacity', [
      '*',
      state.opacity[layer.id],
      ['interpolate', ['linear'], ['get', species.id], 0, 0, species.scaleMax, 1],
    ]);
  }