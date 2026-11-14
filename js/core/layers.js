export const isSceneLayer = (layer) => layer.kind === 'scene';
export const isLayerAvailable = (layer) => Boolean(layer.source || layer.sceneId);