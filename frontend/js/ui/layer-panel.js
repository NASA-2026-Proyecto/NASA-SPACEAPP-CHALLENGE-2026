import { LAYERS } from '../config.js';
import { findScene } from '../catalog/scenes.js';
import { isLayerAvailable, sceneIdOf } from '../core/layers.js';
import {
  store,
  setLayerVisible,
  setLayerOpacity,
  setLayerSpecies,
  setScenePlaying,
} from '../state/app-store.js';
import { icon } from './icons.js';

const STAMP_FORMAT = new Intl.DateTimeFormat('es-ES', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'UTC',
});

const toDate = (stamp) => new Date(stamp.replace('Z', ':00Z'));

// Qué tramo recorre la animación y por dónde va. Cadena vacía si no hay nada que animar.
function animationNote(layer, state) {
  const info = state.sceneInfo[sceneIdOf(layer, state.species[layer.id])];
  if (!info || !state.layers[layer.id] || info.stamps.length < 2) return '';
  const hours = (toDate(info.stamps.at(-1)) - toDate(info.stamps[0])) / 3_600_000;
  // Series de varios días (incendios) en días; las demás, en horas
  const inDays = hours >= 48;
  const span = Math.round(inDays ? hours / 24 : hours);
  const unit = (count) => (inDays ? (count === 1 ? 'día' : 'días') : 'h');
  const range = `${inDays ? 'Últimos' : 'Últimas'} ${span} ${unit(span)}`;
  if (!state.scenePlaying) return `${range} · en pausa en el último dato`;
  const back = Math.round((1 - state.sceneProgress) * span);
  return `${range} · ${back === 0 ? 'último dato' : `${back} ${unit(back)} antes`}`;
}

// Qué se está viendo y de cuándo es: cada fuente tiene su propia fecha.
function sceneNote(layer, state) {
  const sceneId = sceneIdOf(layer, state.species[layer.id]);
  if (!sceneId || !state.layers[layer.id]) return '';
  const scene = findScene(sceneId);
  const info = state.sceneInfo[sceneId];
  if (!info) return `${scene.source} · cargando datos de la NASA…`;
  const stamp = STAMP_FORMAT.format(toDate(info.stamps.at(-1)));
  return `${scene.source} · ${scene.stampLabel} ${stamp} UTC`;
}

function buildSpeciesGroup(layer, isAvailable) {
  const groupId = `layer-${layer.id}-species`;

  const wrap = document.createElement('div');
  wrap.className = 'ej-species-wrap';

  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'ej-species-toggle';
  toggle.disabled = !isAvailable;
  toggle.setAttribute('aria-expanded', 'false');
  toggle.setAttribute('aria-controls', groupId);

  const toggleLabel = document.createElement('span');
  toggleLabel.className = 'ej-species-toggle__label';
  toggleLabel.textContent = `Tipo`;

  const toggleValue = document.createElement('span');
  toggleValue.className = 'ej-species-toggle__value';
  const toggleDot = document.createElement('span');
  toggleDot.className = 'ej-species-toggle__dot';
  toggleDot.setAttribute('aria-hidden', 'true');
  const toggleName = document.createElement('span');
  toggleName.className = 'ej-species-toggle__name';
  toggleValue.append(toggleDot, toggleName);

  const chevron = document.createElement('span');
  chevron.className = 'ej-species-toggle__chevron';
  chevron.setAttribute('aria-hidden', 'true');

  toggle.append(toggleLabel, toggleValue, chevron);

  const group = document.createElement('div');
  group.id = groupId;
  group.className = 'ej-species';
  group.hidden = true;
  group.setAttribute('role', 'radiogroup');
  group.setAttribute('aria-label', `Tipo de ${layer.label.toLowerCase()}`);

  toggle.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') === 'true';
    toggle.setAttribute('aria-expanded', String(!open));
    wrap.classList.toggle('is-open', !open);
    group.hidden = open;
  });

  const buttons = new Map();
  const ids = layer.species.map((species) => species.id);

  for (const species of layer.species) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ej-species__option';
    button.setAttribute('role', 'radio');
    button.disabled = !isAvailable;
    button.style.setProperty('--species-color', species.color);
    button.textContent = species.label;
    button.addEventListener('click', () => setLayerSpecies(layer.id, species.id));
    button.addEventListener('keydown', (event) => {
      const forward = event.key === 'ArrowRight' || event.key === 'ArrowDown';
      const backward = event.key === 'ArrowLeft' || event.key === 'ArrowUp';
      if (!forward && !backward) return;
      event.preventDefault();
      const index = ids.indexOf(species.id);
      const next = ids[(index + (forward ? 1 : -1) + ids.length) % ids.length];
      setLayerSpecies(layer.id, next);
      buttons.get(next).focus();
    });
    group.append(button);
    buttons.set(species.id, button);
  }

  wrap.append(toggle, group);
  return { wrap, buttons, toggle, toggleDot, toggleName };
}

export function initLayerPanel(listElement) {
  const rows = new Map();

  for (const layer of LAYERS) {
    const isAvailable = isLayerAvailable(layer);
    const [first, ...rest] = layer.ramp;
    const last = rest[rest.length - 1] ?? first;

    const item = document.createElement('li');
    item.className = 'ej-layer';
    item.classList.toggle('is-disabled', !isAvailable);
    item.style.setProperty('--layer-a', first);
    item.style.setProperty('--layer-b', last);
    item.style.setProperty('--layer-ramp', `linear-gradient(90deg, ${layer.ramp.join(', ')})`);

    const tile = document.createElement('span');
    tile.className = 'ej-layer__icon';
    tile.innerHTML = icon(layer.icon);

    const input = document.createElement('input');
    input.className = 'ej-switch';
    input.type = 'checkbox';
    input.id = `layer-${layer.id}`;
    input.setAttribute('role', 'switch');
    input.disabled = !isAvailable;
    input.addEventListener('change', () => setLayerVisible(layer.id, input.checked));

    const label = document.createElement('label');
    label.className = 'ej-layer__label';
    label.htmlFor = input.id;
    label.textContent = layer.label;

    const badge = document.createElement('span');
    badge.id = `layer-${layer.id}-status`;
    badge.className = `ej-badge ${isAvailable ? 'ej-badge--test' : 'ej-badge--pending'}`;
    badge.textContent = isAvailable ? (layer.badge ?? 'Prueba') : 'Pendiente';
    input.setAttribute('aria-describedby', badge.id);

    const slider = document.createElement('input');
    slider.className = 'ej-slider';
    slider.type = 'range';
    slider.min = '0.1';
    slider.max = '1';
    slider.step = '0.05';
    slider.disabled = !isAvailable;
    slider.setAttribute('aria-label', `Intensidad de ${layer.label}`);
    slider.addEventListener('input', () => setLayerOpacity(layer.id, Number(slider.value)));

    const amount = document.createElement('span');
    amount.className = 'ej-layer__amount';

    const head = document.createElement('div');
    head.className = 'ej-layer__head';
    head.append(label, badge);

    const control = document.createElement('div');
    control.className = 'ej-layer__control';
    control.append(slider, amount);

    const body = document.createElement('div');
    body.className = 'ej-layer__body';
    body.append(head, control);

    let speciesButtons = null;
    let speciesUi = null;
    let note = null;
    let animation = null;
    let animationButton = null;
    let animationLabel = null;
    if (layer.species) {
      speciesUi = buildSpeciesGroup(layer, isAvailable);
      speciesButtons = speciesUi.buttons;
      note = document.createElement('p');
      note.className = 'ej-layer__note';
      note.setAttribute('aria-live', 'polite');

      // Animación: botón de pausa y rótulo del tramo (sin aria-live: cambia varias veces por segundo)
      animation = document.createElement('div');
      animation.className = 'ej-layer__anim';
      animationButton = document.createElement('button');
      animationButton.type = 'button';
      animationButton.className = 'ej-layer__anim-button';
      animationButton.addEventListener('click', () =>
        setScenePlaying(!store.getState().scenePlaying)
      );
      animationLabel = document.createElement('span');
      animationLabel.className = 'ej-layer__anim-label';
      animation.append(animationButton, animationLabel);
      body.append(note, animation);
    }

    item.append(tile, body, input);
    if (speciesUi) item.append(speciesUi.wrap);
    listElement.append(item);
    rows.set(layer.id, {
      layer,
      item,
      input,
      slider,
      amount,
      speciesButtons,
      speciesUi,
      note,
      animation,
      animationButton,
      animationLabel,
    });
  }

  const render = (state) => {
    for (const [id, row] of rows) {
      const on = Boolean(state.layers[id]);
      const opacity = state.opacity[id];
      row.input.checked = on;
      row.item.classList.toggle('is-on', on);
      row.slider.value = String(opacity);
      row.slider.style.setProperty('--fill', `${((opacity - 0.1) / 0.9) * 100}%`);
      row.amount.textContent = `${Math.round(opacity * 100)} %`;

      if (row.speciesButtons) {
        const activeId = state.species[id];
        for (const [speciesId, button] of row.speciesButtons) {
          const active = activeId === speciesId;
          button.classList.toggle('is-active', active);
          button.setAttribute('aria-checked', String(active));
          button.tabIndex = active ? 0 : -1;
        }
        const current = row.layer.species.find((species) => species.id === activeId);
        if (current) {
          row.speciesUi.toggleName.textContent = current.label;
          row.speciesUi.toggle.style.setProperty('--species-color', current.color);
        }
        const text = sceneNote(row.layer, state);
        if (row.note.textContent !== text) row.note.textContent = text;
        row.note.hidden = text === '';

        const moving = animationNote(row.layer, state);
        row.animation.hidden = moving === '';
        if (row.animationLabel.textContent !== moving) row.animationLabel.textContent = moving;
        const playing = state.scenePlaying;
        row.animationButton.textContent = playing ? '⏸' : '▶';
        row.animationButton.setAttribute('aria-label', playing ? 'Pausar la animación' : 'Reproducir la animación');
      }
    }
  };

  render(store.getState());
  return store.subscribe(render);
}