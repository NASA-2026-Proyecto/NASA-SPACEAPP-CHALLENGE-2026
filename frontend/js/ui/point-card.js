// Ficha del punto seleccionado: se muestra en un popup del globo al hacer clic.
// Enseña las dos fuentes por separado, cada una con su fecha:
//   - PM2.5 de la visualización diaria del EIC (cuánto),
//   - composición y tendencia del modelo casi en tiempo real (de qué y hacia dónde).
// Todo se escribe con textContent (nunca innerHTML).
const coordinate = new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
});
const percent = new Intl.NumberFormat('es-ES', { style: 'percent', maximumFractionDigits: 0 });
const signedPercent = new Intl.NumberFormat('es-ES', {
  style: 'percent',
  maximumFractionDigits: 0,
  signDisplay: 'always',
});
const stampFormat = new Intl.DateTimeFormat('es-ES', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'UTC',
});

const TREND_TEXT = { up: 'En aumento', down: 'En descenso', flat: 'Estable' };
const TREND_ARROW = { up: '↗', down: '↘', flat: '→' };

export function formatCoordinates({ lat, lon }) {
  const ns = lat >= 0 ? 'N' : 'S';
  const ew = lon >= 0 ? 'E' : 'O';
  return `${coordinate.format(Math.abs(lat))}° ${ns} · ${coordinate.format(Math.abs(lon))}° ${ew}`;
}

export const formatStamp = (stamp) =>
  `${stampFormat.format(new Date(stamp.replace('Z', ':00Z')))} UTC`;

// De 0,4 a 409,6: un decimal por debajo de 10, entero por encima.
export const formatPm25 = (value) =>
  new Intl.NumberFormat('es-ES', { maximumFractionDigits: value < 10 ? 1 : 0 }).format(value);

function node(tag, className, text = '') {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}

export function createPointCard() {
  const element = node('div', 'ej-point');
  // Mismo nodo en todos los clics: los lectores de pantalla anuncian cada cambio
  element.setAttribute('role', 'status');
  element.setAttribute('aria-live', 'polite');

  const coordinates = node('p', 'ej-point__coords');

  const pmValue = node('p', 'ej-point__value');
  const pmSource = node('p', 'ej-point__source');
  const pmSection = node('section', 'ej-point__section');
  pmSection.append(node('h3', 'ej-point__heading', 'Partículas PM2.5'), pmValue, pmSource);

  const mix = node('ul', 'ej-point__mix');
  const trend = node('p', 'ej-point__trend');
  const liveSource = node('p', 'ej-point__source');
  const liveSection = node('section', 'ej-point__section');
  liveSection.append(node('h3', 'ej-point__heading', 'Composición de los aerosoles'), mix, trend, liveSource);

  element.append(node('p', 'ej-point__title', 'Punto seleccionado'), coordinates, pmSection, liveSection);

  function renderPm25(pm25) {
    pmSection.dataset.state = pm25.status;
    if (pm25.status === 'ok') {
      pmValue.textContent = `${formatPm25(pm25.value)} µg/m³ · ${pm25.level}`;
    } else {
      pmValue.textContent = {
        loading: 'Cargando…',
        empty: 'Sin dato en este punto de la imagen de la NASA',
        error: 'No se pudo cargar',
      }[pm25.status];
    }
    pmSource.textContent = pm25.stamp
      ? `Visualización diaria del EIC · publicada el ${formatStamp(pm25.stamp)}`
      : 'Visualización diaria del EIC';
  }

  function renderLive(live) {
    liveSection.dataset.state = live.status;
    mix.replaceChildren();
    if (live.status === 'ok') {
      for (const item of live.species) {
        const row = node('li', 'ej-point__mix-row');
        const bar = node('span', 'ej-point__bar');
        bar.style.setProperty('--share', `${Math.round(item.share * 100)}%`);
        bar.style.setProperty('--species-color', item.color);
        row.append(node('span', 'ej-point__mix-label', item.label), bar, node('span', 'ej-point__mix-share', percent.format(item.share)));
        mix.append(row);
      }
      const { direction, change, hours } = live.trend;
      trend.textContent = `${TREND_ARROW[direction]} ${TREND_TEXT[direction]}: ${signedPercent.format(change)} en ${hours} h`;
    } else {
      trend.textContent = {
        loading: 'Cargando datos casi en tiempo real…',
        empty: 'Sin aerosoles apreciables en este punto',
        error: 'No se pudieron cargar los datos casi en tiempo real',
      }[live.status];
    }
    liveSource.textContent = live.stamp
      ? `Modelo GEOS-FP (espesor óptico) · dato del ${formatStamp(live.stamp)}`
      : 'Modelo GEOS-FP (espesor óptico)';
  }

  return {
    element,
    render(reading) {
      const settled = [reading.pm25.status, reading.live.status].every((status) => status !== 'loading');
      element.dataset.state = settled ? 'ready' : 'loading';
      coordinates.textContent = formatCoordinates(reading.point);
      renderPm25(reading.pm25);
      renderLive(reading.live);
    },
  };
}
