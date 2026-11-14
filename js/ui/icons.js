// Iconos de línea (24x24) para el explorador. Una sola fuente de verdad:
// en el HTML se usan con data-icon="nombre" y explorer.js los rellena.
const PATHS = {
    flame:
      '<path d="M12 2.5c.8 3.6 5.5 6 5.5 11a5.5 5.5 0 0 1-11 0c0-2.2 1-3.8 2.3-5 .2 1.6.9 2.6 1.9 3C10.3 8.6 11.2 5.6 12 2.5z"/>',
    drops:
      '<path d="M12 3.5s5.5 6 5.5 10a5.5 5.5 0 0 1-11 0c0-4 5.5-10 5.5-10z"/><path d="M9.6 14.2a2.6 2.6 0 0 0 2.2 2.3"/>',
    haze:
      '<path d="M3 8.5h10.5a2.5 2.5 0 1 0-2.5-2.5"/><path d="M3 12.5h15a2.5 2.5 0 1 1-2.5 2.5"/><path d="M3 16.5h7a2 2 0 1 1-2 2"/>',
    moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    layers: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 12.5l9 5 9-5"/><path d="M3 16.5l9 5 9-5"/>',
    pin:
      '<path d="M12 21s6.5-5.6 6.5-11a6.5 6.5 0 0 0-13 0c0 5.4 6.5 11 6.5 11z"/><circle cx="12" cy="10" r="2.3"/>',
    signal:
      '<circle cx="12" cy="12" r="1.6"/><path d="M8 8a5.7 5.7 0 0 0 0 8"/><path d="M16 8a5.7 5.7 0 0 1 0 8"/><path d="M5.2 5.2a9.6 9.6 0 0 0 0 13.6"/><path d="M18.8 5.2a9.6 9.6 0 0 1 0 13.6"/>',
    gauge: '<path d="M4.5 17a8 8 0 1 1 15 0"/><path d="M12 14l3.6-4.2"/><circle cx="12" cy="14.4" r="1"/>',
    tone: '<path d="M2.5 12c1.8-6 3.6-6 5.5 0s3.7 6 5.5 0 3.7-6 5.5 0"/>',
    level: '<path d="M6 20v-5"/><path d="M12 20V6"/><path d="M18 20v-9"/>',
    speaker: '<path d="M4 9.5v5h3.5l4.5 3.5V6L7.5 9.5z"/><path d="M15.5 9a4.2 4.2 0 0 1 0 6"/>',
    globe:
      '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c-3.2 3.2-3.2 14.8 0 18"/><path d="M12 3c3.2 3.2 3.2 14.8 0 18"/>',
  };
  
  export function icon(name) {
    const body = PATHS[name];
    if (!body) return '';
    return (
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
      `stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`
    );
  }
  
  // Rellena todos los elementos con data-icon="nombre"
  export function mountIcons(root = document) {
    for (const el of root.querySelectorAll('[data-icon]')) {
      el.innerHTML = icon(el.dataset.icon);
    }
  }
  