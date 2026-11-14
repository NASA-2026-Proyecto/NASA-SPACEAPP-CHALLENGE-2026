import { createAnimationLoop } from '../core/animation-loop.js';
import { readCssToken } from '../core/css-tokens.js';
import { watchResize } from '../core/resize.js';

const DEFAULTS = {
  density: 0.00009, // estrellas por píxel cuadrado
  maxStars: 500,
  minSpeed: 3,      // píxeles por segundo (estrellas lejanas)
  maxSpeed: 16,     // píxeles por segundo (estrellas cercanas)
};

export function createStarfield(canvas, options = {}) {
  const settings = { ...DEFAULTS, ...options };
  const context = canvas.getContext('2d');
  const color = readCssToken('--ej-star', '#dbe8ff');

  let stars = [];
  let width = 0;
  let height = 0;

  function createStar() {
    const depth = Math.random();
    return {
      x: Math.random() * width,
      y: Math.random() * height,
      radius: 0.4 + depth * 1.1,
      speed: settings.minSpeed + depth * (settings.maxSpeed - settings.minSpeed),
      baseAlpha: 0.25 + depth * 0.65,
      phase: Math.random() * Math.PI * 2,
      twinkle: 0.5 + Math.random() * 1.5,
    };
  }

  function draw(seconds) {
    context.clearRect(0, 0, width, height);
    context.fillStyle = color;
    for (const star of stars) {
      const flicker = 0.75 + 0.25 * Math.sin(star.phase + seconds * star.twinkle);
      context.globalAlpha = star.baseAlpha * flicker;
      context.beginPath();
      context.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
      context.fill();
    }
    context.globalAlpha = 1;
  }

  function update(delta) {
    for (const star of stars) {
      star.x -= star.speed * delta;
      star.y += star.speed * 0.12 * delta;
      if (star.x < -2) star.x = width + 2;
      if (star.y > height + 2) star.y = -2;
    }
  }

  function resize() {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.floor(width * ratio);
    canvas.height = Math.floor(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);

    const count = Math.min(Math.floor(width * height * settings.density), settings.maxStars);
    stars = Array.from({ length: count }, createStar);
    draw(0);
  }

  const loop = createAnimationLoop({
    onFrame(delta, seconds) {
      update(delta);
      draw(seconds);
    },
    onStatic: () => draw(0),
  });

  const stopWatchingResize = watchResize(resize, 150);
  resize();

  return {
    start: loop.start,
    stop: loop.stop,
    destroy() {
      loop.destroy();
      stopWatchingResize();
    },
  };
}