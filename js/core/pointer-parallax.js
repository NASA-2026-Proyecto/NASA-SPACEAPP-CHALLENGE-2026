export function createPointerParallax({ smoothing = 3 } = {}) {
    const value = { x: 0, y: 0 };
    const pointer = { x: 0, y: 0, inside: false };
  
    function onPointerMove(event) {
      pointer.x = event.clientX / window.innerWidth - 0.5;
      pointer.y = event.clientY / window.innerHeight - 0.5;
      pointer.inside = true;
    }
  
    function onPointerLeave() {
      pointer.inside = false;
    }
  
    window.addEventListener('pointermove', onPointerMove, { passive: true });
    document.documentElement.addEventListener('pointerleave', onPointerLeave);
  
    return {
      value,
      pointer,
      update(delta) {
        const ease = 1 - Math.exp(-smoothing * delta);
        value.x += ((pointer.inside ? pointer.x : 0) - value.x) * ease;
        value.y += ((pointer.inside ? pointer.y : 0) - value.y) * ease;
      },
      destroy() {
        window.removeEventListener('pointermove', onPointerMove);
        document.documentElement.removeEventListener('pointerleave', onPointerLeave);
      },
    };
  }