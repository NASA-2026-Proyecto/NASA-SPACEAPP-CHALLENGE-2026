// Escenas: series de mallas (manifiesto + un .f32 por especie) que el mapa dibuja y el
// sonido muestrea. `dataUrl` puede apuntar a archivos estáticos o, como aquí, a la API,
// que prepara cada escena con los últimos datos de la NASA.
//
//   source      -> de dónde vienen los datos, en corto (se enseña en el panel)
//   stampLabel  -> qué significa la fecha del manifiesto ("dato del" / "publicado el")
//   species     -> id, label y color del botón; `fade: 'sparse'` si el dato solo cubre
//                  parte del mapa y hasta su valor más bajo debe verse
//                  (js/map/painters/raster-painter.js); `material`, el aspecto en el globo:
//                  'embers' (puntos encendidos, js/map/painters/ember-painter.js) o una
//                  textura de js/map/painters/materials.js ('haze', 'smoke', 'dust',
//                  'mist', 'rain', 'snow'). El color también es el del punto del panel y
//                  la barra de la ficha, así que tiene que leerse sobre fondo oscuro.
export const SCENES = [
  {
    // Visualización diaria del Earth Information Center: el campo completo, "dónde y cuánto"
    id: 'pm25-latest',
    title: 'Partículas PM2.5: visualización diaria del EIC',
    dataUrl: 'api/scenes/pm25-latest',
    source: 'Visualización diaria del EIC (modelo GEOS-CF)',
    stampLabel: 'publicada el',
    reference: {
      title: 'Particulate Matter (PM) 2.5',
      credit: 'NASA Scientific Visualization Studio',
      url: 'https://svs.gsfc.nasa.gov/5151/',
    },
    species: [{ id: 'pm25', label: 'EIC PM 2.5', color: '#E8862E', material: 'haze' }],
  },
  {
    // API casi en tiempo real: de qué están hechas las partículas
    id: 'aerosol-latest',
    title: 'Aerosoles globales: últimos pasos del modelo GEOS-FP',
    dataUrl: 'api/scenes/aerosol-latest',
    source: 'Casi en tiempo real (modelo GEOS-FP)',
    stampLabel: 'dato del',
    reference: {
      title: 'GEOS Forward Processing (GEOS-FP)',
      credit: 'NASA Global Modeling and Assimilation Office',
      url: 'https://gmao.gsfc.nasa.gov/',
    },
    species: [
      { id: 'brown_carbon', label: 'Brown Carbon', color: '#C4894E', material: 'smoke' },
      { id: 'black_carbon', label: 'Black Carbon', color: '#8E8780', material: 'smoke' },
      { id: 'dust', label: 'Dust', color: '#E89A4C', material: 'dust' },
      { id: 'sea_salt', label: 'Sea Salt', color: '#8FD3DC', material: 'mist' },
      { id: 'sulfate', label: 'Sulfate', color: '#E2D27E', material: 'haze' },
    ],
  },
  {
    // Visualización diaria del EIC: incendios activos vistos por VIIRS, un fotograma por día
    id: 'fires-latest',
    title: 'Incendios activos (VIIRS): visualización diaria del EIC',
    dataUrl: 'api/scenes/fires-latest',
    source: 'Visualización diaria del EIC (satélite VIIRS, ventana de 5 días)',
    stampLabel: 'dato del',
    reference: {
      title: 'Active Fires As Observed by VIIRS, 2024-Present',
      credit: 'NASA Scientific Visualization Studio',
      url: 'https://svs.gsfc.nasa.gov/5113/',
    },
    species: [{ id: 'frp', label: 'EIC Incendios', color: '#FF6A1F', material: 'embers' }],
  },
  {
    // Visualización del EIC: precipitación de los satélites GPM (IMERG), cada media hora
    id: 'precipitation-latest',
    title: 'Precipitación casi en tiempo real (GPM IMERG): visualización del EIC',
    dataUrl: 'api/scenes/precipitation-latest',
    source: 'Visualización del EIC (satélites GPM, IMERG)',
    stampLabel: 'dato del',
    reference: {
      title: 'Near Real-Time Global Precipitation from the Global Precipitation Measurement Constellation',
      credit: 'NASA Scientific Visualization Studio',
      url: 'https://svs.gsfc.nasa.gov/4285/',
    },
    species: [
      { id: 'rain', label: 'Lluvia', color: '#60D300', fade: 'sparse', material: 'rain' },
      { id: 'snow', label: 'Nieve', color: '#4F9AFF', fade: 'sparse', material: 'snow' },
    ],
  },
];

export const findScene = (id) => SCENES.find((scene) => scene.id === id);
