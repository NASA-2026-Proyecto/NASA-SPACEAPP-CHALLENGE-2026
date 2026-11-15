import * as maplibregl from 'https://unpkg.com/maplibre-gl@6.16.0/dist/maplibre-gl.mjs';
import { LAYERS } from '../config.js';
import { readCssToken } from '../core/css-tokens.js';
import { store, setSceneInfo } from '../state/app-store.js';
import { startAutoSpin } from './auto-spin.js';
import { buildGibsSource } from './gibs.js';
import { reducedMotionQuery } from '../core/motion.js';
import { addNightLights, syncNight } from './night-lights.js';
import { addLandDots, DOTS_SOURCE, DOTS_LAYER } from './land-dots.js';
import { createHoverGlow } from './hover-glow.js';
import { findScene } from '../catalog/scenes.js';
import { isSceneLayer, sceneIdOf } from '../core/layers.js';
import { loadScene } from '../data/scene-data.js';
import { createSeriesLayer } from './series-layer.js';


const STYLE = 'https://tiles.openfreemap.org/styles/dark';
const INITIAL_VIEW = { center: [-30, 25], zoom: 1.6 };
const PLACES = { spain: { center: [-3.7, 40.4], zoom: 5.2 } };
const LOAD_TIMEOUT_MS = 20000;
const ON_GLOBE_TOLERANCE_PX = 2;
const SCENE_RETRY_MS = 5000;

const BASEMAP_ID = 'nasa-blue-marble';
const BASEMAP_TILES =
  'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/wmts.cgi' +
  '?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0' +
  '&LAYER=BlueMarble_ShadedRelief_Bathymetry&STYLE=default' +
  '&TILEMATRIXSET=GoogleMapsCompatible_Level8' +
  '&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/jpeg';

const KEEP_SOURCE_LAYERS = new Set(['place', 'water_name', 'boundary']);

function useNasaBasemap(map) {
  const layers = map.getStyle().layers;
  const bottomId = layers[0]?.id;

  for (const layer of layers) {
    if (!KEEP_SOURCE_LAYERS.has(layer['source-layer'])) {
      map.setLayoutProperty(layer.id, 'visibility', 'none');
    }
  }

  map.addSource(BASEMAP_ID, {
    type: 'raster',
    tiles: [BASEMAP_TILES],
    tileSize: 256,
    maxzoom: 8,
    attribution: 'Imagery: NASA GIBS',
  });
  map.addLayer({ id: BASEMAP_ID, type: 'raster', source: BASEMAP_ID }, bottomId);
}

function applyAtmosphere(map, night = false) {
  // Fondo transparente: detrás se ve el campo de estrellas de la página
  map.getContainer().style.background = 'transparent';
  map.setSky({
    'sky-color': night ? '#14286b' : readCssToken('--ej-globe-atmosphere', '#409dff'),
    'horizon-color': night ? '#3a5bb5' : '#bad2eb',
    'fog-color': night ? '#1a2a63' : '#bad2eb',
    'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 5, 1, 7, 0],
  });
}

const dotColor = (night) =>
  night
    ? readCssToken('--ej-night-glow', '#ffd9a0')
    : readCssToken('--ej-globe-highlight', '#cfeaff');

function findFirstLabelId(map) {
  return map
    .getStyle()
    .layers.find(
      (layer) =>
        layer.type === 'symbol' && map.getLayoutProperty(layer.id, 'visibility') !== 'none'
    )?.id;
}

function addNasaLayers(map, firstLabelId) {
  for (const layer of LAYERS) {
    if (!layer.source) continue;

    map.addSource(layer.id, buildGibsSource(layer.source));
    map.addLayer(
      {
        id: layer.id,
        type: 'raster',
        source: layer.id,
        layout: { visibility: 'none' },
        paint: { 'raster-opacity': layer.defaultOpacity ?? 0.85, ...layer.paint },
      },
      firstLabelId
    );
  }
}

function syncLayers(map, state) {
  for (const layer of LAYERS) {
    if (!layer.source || !map.getLayer(layer.id)) continue;
    map.setLayoutProperty(layer.id, 'visibility', state.layers[layer.id] ? 'visible' : 'none');
    map.setPaintProperty(layer.id, 'raster-opacity', state.opacity[layer.id]);
  }
}

export async function createGlobeMap({ container }) {
  const map = new maplibregl.Map({
    container,
    style: STYLE,
    ...INITIAL_VIEW,
  });
  map.addControl(new maplibregl.NavigationControl(), 'bottom-right');

  map.once('style.load', () => {
    map.setProjection({ type: 'globe' });
    useNasaBasemap(map);
    applyAtmosphere(map, store.getState().nightMode);
  });

  await new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error('El mapa tardó demasiado en cargar. Revisa tu conexión.')),
      LOAD_TIMEOUT_MS
    );
    map.once('load', () => {
      clearTimeout(timer);
      resolve();
    });
    map.on('error', (event) => console.warn('Aviso del mapa:', event.error?.message ?? event));
  });

  // Orden (de abajo arriba): mapa base, luces de noche, capas NASA, puntos, etiquetas
  const beforeId = findFirstLabelId(map);
  addNightLights(map, { beforeId, baseId: BASEMAP_ID });
  addNasaLayers(map, beforeId);

  let lastNight = null;
  function syncAppearance(state) {
    syncNight(map, { night: state.nightMode, baseId: BASEMAP_ID });
    if (state.nightMode !== lastNight) {
      lastNight = state.nightMode;
      applyAtmosphere(map, state.nightMode);
    }
    if (map.getLayer(DOTS_LAYER)) {
      map.setPaintProperty(DOTS_LAYER, 'circle-color', dotColor(state.nightMode));
    }
  }

  // Cada escena se descarga la primera vez que hace falta: con su capa activa y una de
  // sus especies elegida. Si aún no está lista (la API la prepara con datos de la NASA)
  // se reintenta mientras siga haciendo falta.
  const seriesLayers = [];
  const requestedScenes = new Set();
  const sceneRetryTimers = new Set();
  function loadScenesOnDemand(state) {
    for (const layer of LAYERS.filter(isSceneLayer)) {
      const sceneId = sceneIdOf(layer, state.species[layer.id]);
      if (!state.layers[layer.id] || !sceneId || requestedScenes.has(sceneId)) continue;
      requestedScenes.add(sceneId);
      const entry = findScene(sceneId);
      loadScene(entry.dataUrl)
        .then((scene) => {
          seriesLayers.push(
            createSeriesLayer(map, {
              id: `${layer.id}-${sceneId}`,
              layerId: layer.id,
              scene,
              species: entry.species,
              live: entry.live,
              beforeId,
            })
          );
          setSceneInfo(sceneId, { stamp: scene.time.stamps_utc.at(-1) });
        })
        .catch((error) => {
          console.warn(`[mapa] Sin datos para la escena "${sceneId}"; se reintentará:`, error);
          const timer = setTimeout(() => {
            sceneRetryTimers.delete(timer);
            requestedScenes.delete(sceneId);
            sync(store.getState());
          }, SCENE_RETRY_MS);
          sceneRetryTimers.add(timer);
        });
    }
  }

  const sync = (state) => {
    syncLayers(map, state);
    syncAppearance(state);
    loadScenesOnDemand(state);
    for (const series of seriesLayers) series.sync(state);
  };
  sync(store.getState());

  // Puntos de tierra + brillo al pasar el cursor. Si fallan, el mapa sigue funcionando.
  let hoverGlow = null;
  addLandDots(map, { beforeId, color: dotColor(store.getState().nightMode) })
    .then(() => {
      hoverGlow = createHoverGlow(map, {
        source: DOTS_SOURCE,
        layer: DOTS_LAYER,
        reducedMotion: reducedMotionQuery.matches,
      });
    })
    .catch((error) => console.warn('[mapa] Sin puntos de tierra:', error));

  const unsubscribe = store.subscribe(sync);
  const stopSpin = startAutoSpin(map);

  // Un único popup reutilizable. closeOnClick: false porque es el propio clic en el
  // mapa el que lo mueve; focusAfterOpen: false para no robar el foco en cada clic.
  let popup = null;

  return {
    map,
    flyTo(name) {
      const place = PLACES[name];
      if (!place) return;
      stopSpin();
      map.flyTo({ ...place, duration: 4000 });
    },
    // En proyección globo, un clic en el espacio (fuera de la esfera) también trae
    // coordenadas: las de un punto del borde. Si al proyectarlas de vuelta no caen
    // donde se hizo clic, el clic no fue sobre la Tierra.
    isOnGlobe({ point, lngLat }) {
      const back = map.project(lngLat);
      return Math.hypot(back.x - point.x, back.y - point.y) <= ON_GLOBE_TOLERANCE_PX;
    },
    showPopup(lngLat, content) {
      popup ??= new maplibregl.Popup({
        className: 'ej-popup',
        closeOnClick: false,
        focusAfterOpen: false,
        maxWidth: '280px',
        offset: 12,
      });
      popup.setLngLat(lngLat).setDOMContent(content);
      if (!popup.isOpen()) popup.addTo(map);
    },
    destroy() {
      unsubscribe();
      hoverGlow?.destroy();
      stopSpin();
      popup?.remove();
      sceneRetryTimers.forEach(clearTimeout);
      seriesLayers.forEach((series) => series.destroy());
      map.remove();
    },
  };
}