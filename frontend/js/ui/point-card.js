// Tarjeta del punto seleccionado: se muestra en un popup del globo al hacer clic.
// Todo se escribe con textContent (nunca innerHTML): lo que llega de la API no se
// interpreta como HTML.
const number = new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
});

export function formatCoordinates({ lat, lon }) {
  const ns = lat >= 0 ? 'N' : 'S';
  const ew = lon >= 0 ? 'E' : 'O';
  return `${number.format(Math.abs(lat))}° ${ns} · ${number.format(Math.abs(lon))}° ${ew}`;
}

function paragraph(className, text = '') {
  const element = document.createElement('p');
  element.className = className;
  element.textContent = text;
  return element;
}

export function createPointCard() {
  const element = document.createElement('div');
  element.className = 'ej-point';
  // Mismo nodo en todos los clics: los lectores de pantalla anuncian cada cambio
  element.setAttribute('role', 'status');
  element.setAttribute('aria-live', 'polite');

  const coordinates = paragraph('ej-point__coords');
  const message = paragraph('ej-point__message');
  element.append(paragraph('ej-point__title', 'Punto seleccionado'), coordinates, message);

  function render(state, point, text) {
    element.dataset.state = state;
    coordinates.textContent = formatCoordinates(point);
    message.textContent = text;
  }

  return {
    element,
    pending: (point) => render('pending', point, 'Enviando a la API…'),
    success: (reply) => render('ok', reply, reply.message),
    error: (point, text) => render('error', point, text),
  };
}
