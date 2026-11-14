export function createGlobeStatus({ container, textElement }) {
    return {
      setReady() {
        container.classList.add('globe--ready');
      },
      setError(message) {
        textElement.textContent = message;
        container.classList.add('globe--error');
      },
    };
  }