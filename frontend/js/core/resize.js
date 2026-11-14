// Sin retardo: se ejecuta como máximo una vez por fotograma.
// Con retardo: se ejecuta cuando el usuario deja de redimensionar.
export function watchResize(callback, delay = 0) {
    let frameId = null;
    let timerId = null;
  
    function onResize() {
      if (delay > 0) {
        clearTimeout(timerId);
        timerId = setTimeout(callback, delay);
        return;
      }
      if (frameId !== null) return;
      frameId = requestAnimationFrame(() => {
        frameId = null;
        callback();
      });
    }
  
    window.addEventListener('resize', onResize);
  
    return function stopWatching() {
      window.removeEventListener('resize', onResize);
      clearTimeout(timerId);
      if (frameId !== null) cancelAnimationFrame(frameId);
    };
  }