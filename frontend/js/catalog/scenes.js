export const SCENES = [
    {
      id: 'global-aerosols-2026-07',
      title: 'Aerosoles globales, 24–28 de julio de 2026',
      dataUrl: 'assets/data/scenes/global-aerosols-2026-07',
      reference: {
        title: 'Smoke from Record-Breaking Wildfires in Spain and France',
        credit: 'NASA Scientific Visualization Studio',
        url: 'https://svs.gsfc.nasa.gov/5666/',
      },
      focus: { center: [-3.7, 40.4], zoom: 3 },
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