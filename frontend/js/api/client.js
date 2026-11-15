// Cliente de la API del backend (FastAPI).
//
// Las rutas son relativas al origen de la página: nginx (o la plataforma de despliegue)
// reenvía /api/* al backend. Así no hace falta CORS ni configurar la URL de la API.
const API_BASE = '/api';
const DEFAULT_TIMEOUT_MS = 8000;

export class ApiError extends Error {
  constructor(message, { status = 0, cause } = {}) {
    super(message, { cause });
    this.name = 'ApiError';
    this.status = status; // 0 = sin respuesta (red caída, tiempo agotado...)
  }
}

// FastAPI responde {detail: "texto"} o, si falla la validación, {detail: [{msg, ...}, ...]}
async function readErrorDetail(response) {
  try {
    const { detail } = await response.json();
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((item) => item.msg).join('; ');
  } catch {
    // Cuerpo vacío o no JSON (p. ej., la página de error de nginx si el backend está caído)
  }
  return response.statusText || 'error desconocido';
}

/**
 * GET a la API. Devuelve el JSON de la respuesta o lanza ApiError.
 * Si se cancela con `signal`, se relanza el error de cancelación tal cual:
 * quien llama lo reconoce mirando su propio `signal.aborted`.
 */
export async function apiGet(path, params = {}, { signal, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  const query = new URLSearchParams(Object.entries(params).map(([key, value]) => [key, String(value)]));
  const search = query.toString();
  const url = `${API_BASE}${path}${search ? `?${search}` : ''}`;

  const timeout = AbortSignal.timeout(timeoutMs);
  let response;
  try {
    response = await fetch(url, {
      headers: { Accept: 'application/json' },
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    if (timeout.aborted) throw new ApiError('La API no respondió a tiempo.', { cause: error });
    throw new ApiError('No se pudo conectar con la API.', { cause: error });
  }

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new ApiError(`Error ${response.status}: ${detail}`, { status: response.status });
  }

  try {
    return await response.json();
  } catch (error) {
    throw new ApiError('Respuesta inesperada de la API.', { status: response.status, cause: error });
  }
}

/** GET /api/point: confirma que el backend recibe unas coordenadas del globo. */
export function getPoint(lat, lon, options) {
  return apiGet('/point', { lat, lon }, options);
}
