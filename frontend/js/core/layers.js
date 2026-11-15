export const isSceneLayer = (layer) => layer.kind === 'scene';
export const isLayerAvailable = (layer) => Boolean(layer.scenes?.length);

// Escena a la que pertenece la especie elegida en una capa de escenas
export const sceneIdOf = (layer, speciesId) =>
  layer.species?.find((species) => species.id === speciesId)?.sceneId ?? null;
