// Catálogo de capas del explorador.
//
// Campos:
//   id, label, colorVar   -> los de siempre
//   icon                  -> nombre de js/ui/icons.js
//   ramp                  -> colores de la capa, de "poco" a "mucho" (iconos, deslizador)
//   defaultOpacity        -> opacidad inicial (0-1)
//   paint                 -> ajustes de color del ráster (hue-rotate, saturation, contrast...)
//   source                -> origen de los datos (NASA GIBS). SIN "source" la capa aparece
//                            como "Pendiente"; al añadirlo, se activa sola.
export const LAYERS = [
  {
    id: "fire",
    label: "Incendios",
    colorVar: "--ej-fire",
    icon: "flame",
    ramp: ["#ff5a4d", "#d62f6f", "#7a3cf0"], // de rojo a morado
    defaultOpacity: 0.9,
    // source: { layerId: '…', matrixSet: '…', maxZoom: …, format: 'png' },  <- pendiente
  },
  {
    id: "rain",
    label: "Precipitación",
    colorVar: "--ej-rain",
    icon: "drops",
    ramp: ["#8be9ff", "#2f8cff", "#1537b8"], // de celeste a azul intenso
    defaultOpacity: 0.85,
    // source: { layerId: '…', matrixSet: '…', maxZoom: …, format: 'png' },  <- pendiente
  },
  {
    id: "aerosol",
    label: "Aerosoles",
    colorVar: "--ej-aerosol",
    icon: "haze",
    ramp: ["#ffe29a", "#ff9f43", "#c44569"],
    defaultOpacity: 0.85,
    badge: "Muestra",
    kind: "grid",
    data: { url: "assets/data/aerosols_iberia_20261101T0430Z.json" },
    // scaleMax: percentil 99 global del 2026-11-01 04:30 UTC (provisional)
    defaultSpecies: "dust",
    species: [
      {
        id: "black_carbon",
        label: "Black Carbon",
        color: "#D45F47",
        scaleMax: 0.026,
      },
      { id: "dust", label: "Dust", color: "#C39BDD", scaleMax: 0.148 },
      { id: "sea_salt", label: "Sea Salt", color: "#86ADAA", scaleMax: 0.183 },
      { id: "sulfate", label: "Sulfate", color: "#56E03A", scaleMax: 0.18 },
    ],
  },
];
