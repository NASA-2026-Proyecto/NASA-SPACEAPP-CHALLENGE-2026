import { createStore } from './store.js';
import { LAYERS } from '../config.js';

const initialLayers = Object.fromEntries(LAYERS.map((layer) => [layer.id, false]));
const initialOpacity = Object.fromEntries(LAYERS.map((layer) => [layer.id, layer.defaultOpacity ?? 0.85]));

export const store = createStore({
  layers: initialLayers,
  opacity: initialOpacity,
  nightMode: false,
  selectedMarker: null,
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
