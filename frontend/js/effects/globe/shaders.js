export const SPHERE_VERTEX = `
  varying vec3 vNormal;
  varying vec3 vViewDir;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vNormal = normalize(normalMatrix * normal);
    vViewDir = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }
`;

export const BODY_FRAGMENT = `
  uniform vec3 uBase;
  uniform vec3 uRim;
  varying vec3 vNormal;
  varying vec3 vViewDir;
  void main() {
    float f = pow(1.0 - max(dot(normalize(vNormal), normalize(vViewDir)), 0.0), 2.5);
    gl_FragColor = vec4(mix(uBase, uRim, f * 0.22), 1.0);
  }
`;

// Halo: máximo junto al borde del planeta y se apaga hacia fuera
export const GLOW_FRAGMENT = `
  uniform vec3 uColor;
  uniform float uIntensity;
  uniform float uFalloff;
  varying vec3 vNormal;
  varying vec3 vViewDir;
  void main() {
    float edge = clamp(-dot(normalize(vNormal), normalize(vViewDir)), 0.0, 1.0);
    float glow = pow(smoothstep(0.0, 0.5, edge), uFalloff) * uIntensity;
    gl_FragColor = vec4(uColor * glow, glow);
  }
`;

export const DOT_VERTEX = `
  uniform float uSize;
  uniform vec3 uHover;
  uniform float uHoverStrength;
  uniform float uPlayhead;
  uniform float uPlayheadStrength;
  varying float vFacing;
  varying float vHighlight;

  const float PI = 3.14159265359;
  const float TAU = 6.28318530718;

  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vec3 dir = normalize(position);
    vec3 n = normalize(normalMatrix * dir);
    vFacing = clamp(dot(n, normalize(-mv.xyz)), 0.0, 1.0);

    // Zona iluminada alrededor del puntero
    float hover = smoothstep(0.42, 0.0, distance(dir, uHover)) * uHoverStrength;

    // Cabezal de lectura: franja de longitud que recorre el planeta
    float lon = atan(dir.x, dir.z);
    float delta = abs(mod(lon - uPlayhead + PI, TAU) - PI);
    float playhead = smoothstep(0.22, 0.0, delta) * uPlayheadStrength;

    vHighlight = clamp(hover + playhead * 0.8, 0.0, 1.0);
    gl_PointSize = max(uSize * (1.0 + vHighlight * 0.8) / -mv.z, 1.0);
    gl_Position = projectionMatrix * mv;
  }
`;

export const DOT_FRAGMENT = `
  uniform vec3 uColor;
  uniform vec3 uRim;
  uniform vec3 uAccent;
  varying float vFacing;
  varying float vHighlight;

  void main() {
    float d = length(gl_PointCoord - 0.5);
    float alpha = smoothstep(0.5, 0.25, d);
    float rim = pow(1.0 - vFacing, 2.0);
    vec3 color = mix(uColor, uRim, rim);
    color = mix(color, uAccent, vHighlight);
    float brightness = clamp(0.55 + 0.45 * vFacing + 0.25 * rim + 0.5 * vHighlight, 0.0, 1.0);
    gl_FragColor = vec4(color, alpha * brightness);
  }
`;

// ---------------------------------------------------------------------------
// SUPERFICIE HOLOGRÁFICA (continentes luminosos). Todo lo de arriba queda igual.
// ---------------------------------------------------------------------------
export const LAND_VERTEX = `
  varying vec3 vPos;
  varying vec3 vNormal;
  varying vec3 vViewDir;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vPos = position;
    vNormal = normalize(normalMatrix * normal);
    vViewDir = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }
`;

export const LAND_FRAGMENT = `
  uniform sampler2D uLandMask;
  uniform float uLandIsDark;
  uniform vec2 uTexel;
  uniform vec3 uOcean;
  uniform vec3 uLand;
  uniform vec3 uOutline;
  uniform vec3 uAtmosphere;
  uniform float uGrid;
  uniform float uSparkle;

  varying vec3 vPos;
  varying vec3 vNormal;
  varying vec3 vViewDir;

  const float PI = 3.14159265359;
  const float TAU = 6.28318530718;

  // Posición 3D -> coordenadas de la imagen (misma convención que land-mask.js)
  vec2 toUv(vec3 p) {
    float lon = atan(p.x, p.z);
    float lat = asin(clamp(p.y, -1.0, 1.0));
    return vec2((lon + PI) / TAU, lat / PI + 0.5);
  }

  float readLand(vec2 uv) {
    float v = texture2D(uLandMask, vec2(fract(uv.x), clamp(uv.y, 0.0, 1.0))).r;
    float land = uLandIsDark > 0.5 ? 1.0 - v : v;
    return smoothstep(0.35, 0.65, land);
  }

  float hash(vec3 p) {
    p = fract(p * 0.3183099 + 0.1);
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
  }

  float noise(vec3 x) {
    vec3 i = floor(x);
    vec3 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(mix(hash(i), hash(i + vec3(1, 0, 0)), f.x),
          mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x), f.y),
      mix(mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x),
          mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x), f.y),
      f.z);
  }

  void main() {
    vec3 p = normalize(vPos);
    vec2 uv = toUv(p);
    float land = readLand(uv);

    // Borde: diferencia con los vecinos inmediatos
    vec2 e = uTexel * 0.5;
    float edge = max(
      max(abs(land - readLand(uv - vec2(e.x, 0.0))), abs(land - readLand(uv + vec2(e.x, 0.0)))),
      max(abs(land - readLand(uv - vec2(0.0, e.y))), abs(land - readLand(uv + vec2(0.0, e.y))))
    );
    float outline = smoothstep(0.05, 0.5, edge);

    // Resplandor cerca de la costa (mide cuánta tierra hay alrededor)
    vec2 w = uTexel * 5.0;
    float around = 0.25 * (
      readLand(uv + vec2(w.x, 0.0)) + readLand(uv - vec2(w.x, 0.0)) +
      readLand(uv + vec2(0.0, w.y)) + readLand(uv - vec2(0.0, w.y))
    );
    float coastInside = land * (1.0 - around);
    float coastOutside = (1.0 - land) * around;

    // Borde del planeta
    float facing = max(dot(normalize(vNormal), normalize(vViewDir)), 0.0);
    float rim = pow(1.0 - facing, 2.0);

    // Textura de la tierra: manchas suaves + destellos tipo "luces de ciudad"
    float soft = noise(p * 14.0) * 0.6 + noise(p * 40.0) * 0.4;
    float spark = smoothstep(0.80, 0.97, noise(p * 150.0));

    // Rejilla de meridianos y paralelos cada 15 grados
    vec2 deg = vec2(degrees(atan(p.x, p.z)), degrees(asin(clamp(p.y, -1.0, 1.0))));
    vec2 g = abs(fract(deg / 15.0 + 0.5) - 0.5) * 15.0;
    float grid = 1.0 - smoothstep(0.0, 0.35, min(g.x * cos(radians(deg.y)), g.y));

    vec3 ocean = uOcean * (0.65 + rim * 0.35);
    vec3 earth = uLand * (0.55 + soft * 0.9) * (0.75 + rim * 0.25);

    vec3 color = mix(ocean, earth, land);
    color += uOutline * coastInside * 0.35;
    color += uAtmosphere * coastOutside * 0.18;
    color = mix(color, uOutline, outline * 0.9);
    color += uOutline * spark * land * uSparkle;
    color += uAtmosphere * grid * uGrid;
    color += uAtmosphere * rim * 0.25;

    gl_FragColor = vec4(color, 1.0);
  }
`;