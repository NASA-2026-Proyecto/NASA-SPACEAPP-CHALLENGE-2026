import { store, setNightMode } from '../state/app-store.js';

export function initModeToggle(inputElement) {
  inputElement.addEventListener('change', () => setNightMode(inputElement.checked));

  const render = (state) => {
    inputElement.checked = state.nightMode;
  };

  render(store.getState());
  return store.subscribe(render);
}