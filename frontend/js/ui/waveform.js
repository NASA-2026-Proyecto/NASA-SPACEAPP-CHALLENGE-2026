const POINTS = 160;
const WINDOW = 1024; // muestras que se dibujan: unos 23 ms de sonido
const SMOOTHING = 0.35;

export function createWaveform(canvas, engine) {
  const g = canvas.getContext('2d');
  const smooth = new Float32Array(POINTS);
  const target = new Float32Array(POINTS);
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const accent =
    getComputedStyle(document.documentElement).getPropertyValue('--ej-accent').trim() ||
    '#5eb0ff';

  let buffer = null;
  let raf = 0;
  let tick = 0;
  let w = 0;
  let h = 0;

  function resize() {
    const rect = canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    w = rect.width;
    h = rect.height;
    draw();
  }

  function sample() {
    const analyser = engine.getAnalyser();
    if (!analyser || !engine.isPlaying()) {
      target.fill(0);
      return;
    }
    if (!buffer) buffer = new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(buffer);

    const span = Math.min(buffer.length / 2, WINDOW);

    let start = 0;
    for (let i = 1; i < buffer.length - span; i++) {
      if (buffer[i - 1] < 0 && buffer[i] >= 0) {
        start = i;
        break;
      }
    }

    for (let p = 0; p < POINTS; p++) {
      const pos = start + (p / (POINTS - 1)) * (span - 1);
      const i0 = Math.floor(pos);
      const frac = pos - i0;
      target[p] = buffer[i0] * (1 - frac) + buffer[i0 + 1] * frac;
    }
  }

  function draw() {
    g.clearRect(0, 0, w, h);
    const mid = h / 2;
    const amp = h * 0.45;

    g.strokeStyle = 'rgba(150, 190, 255, 0.15)';
    g.lineWidth = 1;
    g.beginPath();
    g.moveTo(0, mid);
    g.lineTo(w, mid);
    g.stroke();

    const grad = g.createLinearGradient(0, 0, w, 0);
    grad.addColorStop(0, 'rgba(94, 176, 255, 0)');
    grad.addColorStop(0.15, accent);
    grad.addColorStop(0.85, accent);
    grad.addColorStop(1, 'rgba(94, 176, 255, 0)');

    g.strokeStyle = grad;
    g.lineWidth = 2;
    g.lineJoin = 'round';
    g.shadowColor = reduced ? 'transparent' : accent;
    g.shadowBlur = reduced ? 0 : 8;

    g.beginPath();
    const x = (i) => (i / (POINTS - 1)) * w;
    const y = (i) => mid - smooth[i] * amp;
    g.moveTo(x(0), y(0));
    for (let i = 1; i < POINTS - 1; i++) {
      const mx = (x(i) + x(i + 1)) / 2;
      const my = (y(i) + y(i + 1)) / 2;
      g.quadraticCurveTo(x(i), y(i), mx, my);
    }
    g.lineTo(x(POINTS - 1), y(POINTS - 1));
    g.stroke();
    g.shadowBlur = 0;
  }

  function frame() {
    raf = requestAnimationFrame(frame);
    if (reduced && ++tick % 4 !== 0) return;

    sample();
    let peak = 0;
    for (let p = 0; p < POINTS; p++) {
      smooth[p] += (target[p] - smooth[p]) * SMOOTHING;
      peak = Math.max(peak, Math.abs(smooth[p]));
    }
    draw();

    if (!engine.isPlaying() && peak < 0.002) {
      cancelAnimationFrame(raf);
      raf = 0;
      smooth.fill(0);
      draw();
    }
  }

  new ResizeObserver(resize).observe(canvas);
  resize();

  return {
    wake() {
      if (!raf) raf = requestAnimationFrame(frame);
    },
  };
}