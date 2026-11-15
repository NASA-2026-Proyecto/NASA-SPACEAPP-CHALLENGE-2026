import { createStore } from './store.js';
import { LAYERS } from '../config.js';
import { reducedMotionQuery } from '../core/motion.js';

const initialLayers = Object.fromEntries(LAYERS.map((layer) => [layer.id, false]));
const initialOpacity = Object.fromEntries(LAYERS.map((layer) => [layer.id, layer.defaultOpacity ?? 0.85]));
const initialSpecies = Object.fromEntries(
  LAYERS.filter((layer) => layer.species).map((layer) => [
    layer.id,
    layer.species[0].id, // la primera especie es la de por defecto
  ])
);

export const store = createStore({
  layers: initialLayers,
  opacity: initialOpacity,
  nightMode: false,
  species: initialSpecies,
  // Animación de las escenas: recorre sus pasos en bucle. sceneProgress va de 0 (paso
  // más antiguo) a 1 (el más reciente) y aquí solo se actualiza a saltos, para la interfaz.
  scenePlaying: !reducedMotionQuery.matches,
  sceneProgress: 1,
  sceneInfo: {}, // por id de escena: { stamps } (los instantes de sus pasos) cuando está cargada
  reading: null, // lectura del punto seleccionado (js/data/point-reading.js)
});

export function setLayerVisible(id, visible) {
  store.setState((state) => ({
    layers: { ...state.layers, [id]: visible },
  }));
}

export function setNightMode(enabled) {
  store.setState({ nightMode: enabled });
}

export function setLayerOpacity(id, value) {
  store.setState((state) => ({
    opacity: { ...state.opacity, [id]: value },
  }));
}

export function setLayerSpecies(id, speciesId) {
  store.setState((state) => ({
    species: { ...state.species, [id]: speciesId },
  }));
}

export function setSceneProgress(progress) {
  store.setState({ sceneProgress: progress });
}

export function setScenePlaying(playing) {
  store.setState({ scenePlaying: playing });
}

export function setSceneInfo(sceneId, info) {
  store.setState((state) => ({
    sceneInfo: { ...state.sceneInfo, [sceneId]: info },
  }));
}

export function setReading(reading) {
  store.setState({ reading });
}
