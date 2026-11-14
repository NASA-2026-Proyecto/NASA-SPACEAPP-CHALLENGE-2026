import * as THREE from "three";
import { createAnimationLoop } from "../core/animation-loop.js";
import { createPointerParallax } from "../core/pointer-parallax.js";
import { watchResize } from "../core/resize.js";
import { loadLandMask, buildLandPositions } from "./globe/land-mask.js";
import { createHoverProbe } from "./globe/hover-probe.js";
import { buildPlanet } from "./globe/planet.js";
import { createPulseSystem } from "./globe/pulses.js";
import { loadGlobeTheme } from "./globe/theme.js";

// Usamos los colores CSS tal cual, sin conversión de espacio de color
THREE.ColorManagement.enabled = false;

const TAU = Math.PI * 2;

const DEFAULTS = {
  // Datos
  maskUrl: "assets/images/earth-water.png",
  maskWidth: 720,
  maskHeight: 360,
  candidateDots: 120000,

  // Puntos
  dotCoverage: 0.38, // diámetro del punto como fracción de la separación entre puntos

  // Composición
  cameraZ: 3.2,
  fov: 35,
  maxRadiusFactor: 1.2, // tamaño máximo del planeta en pantallas anchas
  planetScale: 1.3, //aumenta el tamaño de la esfera
  planetTop: -0.35, // cuánto baja el borde superior del planeta (0 = centro de la pantalla)
  tiltX: 0.75, // inclinación hacia la cámara
  tiltZ: -0.41,

  // Movimiento
  spinSpeed: 0.035, // radianes por segundo
  playheadSpeed: 0.45, // velocidad del cabezal de lectura
  pulseCount: 5,
  introSeconds: 2.4,
  introDrop: 0.55, // cuánto sube el planeta al entrar (fracción de media pantalla)

  // Capas
  bodyScale: 0.985,
  glowScale: 1.1,
  glowIntensity: 0.85,
  glowFalloff: 2.2,
};

function releaseRenderer(renderer) {
  renderer.dispose();
  renderer.forceContextLoss();
}

export async function createDottedGlobe(canvas, options = {}) {
  const settings = { ...DEFAULTS, ...options };

  const renderer = new THREE.WebGLRenderer({
    canvas,
    alpha: true,
    antialias: true,
  });
  renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
  renderer.setClearColor(0x000000, 0);

  let positions;
  let landMask;
  try {
    landMask = await loadLandMask({
      url: settings.maskUrl,
      width: settings.maskWidth,
      height: settings.maskHeight,
    });

    const result = buildLandPositions(landMask, settings.candidateDots);
    positions = result.positions;
    console.info(
      `[globe] ${(result.landRatio * 100).toFixed(1)} % de los puntos son tierra (esperado: 25-35 %)`,
    );
  } catch (error) {
    releaseRenderer(renderer);
    throw error;
  }

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(settings.fov, 1, 0.1, 30);
  camera.position.set(0, 0, settings.cameraZ);

  const theme = loadGlobeTheme();
  const {
    planet,
    tilt,
    spin,
    dotUniforms,
    glowUniforms,
    dispose: disposePlanet,
  } = buildPlanet({
    positions,
    theme,
    settings,
    landMask,
  });
  scene.add(planet);

  const pulses = createPulseSystem({
    parent: spin,
    positions,
    colors: theme.pulses,
    count: settings.pulseCount,
  });
  const parallax = createPointerParallax();
  const hover = createHoverProbe({
    camera,
    planet,
    spin,
    uniforms: dotUniforms,
  });

  const layoutState = { baseX: 0, baseY: 0, drop: 0 };
  let intro = 0;
  let lastSeconds = 0;

  // Entrada del planeta y "respiración" del halo
  function present() {
    const eased = 1 - Math.pow(1 - intro, 4);
    const breathing = 1 + 0.06 * Math.sin(lastSeconds * 0.8);
    planet.position.x = layoutState.baseX;
    planet.position.y = layoutState.baseY - (1 - eased) * layoutState.drop;
    glowUniforms.uIntensity.value = settings.glowIntensity * eased * breathing;
  }

  function layout() {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) return;

    const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(pixelRatio);
    renderer.setSize(width, height, false);

    camera.aspect = width / height;
    camera.updateProjectionMatrix();

    const halfHeight =
      camera.position.z * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
    const radius =
      halfHeight *
      THREE.MathUtils.clamp(
        camera.aspect * 0.8,
        0.95,
        settings.maxRadiusFactor,
      ) *
      settings.planetScale;
    planet.scale.setScalar(radius);
    layoutState.baseX = radius * 1;
    layoutState.baseY = -halfHeight * settings.planetTop - radius;
    layoutState.drop = halfHeight * settings.introDrop;
    present();

    // El punto se dimensiona según la separación real entre puntos en pantalla
    const pixelsPerUnit = height / (2 * halfHeight);
    const radiusPx = radius * pixelsPerUnit * pixelRatio;
    const spacingPx =
      radiusPx * Math.sqrt((4 * Math.PI) / settings.candidateDots);
    const dotPx = Math.max(spacingPx * settings.dotCoverage, 1.2 * pixelRatio);
    dotUniforms.uSize.value = dotPx * camera.position.z;

    renderer.render(scene, camera);
  }

  const loop = createAnimationLoop({
    onFrame(delta, seconds) {
      lastSeconds = seconds;
      intro = Math.min(intro + delta / settings.introSeconds, 1);
      present();

      spin.rotation.y += settings.spinSpeed * delta;

      const playhead = (seconds * settings.playheadSpeed) % TAU;
      dotUniforms.uPlayhead.value = playhead;
      dotUniforms.uPlayheadStrength.value = 1;

      parallax.update(delta);
      tilt.rotation.x = settings.tiltX + parallax.value.y * 0.1;
      tilt.rotation.y = parallax.value.x * 0.2;

      hover.update(parallax.pointer, delta);
      pulses.update(delta, playhead);

      renderer.render(scene, camera);
    },
    onStatic() {
      intro = 1;
      lastSeconds = 0;
      dotUniforms.uPlayheadStrength.value = 0;
      hover.reset();
      pulses.hideAll();
      present();
      renderer.render(scene, camera);
    },
  });

  const stopWatchingResize = watchResize(layout);
  layout();

  return {
    start: loop.start,
    stop: loop.stop,
    destroy() {
      loop.destroy();
      stopWatchingResize();
      parallax.destroy();
      pulses.dispose();
      disposePlanet();
      releaseRenderer(renderer);
    },
  };
}
