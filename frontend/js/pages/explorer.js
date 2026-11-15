import { initLayerPanel } from '../ui/layer-panel.js';
import { initModeToggle } from '../ui/mode-toggle.js';
import { createGlobeStatus } from '../ui/globe-status.js';
import { createGlobeMap } from '../map/globe-map.js';
import { initPlayer } from '../ui/player.js';
import { mountIcons } from '../ui/icons.js';
import { createStarfield } from '../effects/starfield.js';
import { store, setReading } from '../state/app-store.js';
import { activeLayer } from '../core/layers.js';
import { getScene } from '../data/scene-cache.js';
import { LAYER_READERS, emptyReading } from '../data/point-reading.js';
import { createPointCard } from '../ui/point-card.js';

mountIcons();
initLayerPanel(document.getElementById('layer-list'));
initModeToggle(document.getElementById('night-mode'));
initPlayer(document.getElementById('player'));

// Fondo de estrellas (el mismo de la portada)
const starfield = createStarfield(document.getElementById('starfield'));
starfield.start();
window.addEventListener('pagehide', () => starfield.stop());
window.addEventListener('pageshow', (event) => {
  if (event.persisted) starfield.start();
});

// El modo noche también cambia algunos detalles de la interfaz (ver explorer-shell.css)
store.subscribe((state) => document.body.classList.toggle('is-night', state.nightMode));

const status = createGlobeStatus({
  container: document.getElementById('globe-container'),
  textElement: document.getElementById('globe-status-text'),
});

// Paneles plegables: capas (izquierda) y punto seleccionado (derecha)
function setPanelOpen(toggle, open) {
  const name = toggle.dataset.panelName;
  toggle.setAttribute('aria-expanded', String(open));
  toggle.setAttribute('aria-label', `${open ? 'Plegar' : 'Desplegar'} panel de ${name}`);
  toggle.firstElementChild.textContent = open ? '–' : '+';
  document.getElementById(toggle.getAttribute('aria-controls')).hidden = !open;
}

const panelToggles = document.querySelectorAll('[data-panel-toggle]');
const isNarrow = window.matchMedia('(max-width: 900px)').matches;

for (const toggle of panelToggles) {
  toggle.addEventListener('click', () =>
    setPanelOpen(toggle, toggle.getAttribute('aria-expanded') !== 'true')
  );
  // En pantallas pequeñas los paneles empiezan plegados para ver el globo
  if (isNarrow) setPanelOpen(toggle, false);
}

// Clic en el globo: lee ese punto en las escenas de la capa activa (ya descargadas o
// pidiéndolas ahora) y lo muestra en la ficha del panel "Punto seleccionado". La lectura se
// guarda en el store; el reproductor, en ese mismo panel, ve el punto nuevo y pide a la API
// el sonido de esa capa. Solo cuenta el último clic. Si cambia la capa, el mismo punto se
// vuelve a leer con la nueva; sin capa activa no se enseña nada.
const COORD_DECIMALS = 5; // ~1 m: más precisión no aporta nada
const round = (value) => Number(value.toFixed(COORD_DECIMALS));

function initPointProbe(globe) {
  const card = createPointCard();
  const coordsSlot = document.getElementById('point-coords');
  const cardSlot = document.getElementById('point-card');
  coordsSlot.append(card.coordinates);
  cardSlot.append(card.element);

  let point = null; // último punto en el que se hizo clic
  let layerId = null; // capa con la que se leyó ese punto

  // Lee el punto con la capa activa. Cada parte llega por su cuenta: si una falla, las
  // demás se muestran igual.
  function probe() {
    const target = point;
    const probedLayerId = layerId;
    const readers = LAYER_READERS[layerId] ?? {};
    const current = () => point === target && layerId === probedLayerId;
    let reading = emptyReading(point, layerId);
    const show = () => {
      card.render(reading);
      setReading(reading);
    };

    const hasInfo = Object.keys(readers).length > 0;
    coordsSlot.hidden = !hasInfo;
    cardSlot.hidden = !hasInfo;
    show();

    for (const [key, { sceneId, read }] of Object.entries(readers)) {
      getScene(sceneId)
        .then((scene) => read(scene, target))
        .catch((error) => {
          console.warn(`[punto] Sin datos de la escena "${sceneId}":`, error);
          return { status: 'error' };
        })
        .then((part) => {
          if (!current()) return; // lo sustituyó otro clic o un cambio de capa
          reading = { ...reading, parts: { ...reading.parts, [key]: part } };
          show();
        });
    }
  }

  globe.map.on('click', (event) => {
    if (!globe.isOnGlobe(event)) return; // clic en el espacio, no sobre la Tierra

    // wrap(): el giro automático puede dejar la longitud fuera de [-180, 180]
    const { lng, lat } = event.lngLat.wrap();
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

    point = { lat: round(lat), lon: round(lng) };
    layerId = activeLayer(store.getState())?.id ?? null;
    globe.showMarker([lng, lat]); // el punto se señala en el globo con un marcador
    probe();
  });

  // La ficha enseña los datos de la capa activa: al cambiar de capa, el mismo punto se lee
  // otra vez (el punto es el mismo objeto, así que el reproductor no lo toma por un clic)
  store.subscribe((state) => {
    const nextLayerId = activeLayer(state)?.id ?? null;
    if (nextLayerId === layerId) return;
    layerId = nextLayerId;
    if (point) probe();
  });
}

// El rótulo superior dice qué capa se oye al hacer clic (o que no suena nada)
const modeChip = document.getElementById('mode-chip-text');
function showSoundMode(state) {
  const layer = activeLayer(state);
  const text = layer ? `Sonido: ${layer.label}` : 'Sin capa activa: en silencio';
  if (modeChip.textContent !== text) modeChip.textContent = text;
}
store.subscribe(showSoundMode);
showSoundMode(store.getState());

createGlobeMap({ container: 'map' })
  .then((globe) => {
    status.setReady();
    document.getElementById('fly-spain').addEventListener('click', () => globe.flyTo('spain'));
    initPointProbe(globe);
  })
  .catch((error) => {
    console.error(error);
    status.setError(error.message);
  });
