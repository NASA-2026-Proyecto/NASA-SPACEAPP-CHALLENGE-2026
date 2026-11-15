import { createStarfield } from '../effects/starfield.js';
import { createDottedGlobe } from '../effects/dotted-globe.js';
import { reducedMotionQuery } from '../core/motion.js';
import { bindDialog } from '../ui/dialog.js';

const LEAVE_DELAY_MS = 400;

const starfieldCanvas = document.getElementById('starfield');
const globeCanvas = document.getElementById('globe-canvas');
const enterButton = document.getElementById('enter-button');
const aboutDialog = document.getElementById('about-dialog');
const aboutButton = document.getElementById('about-button');

let starfield = null;
let globe = null;

async function initGlobe() {
  try {
    globe = await createDottedGlobe(globeCanvas);
    globe.start();
    globeCanvas.classList.add('is-ready');
  } catch (error) {
    console.warn('[landing] Globo 3D no disponible; se usa el fondo estático.', error);
    document.body.classList.add('landing--static');
  }
}

if (aboutDialog && aboutButton) {
  bindDialog({ dialog: aboutDialog, openButton: aboutButton });
}

if (starfieldCanvas) {
  starfield = createStarfield(starfieldCanvas);
  starfield.start();
}

if (globeCanvas) {
  initGlobe();
}

window.addEventListener('pagehide', (event) => {
  if (starfield) starfield.stop();
  if (!globe) return;
  if (event.persisted) globe.stop();
  else globe.destroy();
});

window.addEventListener('pageshow', (event) => {
  if (!event.persisted) return;
  if (starfield) starfield.start();
  if (globe) globe.start();
});

if (enterButton) {
  enterButton.addEventListener('click', (event) => {
    const modified =
      event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0;

    if (modified || reducedMotionQuery.matches) return;

    event.preventDefault();
    document.body.classList.add('is-leaving');
    window.setTimeout(() => {
      window.location.href = enterButton.href;
    }, LEAVE_DELAY_MS);
  });
}