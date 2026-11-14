import * as THREE from "three";
import { readCssToken } from "../../core/css-tokens.js";

const color = (name, fallback) => new THREE.Color(readCssToken(name, fallback));

export function loadGlobeTheme() {
  return {
    body: color("--ej-bg-mid", "#0b1426"),
    ocean: color("--ej-globe-ocean", "#061725"),
    land: color("--ej-globe-land", "#066fa8"),
    outline: color("--ej-globe-outline", "#75f3ef"),
    dot: color("--ej-globe-dot", "#7fb4ff"),
    rim: color("--ej-globe-rim", "#62c8ff"),
    highlight: color("--ej-globe-highlight", "#cfeaff"),
    atmosphere: color("--ej-globe-atmosphere", "#7fb4ff"),
    pulses: [
      color("--ej-fire", "#ff9857"),
      color("--ej-rain", "#62c8ff"),
      color("--ej-accent-strong", "#62c8ff"),
    ],
  };
}
