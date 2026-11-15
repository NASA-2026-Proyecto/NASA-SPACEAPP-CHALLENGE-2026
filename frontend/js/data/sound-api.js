// Sonidos de la API: qué suena en un punto (rápido, sin audio) y el clip que lo dice.
const BASE = 'api/sounds';
const BUSY_RETRIES = 3; // la API genera pocos sonidos a la vez: si está ocupada, se espera
const DEFAULT_RETRY_SECONDS = 2;

function httpError(response) {
  const error = new Error(`La API de sonidos respondió ${response.status}`);
  error.status = response.status;
  return error;
}

const wait = (seconds, signal) =>
  new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, seconds * 1000);
    signal?.addEventListener('abort', () => {
      clearTimeout(timer);
      reject(signal.reason);
    });
  });

// Lectura del punto: dato, descripción, parámetros y la ruta del audio (si suena algo)
export async function fetchSoundReading(soundId, { lat, lon }, signal) {
  const response = await fetch(`${BASE}/${soundId}?lat=${lat}&lon=${lon}`, { signal });
  if (!response.ok) throw httpError(response);
  return response.json();
}

// El clip (WAV) de una lectura, como ArrayBuffer
export async function fetchSoundClip(audioPath, signal) {
  for (let attempt = 0; ; attempt += 1) {
    const response = await fetch(`${BASE}/${audioPath}`, { signal });
    if (response.ok) return response.arrayBuffer();
    if (response.status !== 503 || attempt === BUSY_RETRIES) throw httpError(response);
    const seconds = Number(response.headers.get('Retry-After')) || DEFAULT_RETRY_SECONDS;
    await wait(seconds, signal);
  }
}
