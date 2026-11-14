import * as THREE from 'three';

export function createHoverProbe({ camera, planet, spin, uniforms, smoothing = 8 }) {
  const raycaster = new THREE.Raycaster();
  const sphere = new THREE.Sphere();
  const hit = new THREE.Vector3();
  const ndc = new THREE.Vector2();
  let strength = 0;

  return {
    update(pointer, delta) {
      let target = 0;

      if (pointer.inside) {
        ndc.set(pointer.x * 2, -pointer.y * 2);
        raycaster.setFromCamera(ndc, camera);

        planet.updateWorldMatrix(true, false);
        sphere.center.setFromMatrixPosition(planet.matrixWorld);
        sphere.radius = planet.scale.x;

        if (raycaster.ray.intersectSphere(sphere, hit)) {
          spin.updateWorldMatrix(true, false);
          spin.worldToLocal(hit);
          uniforms.uHover.value.copy(hit).normalize();
          target = 1;
        }
      }

      strength += (target - strength) * (1 - Math.exp(-smoothing * delta));
      uniforms.uHoverStrength.value = strength;
    },

    reset() {
      strength = 0;
      uniforms.uHoverStrength.value = 0;
    },
  };
}