import { findScene } from '../catalog/scenes.js';
import { loadScene } from './scene-data.js';

// Una sola descarga por escena, la pida quien la pida (el mapa para dibujarla, la ficha
// del punto y el sonido para leer valores). Si falla (p. ej. la API aún la está
// preparando) no se guarda el fallo: la siguiente petición lo vuelve a intentar.
const pending = new Map();

export function getScene(sceneId) {
  if (!pending.has(sceneId)) {
    const request = loadScene(findScene(sceneId).dataUrl).catch((error) => {
      pending.delete(sceneId);
      throw error;
    });
    pending.set(sceneId, request);
  }
  return pending.get(sceneId);
}
