import * as THREE from 'three';
import * as shaders from './shaders.js';

export function buildPlanet({ positions, theme, settings, landMask }) {
  const planet = new THREE.Group();
  const tilt = new THREE.Group();
  const spin = new THREE.Group();
  tilt.rotation.set(settings.tiltX, 0, settings.tiltZ);
  planet.add(tilt);
  tilt.add(spin);

  const sphere = new THREE.SphereGeometry(1, 64, 64);

  // Cuerpo oscuro: oculta los puntos del lado de atrás
  const bodyMaterial = new THREE.ShaderMaterial({
    vertexShader: shaders.SPHERE_VERTEX,
    fragmentShader: shaders.BODY_FRAGMENT,
    uniforms: {
      uBase: { value: theme.body },
      uRim: { value: theme.rim },
    },
  });
  const body = new THREE.Mesh(sphere, bodyMaterial);
  body.scale.setScalar(settings.bodyScale);
  spin.add(body);

  // NUEVO: superficie holográfica de los continentes (queda entre el cuerpo y los puntos)
  const landMaterial = new THREE.ShaderMaterial({
    vertexShader: shaders.LAND_VERTEX,
    fragmentShader: shaders.LAND_FRAGMENT,
    uniforms: {
      uLandMask: { value: landMask.texture },
      uLandIsDark: { value: landMask.landIsDark ? 1 : 0 },
      uTexel: { value: new THREE.Vector2(1 / settings.maskWidth, 1 / settings.maskHeight) },
      uOcean: { value: theme.ocean },
      uLand: { value: theme.land },
      uOutline: { value: theme.outline },
      uAtmosphere: { value: new THREE.Color(0x32bcd0) },
      uGrid: { value: 0.12 },     // intensidad de la rejilla (0 = sin rejilla)
      uSparkle: { value: 0.55 },  // intensidad de los destellos (0 = sin destellos)
    },
  });
  const landSurface = new THREE.Mesh(sphere, landMaterial);
  landSurface.scale.setScalar(settings.bodyScale * 1.003);
  spin.add(landSurface);

  const dotGeometry = new THREE.BufferGeometry();
  dotGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const dotMaterial = new THREE.ShaderMaterial({
    vertexShader: shaders.DOT_VERTEX,
    fragmentShader: shaders.DOT_FRAGMENT,
    transparent: true,
    depthWrite: false,
    uniforms: {
      uSize: { value: 1 },
      uColor: { value: theme.dot },
      uRim: { value: theme.rim },
      uAccent: { value: theme.highlight },
      uHover: { value: new THREE.Vector3(0, 0, 1) },
      uHoverStrength: { value: 0 },
      uPlayhead: { value: 0 },
      uPlayheadStrength: { value: 0 },
    },
  });
  const dots = new THREE.Points(dotGeometry, dotMaterial);
  dots.frustumCulled = false;
  spin.add(dots);

  const glowMaterial = new THREE.ShaderMaterial({
    vertexShader: shaders.SPHERE_VERTEX,
    fragmentShader: shaders.GLOW_FRAGMENT,
    side: THREE.BackSide,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uColor: { value: theme.atmosphere },
      uIntensity: { value: settings.glowIntensity },
      uFalloff: { value: settings.glowFalloff },
    },
  });
  const glow = new THREE.Mesh(sphere, glowMaterial);
  glow.scale.setScalar(settings.glowScale);
  planet.add(glow);

  function dispose() {
    sphere.dispose();
    dotGeometry.dispose();
    bodyMaterial.dispose();
    landMaterial.dispose();
    landMask.texture.dispose();
    dotMaterial.dispose();
    glowMaterial.dispose();
  }

  return {
    planet,
    tilt,
    spin,
    dotUniforms: dotMaterial.uniforms,
    glowUniforms: glowMaterial.uniforms,
    dispose,
  };
}