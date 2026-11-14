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
      id: 'fire',
      label: 'Incendios',
      colorVar: '--ej-fire',
      icon: 'flame',
      ramp: ['#ff5a4d', '#d62f6f', '#7a3cf0'], // de rojo a morado
      defaultOpacity: 0.9,
      // source: { layerId: '…', matrixSet: '…', maxZoom: …, format: 'png' },  <- pendiente
    },
    {
      id: 'rain',
      label: 'Precipitación',
      colorVar: '--ej-rain',
      icon: 'drops',
      ramp: ['#8be9ff', '#2f8cff', '#1537b8'], // de celeste a azul intenso
      defaultOpacity: 0.85,
      // source: { layerId: '…', matrixSet: '…', maxZoom: …, format: 'png' },  <- pendiente
    },
    {
      id: 'aerosol',
      label: 'Aerosoles', // la insignia "Prueba" la pone el panel al tener datos de ejemplo
      colorVar: '--ej-aerosol',
      icon: 'haze',
      ramp: ['#ffe29a', '#ff9f43', '#c44569'], // de dorado a rosa
      defaultOpacity: 0.85,
      // Ajuste de color de las teselas. Se prueba a ojo: cambia 'raster-hue-rotate' (0-360)
      // para desplazar todos los colores y 'raster-saturation' / 'raster-contrast' (-1 a 1).
      paint: {
        'raster-hue-rotate': 0,
        'raster-saturation': 0.25,
        'raster-contrast': 0.1,
      },
      source: {
        layerId: 'MODIS_Terra_Aerosol',
        matrixSet: 'GoogleMapsCompatible_Level6',
        maxZoom: 6,
        format: 'png',
        time: '2014-04-09', // fecha del ejemplo oficial; sirve para comprobar que todo funciona
      },
    },
  ];
  