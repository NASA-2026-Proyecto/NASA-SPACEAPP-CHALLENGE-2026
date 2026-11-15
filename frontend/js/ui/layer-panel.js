import { LAYERS } from '../config.js';
import { isLayerAvailable } from '../core/layers.js';
import { store, setLayerVisible, setLayerOpacity, setLayerSpecies } from '../state/app-store.js';
import { icon } from './icons.js';

function buildSpeciesGroup(layer, isAvailable) {
  const group = document.createElement('div');
  group.className = 'ej-species';
  group.setAttribute('role', 'radiogroup');
  group.setAttribute('aria-label', `Tipo de ${layer.label.toLowerCase()}`);

  const buttons = new Map();
  for (const species of layer.species) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ej-species__option';
    button.setAttribute('role', 'radio');
    button.disabled = !isAvailable;
    button.style.setProperty('--species-color', species.color);
    button.textContent = species.label;
    button.addEventListener('click', () => setLayerSpecies(layer.id, species.id));
    group.append(button);
    buttons.set(species.id, button);
  }
  return { group, buttons };
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
    if (layer.species) {
      const { group, buttons } = buildSpeciesGroup(layer, isAvailable);
      body.append(group);
      speciesButtons = buttons;
    }

    item.append(tile, body, input);
    listElement.append(item);
    rows.set(layer.id, { item, input, slider, amount, speciesButtons });
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
        for (const [speciesId, button] of row.speciesButtons) {
          const active = state.species[id] === speciesId;
          button.classList.toggle('is-active', active);
          button.setAttribute('aria-checked', String(active));
        }
      }
    }
  };

  render(store.getState());
  return store.subscribe(render);
}