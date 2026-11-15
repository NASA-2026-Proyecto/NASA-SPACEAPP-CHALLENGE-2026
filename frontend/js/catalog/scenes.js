// Escenas: series de mallas (manifiesto + un .f32 por especie) que el mapa dibuja y el
// sonido muestrea. `dataUrl` puede apuntar a archivos estáticos o, como aquí, a la API,
// que prepara la escena con los últimos datos de la NASA.
export const SCENES = [
  {
    id: 'aerosol-latest',
    title: 'Aerosoles globales: últimos pasos del modelo GEOS-FP',
    dataUrl: 'api/scenes/aerosol-latest',
    live: true, // se muestra el paso más reciente
    reference: {
      title: 'GEOS Forward Processing (GEOS-FP)',
      credit: 'NASA Global Modeling and Assimilation Office',
      url: 'https://gmao.gsfc.nasa.gov/',
    },
    defaultSpecies: 'brown_carbon',
    species: [
      { id: 'brown_carbon', label: 'Brown Carbon', color: '#B8733A' },
      { id: 'black_carbon', label: 'Black Carbon', color: '#D45F47' },
      { id: 'dust', label: 'Dust', color: '#C39BDD' },
      { id: 'sea_salt', label: 'Sea Salt', color: '#86ADAA' },
      { id: 'sulfate', label: 'Sulfate', color: '#56E03A' },
    ],
  },
];
