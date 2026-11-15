import { createStore } from './store.js';
import { LAYERS } from '../config.js';

const initialLayers = Object.fromEntries(LAYERS.map((layer) => [layer.id, false]));
const initialOpacity = Object.fromEntries(LAYERS.map((layer) => [layer.id, layer.defaultOpacity ?? 0.85]));
const initialSpecies = Object.fromEntries(
  LAYERS.filter((layer) => layer.species).map((layer) => [
    layer.id,
    layer.defaultSpecies ?? layer.species[0].id,
  ])
);

export const store = createStore({
  layers: initialLayers,
  opacity: initialOpacity,
  nightMode: false,
  selectedMarker: null,
  species: initialSpecies,
  sceneStep:0,
  scenePlaying: false,
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

export function setSceneStep(step) {
  store.setState({ sceneStep: step });
}

export function setScenePlaying(playing) {
  store.setState({ scenePlaying: playing });
}
