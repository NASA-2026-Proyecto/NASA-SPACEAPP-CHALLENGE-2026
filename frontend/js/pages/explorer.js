import { initLayerPanel } from '../ui/layer-panel.js';
import { initModeToggle } from '../ui/mode-toggle.js';
import { createGlobeStatus } from '../ui/globe-status.js';
import { createGlobeMap } from '../map/globe-map.js';
import { initPlayer } from '../ui/player.js';
import { mountIcons } from '../ui/icons.js';
import { createStarfield } from '../effects/starfield.js';
import { store, setReading } from '../state/app-store.js';
import { getScene } from '../data/scene-cache.js';
import {
  PM25_SCENE,
  LIVE_SCENE,
  emptyReading,
  readPm25,
  readAerosols,
} from '../data/point-reading.js';
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

// Paneles plegables: capas (izquierda) y señal (derecha)
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

// Clic en el globo: lee ese punto en las escenas (ya descargadas o pidiéndolas ahora) y lo
// muestra en una ficha fija. No hay viaje al servidor por clic. La lectura se guarda en el
// store: el reproductor la convierte en sonido. Solo cuenta el último clic.
const COORD_DECIMALS = 5; // ~1 m: más precisión no aporta nada
const round = (value) => Number(value.toFixed(COORD_DECIMALS));

function initPointProbe(globe) {
  const card = createPointCard();
  let latest = null;

  // La ficha va en la esquina inferior derecha, para no tapar el globo; el punto se
  // señala con un marcador.
  const dock = document.createElement('aside');
  dock.className = 'ej-point-dock';
  dock.hidden = true;
  dock.setAttribute('aria-label', 'Punto seleccionado');
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'ej-point-dock__close';
  close.setAttribute('aria-label', 'Cerrar la ficha del punto');
  close.textContent = '×';
  close.addEventListener('click', () => {
    dock.hidden = true;
    globe.hideMarker();
  });
  dock.append(close, card.element);
  document.body.append(dock);

  globe.map.on('click', (event) => {
    if (!globe.isOnGlobe(event)) return; // clic en el espacio, no sobre la Tierra

    // wrap(): el giro automático puede dejar la longitud fuera de [-180, 180]
    const { lng, lat } = event.lngLat.wrap();
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

    const point = { lat: round(lat), lon: round(lng) };
    latest = point;
    let reading = emptyReading(point);
    const show = (part) => {
      if (latest !== point) return; // lo sustituyó un clic posterior
      reading = { ...reading, ...part };
      card.render(reading);
      setReading(reading);
    };

    show({});
    dock.hidden = false;
    globe.showMarker([lng, lat]);

    // Cada fuente llega por su cuenta: si una falla, la otra se muestra igual
    getScene(PM25_SCENE)
      .then((scene) => show({ pm25: readPm25(scene, point) }))
      .catch((error) => {
        console.warn('[punto] Sin escena de PM2.5:', error);
        show({ pm25: { status: 'error' } });
      });
    getScene(LIVE_SCENE)
      .then((scene) => show({ live: readAerosols(scene, point) }))
      .catch((error) => {
        console.warn('[punto] Sin escena casi en tiempo real:', error);
        show({ live: { status: 'error' } });
      });
  });
}

// El rótulo superior dice si lo que suena es la demostración o datos de la NASA
const modeChip = document.getElementById('mode-chip-text');
store.subscribe((state) => {
  const text = state.reading?.pm25.status === 'ok' ? 'Datos de la NASA' : 'Modo demostración';
  if (modeChip.textContent !== text) modeChip.textContent = text;
});

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
