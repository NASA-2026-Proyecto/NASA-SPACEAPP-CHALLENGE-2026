// Ficha del punto seleccionado: va dentro del panel "Punto seleccionado", debajo del sonido
// (las coordenadas, arriba del todo). Enseña los datos de la capa activa, cada fuente en su
// bloque y con su fecha:
//   - Aerosoles: PM2.5 de la visualización diaria del EIC (cuánto) y composición y tendencia
//     del modelo casi en tiempo real (de qué y hacia dónde).
//   - Incendios: el más fuerte junto al punto y su evolución día a día.
//   - Precipitación: lluvia y nieve en el punto y su evolución.
// Las partes de la lectura (js/data/point-reading.js) deciden qué bloques se ven.
// Todo se escribe con textContent (nunca innerHTML).
import { findScene } from '../catalog/scenes.js';

const coordinate = new Intl.NumberFormat('es-ES', {
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
});
const oneDecimal = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1 });
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
const dayFormat = new Intl.DateTimeFormat('es-ES', { day: 'numeric', month: 'short', timeZone: 'UTC' });
const hourFormat = new Intl.DateTimeFormat('es-ES', {
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'UTC',
});

const TREND_TEXT = { up: 'En aumento', down: 'En descenso', flat: 'Estable' };
const TREND_ARROW = { up: '↗', down: '↘', flat: '→' };
const WAITING = { loading: 'Cargando…', error: 'No se pudo cargar' };

const toDate = (stamp) => new Date(stamp.replace('Z', ':00Z'));

function formatCoordinates({ lat, lon }) {
  const ns = lat >= 0 ? 'N' : 'S';
  const ew = lon >= 0 ? 'E' : 'O';
  return `${coordinate.format(Math.abs(lat))}° ${ns} · ${coordinate.format(Math.abs(lon))}° ${ew}`;
}

const formatStamp = (stamp) => `${stampFormat.format(toDate(stamp))} UTC`;

// De 0,4 a 409,6: un decimal por debajo de 10, entero por encima.
const formatPm25 = (value) =>
  new Intl.NumberFormat('es-ES', { maximumFractionDigits: value < 10 ? 1 : 0 }).format(value);

function node(tag, className, text = '') {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}

// Bloque de una fuente: título, valor principal, lo que cada bloque añada y la fuente con su fecha
function section(title, sceneId, ...middle) {
  const scene = findScene(sceneId);
  const element = node('section', 'ej-point__section');
  const value = node('p', 'ej-point__value');
  const source = node('p', 'ej-point__source');
  element.append(node('h3', 'ej-point__heading', title), value, ...middle, source);
  return {
    element,
    value,
    // Deja el bloque en el estado de la parte; devuelve true si aún no hay nada que enseñar
    settle(part) {
      element.dataset.state = part.status;
      source.textContent = part.stamp
        ? `${scene.source} · ${scene.stampLabel} ${formatStamp(part.stamp)}`
        : scene.source;
      if (part.status in WAITING) value.textContent = WAITING[part.status];
      return part.status in WAITING;
    },
  };
}

// Una fila con barra: rótulo, barra (posición 0..1) y cifra
function barRow(label, position, color, figure, className = 'ej-point__mix-row') {
  const row = node('li', className);
  const bar = node('span', 'ej-point__bar');
  bar.style.setProperty('--share', `${Math.round(position * 100)}%`);
  bar.style.setProperty('--species-color', color);
  row.append(node('span', 'ej-point__mix-label', label), bar, node('span', 'ej-point__mix-share', figure));
  return row;
}

function pm25Section() {
  const block = section('Partículas PM2.5', 'pm25-latest');
  return {
    element: block.element,
    render(pm25) {
      if (block.settle(pm25)) return;
      block.value.textContent =
        pm25.status === 'ok'
          ? `${formatPm25(pm25.value)} µg/m³ · ${pm25.level}`
          : 'Sin dato en este punto de la imagen de la NASA';
    },
  };
}

function mixSection() {
  const mix = node('ul', 'ej-point__mix');
  const trend = node('p', 'ej-point__trend');
  const block = section('Composición de los aerosoles', 'aerosol-latest', mix, trend);
  return {
    element: block.element,
    render(live) {
      mix.replaceChildren();
      trend.textContent = '';
      if (block.settle(live)) return;
      block.value.textContent = live.status === 'ok' ? '' : 'Sin aerosoles apreciables en este punto';
      if (live.status !== 'ok') return;
      for (const item of live.species) {
        mix.append(barRow(item.label, item.share, item.color, percent.format(item.share)));
      }
      const { direction, change, hours } = live.trend;
      trend.textContent = `${TREND_ARROW[direction]} ${TREND_TEXT[direction]}: ${signedPercent.format(change)} en ${hours} h`;
    },
  };
}

// Bloque con una serie: un valor por paso de la escena, del más antiguo al más reciente
function seriesSection(title, sceneId, speciesId) {
  const detail = node('p', 'ej-point__trend');
  const caption = node('p', 'ej-point__caption');
  const list = node('ul', 'ej-point__mix');
  const block = section(title, sceneId, detail, caption, list);
  const { color } = findScene(sceneId).species.find((species) => species.id === speciesId);
  return {
    block,
    detail,
    color,
    // rows: [{ label, position, figure, color? }]
    showSeries(text, rows) {
      caption.textContent = rows.length ? text : '';
      list.replaceChildren(
        ...rows.map((row) =>
          barRow(row.label, row.position, row.color ?? color, row.figure, 'ej-point__mix-row ej-point__series-row')
        )
      );
    },
  };
}

function fireSection() {
  const { block, detail, showSeries } = seriesSection('Incendios activos', 'fires-latest', 'frp');
  return {
    element: block.element,
    render(fires) {
      detail.textContent = '';
      showSeries('', []);
      if (block.settle(fires)) return;
      if (fires.status === 'ok') {
        block.value.textContent = `${oneDecimal.format(fires.value)} MW · el más fuerte junto al punto`;
        detail.textContent = `Hay fuego en ${fires.burning} de las ${fires.cells} celdas de alrededor`;
      } else {
        block.value.textContent = 'Sin incendios activos junto a este punto';
      }
      // La evolución se enseña también si hoy no hay fuego pero lo hubo algún día de la serie
      if (fires.series.some((day) => day.value > 0)) {
        showSeries(
          'El más fuerte de cada día',
          fires.series.map((day) => ({
            label: dayFormat.format(toDate(day.stamp)),
            position: day.position,
            figure: day.value > 0 ? `${oneDecimal.format(day.value)} MW` : '—',
          }))
        );
      }
    },
  };
}

function rainSection() {
  const { block, detail, color, showSeries } = seriesSection('Precipitación', 'precipitation-latest', 'rain');
  const snowColor = findScene('precipitation-latest').species.find((species) => species.id === 'snow').color;
  const amount = (value) => `${oneDecimal.format(value)} mm/h`;
  return {
    element: block.element,
    render(precipitation) {
      detail.textContent = '';
      showSeries('', []);
      if (block.settle(precipitation)) return;
      const { rain, snow, category } = precipitation;
      if (precipitation.status === 'ok') {
        block.value.textContent = category ? `${amount(rain)} · ${category}` : `Nieve: ${amount(snow)}`;
        if (category && precipitation.snowing) detail.textContent = `Y nieve: ${amount(snow)}`;
      } else {
        block.value.textContent = 'Seco: ni llueve ni nieva en este punto';
      }
      if (precipitation.series.some((step) => step.wet)) {
        showSeries(
          'Lluvia y nieve en cada paso de la serie (día y hora UTC)',
          precipitation.series.map((step) => ({
            label: hourFormat.format(toDate(step.stamp)),
            position: step.position,
            color: step.snow > step.rain ? snowColor : color,
            figure: step.wet ? amount(step.value) : '—',
          }))
        );
      }
    },
  };
}

// Un bloque por cada parte que puede traer una lectura (ver LAYER_READERS)
const SECTIONS = {
  pm25: pm25Section,
  live: mixSection,
  fires: fireSection,
  precipitation: rainSection,
};

export function createPointCard() {
  const element = node('div', 'ej-point');
  // Mismo nodo en todos los clics: los lectores de pantalla anuncian cada cambio
  element.setAttribute('role', 'status');
  element.setAttribute('aria-live', 'polite');

  const coordinates = node('p', 'ej-point__coords');
  const sections = Object.entries(SECTIONS).map(([key, build]) => ({ key, ...build() }));
  element.append(...sections.map((item) => item.element));

  return {
    element,
    coordinates,
    // Enseña los bloques de las partes que trae la lectura y oculta los demás
    render(reading) {
      const settled = Object.values(reading.parts).every((part) => part.status !== 'loading');
      element.dataset.state = settled ? 'ready' : 'loading';
      coordinates.textContent = formatCoordinates(reading.point);
      for (const item of sections) {
        const part = reading.parts[item.key];
        item.element.hidden = !part;
        if (part) item.render(part);
      }
    },
  };
}
