import { LAYERS } from '../config.js';

export const isSceneLayer = (layer) => layer.kind === 'scene';
export const isLayerAvailable = (layer) => Boolean(layer.scenes?.length);

// La capa de datos activa (solo puede haber una a la vez), o null si no hay ninguna
export const activeLayer = (state) => LAYERS.find((layer) => state.layers[layer.id]) ?? null;

// Escena a la que pertenece la especie elegida en una capa de escenas
export const sceneIdOf = (layer, speciesId) =>
  layer.species?.find((species) => species.id === speciesId)?.sceneId ?? null;
