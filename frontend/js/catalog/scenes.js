// Escenas: series de mallas (manifiesto + un .f32 por especie) que el mapa dibuja y el
// sonido muestrea. `dataUrl` puede apuntar a archivos estáticos o, como aquí, a la API,
// que prepara cada escena con los últimos datos de la NASA.
//
//   source      -> de dónde vienen los datos, en corto (se enseña en el panel)
//   stampLabel  -> qué significa la fecha del manifiesto ("dato del" / "publicado el")
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
    species: [{ id: 'pm25', label: 'EIC PM 2.5', color: '#E8862E' }],
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
      { id: 'brown_carbon', label: 'Brown Carbon', color: '#B8733A' },
      { id: 'black_carbon', label: 'Black Carbon', color: '#D45F47' },
      { id: 'dust', label: 'Dust', color: '#C39BDD' },
      { id: 'sea_salt', label: 'Sea Salt', color: '#86ADAA' },
      { id: 'sulfate', label: 'Sulfate', color: '#56E03A' },
    ],
  },
];

export const findScene = (id) => SCENES.find((scene) => scene.id === id);
