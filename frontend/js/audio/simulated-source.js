export function createSimulatedSource() {
    const t0 = performance.now();
  
    return {
      label: 'Simulado',
      getValue() {
        const t = (performance.now() - t0) / 1000;
        const v =
          0.5 +
          0.32 * Math.sin((2 * Math.PI * t) / 24) +
          0.14 * Math.sin((2 * Math.PI * t) / 9.7);
        return Math.min(1, Math.max(0, v));
      },
    };
  }