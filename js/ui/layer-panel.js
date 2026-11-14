import { LAYERS } from '../config.js';
import { store, setLayerVisible, setLayerOpacity } from '../state/app-store.js';
import { icon } from './icons.js';

export function initLayerPanel(listElement) {
  const rows = new Map();

  for (const layer of LAYERS) {
    const isAvailable = Boolean(layer.source);
    const [first, ...rest] = layer.ramp;
    const last = rest[rest.length - 1] ?? first;

    const item = document.createElement('li');
    item.className = 'ej-layer';
    item.classList.toggle('is-disabled', !isAvailable);
    item.style.setProperty('--layer-a', first);
    item.style.setProperty('--layer-b', last);
    item.style.setProperty('--layer-ramp', `linear-gradient(90deg, ${layer.ramp.join(', ')})`);

    // Icono de color
    const tile = document.createElement('span');
    tile.className = 'ej-layer__icon';
    tile.innerHTML = icon(layer.icon);

    // Interruptor
    const input = document.createElement('input');
    input.className = 'ej-switch';
    input.type = 'checkbox';
    input.id = `layer-${layer.id}`;
    input.setAttribute('role', 'switch');
    input.disabled = !isAvailable;
    input.addEventListener('change', () => setLayerVisible(layer.id, input.checked));

    // Nombre y estado
    const label = document.createElement('label');
    label.className = 'ej-layer__label';
    label.htmlFor = input.id;
    label.textContent = layer.label;

    const badge = document.createElement('span');
    badge.id = `layer-${layer.id}-status`;
    badge.className = `ej-badge ${isAvailable ? 'ej-badge--test' : 'ej-badge--pending'}`;
    badge.textContent = isAvailable ? 'Prueba' : 'Pendiente';
    input.setAttribute('aria-describedby', badge.id);

    // Deslizador de intensidad (opacidad de la capa)
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

    item.append(tile, body, input);
    listElement.append(item);
    rows.set(layer.id, { item, input, slider, amount });
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
    }
  };

  render(store.getState());
  return store.subscribe(render);
}
