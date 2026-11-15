// Catálogo de capas del explorador.
//
// Campos:
//   id, label             -> identificador y nombre que se muestra
//   icon                  -> nombre de js/ui/icons.js
//   ramp                  -> colores de la capa, de "poco" a "mucho" (iconos, deslizador)
//   defaultOpacity        -> opacidad inicial (0-1)
//   kind: 'scene' + scenes -> la capa dibuja escenas (js/catalog/scenes.js). Cada botón de
//                            especie pertenece a una escena; el primero es el de por defecto.
//                            SIN escenas la capa aparece como "Pendiente".
import { findScene } from './catalog/scenes.js';

// Aerosoles: primero la visualización diaria del EIC (PM2.5) y después las especies del
// modelo casi en tiempo real.
const AEROSOL_SCENES = ['pm25-latest', 'aerosol-latest'];
// Incendios: la visualización diaria del EIC (potencia radiativa, VIIRS).
const FIRE_SCENES = ['fires-latest'];
// Precipitación: la visualización del EIC (IMERG), con la lluvia y la nieve por separado.
const RAIN_SCENES = ['precipitation-latest'];
const speciesOf = (sceneIds) =>
  sceneIds.flatMap((sceneId) =>
    findScene(sceneId).species.map((species) => ({ ...species, sceneId }))
  );

export const LAYERS = [
  {
    id: "fire",
    label: "Incendios",
    icon: "flame",
    ramp: ["#ff5a4d", "#d62f6f", "#7a3cf0"], // de rojo a morado
    defaultOpacity: 0.9,
    badge: 'NASA',
    kind: 'scene',
    scenes: FIRE_SCENES,
    species: speciesOf(FIRE_SCENES),
  },
  {
    id: "rain",
    label: "Precipitación",
    icon: "drops",
    ramp: ["#8be9ff", "#2f8cff", "#1537b8"], // de celeste a azul intenso
    defaultOpacity: 0.85,
    badge: 'NASA',
    kind: 'scene',
    scenes: RAIN_SCENES,
    species: speciesOf(RAIN_SCENES),
  },
  {
    id: 'aerosol',
    label: 'Aerosoles',
    icon: 'haze',
    ramp: ['#ffe29a', '#ff9f43', '#c44569'],
    defaultOpacity: 0.85,
    badge: 'NASA',
    kind: 'scene',
    scenes: AEROSOL_SCENES,
    species: speciesOf(AEROSOL_SCENES),
  },
];
