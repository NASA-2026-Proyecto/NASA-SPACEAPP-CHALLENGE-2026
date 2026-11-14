export const isGridLayer = (layer) => layer.kind === 'grid';
export const isLayerAvailable = (layer) => Boolean(layer.source || layer.data);