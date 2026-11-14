import { initLayerPanel } from '../ui/layer-panel.js';
import { initModeToggle } from '../ui/mode-toggle.js';
import { createGlobeStatus } from '../ui/globe-status.js';
import { createGlobeMap } from '../map/globe-map.js';
import { initPlayer } from '../ui/player.js';
import { mountIcons } from '../ui/icons.js';
import { createStarfield } from '../effects/starfield.js';
import { store } from '../state/app-store.js';

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

createGlobeMap({ container: 'map' })
  .then((globe) => {
    status.setReady();
    document.getElementById('fly-spain').addEventListener('click', () => globe.flyTo('spain'));
  })
  .catch((error) => {
    console.error(error);
    status.setError(error.message);
  });
