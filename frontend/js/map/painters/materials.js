// Materiales: el aspecto de cada tipo de evento en el globo. Cada especie del catálogo
// (js/catalog/scenes.js) elige uno con `material`; sin material se pinta un campo liso.
//
// Un material solo cambia el aspecto: textura, relieve, nubes o humo alrededor del dato.
// Los colores siguen saliendo de la rampa de la NASA (o del color de la especie), y la
// ficha y el sonido leen la escena original, nunca el lienzo.
//
// Campos de un material de campo (js/map/painters/raster-painter.js):
//   texture   -> ruido que modula la opacidad (js/map/painters/noise.js)
//   strength  -> cuánto modula: 0 = nada, 1 = la textura puede vaciar del todo un píxel
//   contrast  -> contraste del ruido (más alto = huecos y jirones más marcados)
//   grain     -> segundo ruido, fino: { texture, strength } (grano de polvo, chubascos)
//   shade     -> relieve: aclara las caras de la bruma que miran al noroeste y oscurece
//                las otras, como si la iluminara el sol (0 = plano)
//   whiten    -> cuánto se acerca el color al blanco (nieve)
//   tint      -> para especies de un solo color: { dark, light }, el color de los valores
//                bajos (proporción del color) y de los altos (mezcla con blanco). Poca
//                variación, para que no parezca una nube blanca ni se pierda sobre el suelo
//   drift     -> desplazamiento de la textura por paso, en píxeles: parece llevada por el viento
//   soften    -> desenfoque del dato, en píxeles (solo con nube): suaviza los escalones
//   cloud     -> nube bajo el dato: { blur, colour, alpha, floor, texture, contrast }
//                (floor: opacidad mínima de la textura, para que la nube no quede en jirones)

export const FIELD_MATERIALS = {
  // Bruma: partículas finas (PM2.5, sulfatos). Velo continuo con volumen suave.
  haze: {
    texture: { periodX: 5, periodY: 5, octaves: 5, warp: 1.6, seed: 11 },
    strength: 0.5,
    contrast: 1.4,
    shade: 3,
    tint: { dark: 0.85, light: 0.12 },
    drift: [3, 0],
  },
  // Humo (carbono negro y pardo): jirones alargados en horizontal, con huecos marcados.
  smoke: {
    texture: { periodX: 4, periodY: 9, octaves: 5, warp: 2.6, seed: 23 },
    strength: 0.75,
    contrast: 1.8,
    shade: 2.5,
    tint: { dark: 0.8, light: 0.08 },
    drift: [4, 0],
  },
  // Polvo del desierto: frentes en remolino y un grano arenoso fino.
  dust: {
    texture: { periodX: 6, periodY: 4, octaves: 5, warp: 2.0, seed: 37 },
    strength: 0.6,
    contrast: 1.5,
    grain: { texture: { periodX: 96, periodY: 96, octaves: 2, seed: 41 }, strength: 0.3 },
    shade: 4.5,
    tint: { dark: 0.9, light: 0.15 },
    drift: [3, 1],
  },
  // Sal marina: neblina fina y uniforme sobre el océano.
  mist: {
    texture: { periodX: 8, periodY: 8, octaves: 4, warp: 1.0, seed: 53 },
    strength: 0.4,
    contrast: 1.2,
    shade: 1.5,
    tint: { dark: 0.85, light: 0.1 },
    drift: [2, 0],
  },
  // Lluvia: núcleos de chubasco dentro de una nube blanca con forma de nube.
  rain: {
    texture: { periodX: 24, periodY: 24, octaves: 3, warp: 0.8, seed: 61 },
    strength: 0.35,
    contrast: 1.3,
    shade: 2,
    soften: 1.5,
    drift: [2, 0],
    cloud: {
      blur: 12,
      colour: [236, 241, 246],
      alpha: 0.9,
      floor: 0.25,
      texture: { periodX: 7, periodY: 7, octaves: 6, warp: 2.2, seed: 71 },
      contrast: 1.7,
    },
  },
  // Nieve: más blanca, con un brillo granulado fino y también bajo una nube.
  snow: {
    texture: { periodX: 16, periodY: 16, octaves: 4, warp: 1.2, seed: 83 },
    strength: 0.3,
    contrast: 1.2,
    grain: { texture: { periodX: 128, periodY: 128, octaves: 1, seed: 89 }, strength: 0.35 },
    shade: 1.5,
    whiten: 0.45,
    soften: 1.5,
    drift: [2, 0],
    cloud: {
      blur: 12,
      colour: [242, 246, 252],
      alpha: 0.9,
      floor: 0.25,
      texture: { periodX: 7, periodY: 7, octaves: 6, warp: 2.2, seed: 97 },
      contrast: 1.6,
    },
  },
};
