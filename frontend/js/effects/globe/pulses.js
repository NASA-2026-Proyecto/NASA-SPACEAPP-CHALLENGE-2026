import * as THREE from 'three';

const TAU = Math.PI * 2;
const Z_AXIS = new THREE.Vector3(0, 0, 1);
const MIN_SCALE = 0.012;
const MAX_SCALE = 0.17;
const PLAYHEAD_WINDOW = 0.14; // radianes alrededor del cabezal
const PICK_ATTEMPTS = 60;

function angularDistance(a, b) {
  return Math.abs((((a - b + Math.PI) % TAU) + TAU) % TAU - Math.PI);
}

export function createPulseSystem({ parent, positions, colors, count }) {
  const geometry = new THREE.RingGeometry(0.92, 1, 64);
  const normal = new THREE.Vector3();
  const pointCount = positions.length / 3;

  function pickIndex(playhead) {
    for (let attempt = 0; attempt < PICK_ATTEMPTS; attempt++) {
      const index = Math.floor(Math.random() * pointCount) * 3;
      const lon = Math.atan2(positions[index], positions[index + 2]);
      if (angularDistance(lon, playhead) < PLAYHEAD_WINDOW) return index;
    }
    return Math.floor(Math.random() * pointCount) * 3;
  }

  function schedule(pulse, delay) {
    pulse.age = -delay;
    pulse.duration = 3.4 + Math.random() * 1.8;
    pulse.placed = false;
    pulse.mesh.visible = false;
  }

  function place(pulse, playhead) {
    const index = pickIndex(playhead);
    normal.set(positions[index], positions[index + 1], positions[index + 2]).normalize();

    pulse.mesh.position.copy(normal).multiplyScalar(1.004);
    pulse.mesh.quaternion.setFromUnitVectors(Z_AXIS, normal);
    pulse.mesh.material.color.copy(colors[Math.floor(Math.random() * colors.length)]);
    pulse.placed = true;
  }

  const pulses = Array.from({ length: count }, (_, index) => {
    const material = new THREE.MeshBasicMaterial({
      transparent: true,
      opacity: 0,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
    });
    const mesh = new THREE.Mesh(geometry, material);
    parent.add(mesh);

    const pulse = { mesh, age: 0, duration: 4, placed: false };
    schedule(pulse, 0.8 + index * 0.7);
    return pulse;
  });

  return {
    update(delta, playhead) {
      for (const pulse of pulses) {
        pulse.age += delta;
        if (pulse.age < 0) continue;

        if (!pulse.placed) place(pulse, playhead);

        const t = pulse.age / pulse.duration;
        if (t >= 1) {
          schedule(pulse, 0.3 + Math.random() * 1.4);
          continue;
        }

        const eased = 1 - Math.pow(1 - t, 3);
        const fadeIn = Math.min(t / 0.08, 1);
        pulse.mesh.visible = true;
        pulse.mesh.scale.setScalar(MIN_SCALE + eased * (MAX_SCALE - MIN_SCALE));
        pulse.mesh.material.opacity = Math.pow(1 - t, 1.6) * fadeIn * 0.9;
      }
    },

    hideAll() {
      for (const pulse of pulses) pulse.mesh.visible = false;
    },

    dispose() {
      geometry.dispose();
      pulses.forEach((pulse) => pulse.mesh.material.dispose());
    },
  };
}