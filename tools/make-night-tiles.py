#!/usr/bin/env python3
"""
Genera las teselas del modo noche a partir del mapa de luces nocturnas de la NASA.

Entrada : earth_nightlights_10K.tif  (equirrectangular, luces blancas sobre negro)
Salida  : assets/tiles/nightlights/{z}/{x}/{y}.webp  (Web Mercator, 512 px, con transparencia)

Uso (desde la raíz del proyecto):
    pip install pillow numpy
    python tools/make-night-tiles.py ruta/a/earth_nightlights_10K.tif

Solo hace falta volver a ejecutarlo si se cambia el mapa de origen o los colores.
"""
import math, os, sys
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
SRC = sys.argv[1] if len(sys.argv) > 1 else "earth_nightlights_10K.tif"
OUT = os.path.join("assets", "tiles", "nightlights")
TILE = 512          # tamaño de cada tesela (en el mapa: tileSize 512)
MAX_Z = 4           # zoom máximo de teselas (mundo de 8192 px)

# Color de las luces: ámbar suave -> blanco cálido en las zonas más intensas
LOW, HIGH = np.array([255, 150, 50]), np.array([255, 244, 205])

src = Image.open(SRC).convert("RGB")
lum = Image.fromarray(np.asarray(src).max(axis=2))      # intensidad de luz (0-255)
del src

def sample(arr, xs, ys):
    """Interpolación bilineal de arr (H, W) en coordenadas de píxel xs, ys."""
    h, w = arr.shape
    x0 = np.clip(np.floor(xs).astype(int), 0, w - 1); x1 = np.clip(x0 + 1, 0, w - 1)
    y0 = np.clip(np.floor(ys).astype(int), 0, h - 1); y1 = np.clip(y0 + 1, 0, h - 1)
    fx, fy = xs - np.floor(xs), ys - np.floor(ys)
    top = arr[y0, x0] * (1 - fx) + arr[y0, x1] * fx
    bot = arr[y1, x0] * (1 - fx) + arr[y1, x1] * fx
    return top * (1 - fy) + bot * fy

os.makedirs(OUT, exist_ok=True)
total = 0
for z in range(MAX_Z + 1):
    world = TILE * 2 ** z
    # Reducimos el origen según el zoom para no perder luces por submuestreo
    sw = min(lum.width, world * 2)
    level = lum if sw == lum.width else lum.resize((sw, sw // 2), Image.LANCZOS)
    arr = np.asarray(level, dtype=np.float32) / 255.0
    gain = max(1.0, (lum.width / (world * 2)) ** 0.5 * 1.1)   # compensa el brillo perdido
    n = 2 ** z
    cols = (np.arange(TILE) + 0.5)
    for ty in range(n):
        rows = ty * TILE + cols
        merc = math.pi * (1 - 2 * rows / world)
        lat = np.degrees(np.arctan(np.sinh(merc)))
        sy = (90 - lat) / 180 * arr.shape[0] - 0.5
        for tx in range(n):
            lon_px = tx * TILE + cols
            sx = lon_px / world * arr.shape[1] - 0.5
            xs, ys = np.meshgrid(sx, sy)
            v = np.clip(sample(arr, xs, ys) * gain, 0, 1)
            a = np.clip((v - 0.015) / 0.9, 0, 1) ** 0.65
            rgb = LOW + (HIGH - LOW) * (a[..., None] ** 1.3)
            rgba = np.dstack([rgb, a * 255]).astype(np.uint8)
            d = os.path.join(OUT, str(z), str(tx)); os.makedirs(d, exist_ok=True)
            Image.fromarray(rgba, "RGBA").save(
                os.path.join(d, f"{ty}.webp"), "WEBP", quality=80, alpha_quality=90, method=4)
            total += 1
    print(f"z{z}: {n * n} teselas")
print(f"Listo: {total} teselas en {OUT}")
