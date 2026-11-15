# CLAUDE.md: Earth Jukebox

Context for AI coding sessions. Read this before exploring the code; open source files only when this file doesn't answer the question. Keep it updated when architecture or conventions change.

## Project

- **Earth Jukebox**, for the NASA Space Apps Challenge 2026: a 3D globe that turns NASA Earth observation data into sound (sonification), for accessibility (blind and low-vision users). See [README.md](README.md) for the pitch.
- Hackathon goal: the team is aiming for the award for **most plausible concept and design**, so architecture quality, clean structure and a credible path to scale matter as much as features. Avoid overbuilding: no DB, queue or cache server unless asked.
- The UI and code comments are in **Spanish**. Keep that for UI text, API `message`s and comments. Docs (README, this file) are in English.
- Local-only for now. Hosting candidates: Vercel (can run FastAPI from `pyproject.toml` + `uv.lock`) or any container host. **Supabase cannot host the Python API** (Edge Functions are TypeScript/Deno only).

## Working rules (from the user)

- **Never commit, push, pull, merge or tag** unless the user asks in that message. Work on feature branches, not `main`.
- Analysis requests are read-only. For bigger tasks, propose a plan and wait for approval.
- Python tooling is **uv** (never pip or requirements.txt). Prefer a tidy structure and clean code.
- Before claiming a library feature exists, check the version pinned here (lockfile, CDN URL).
- A permission rule blocks Claude from reading or writing `.env*` files (including `.env.example`). Ask the user to edit them.

## Layout

```
frontend/                 Static site = nginx web root (relative paths everywhere)
  index.html              Landing page: Three.js dotted globe (js/pages/landing.js)
  explorer.html           Main app: MapLibre globe (js/pages/explorer.js)
  css/                    tokens.css (design tokens), base, components, landing, explorer, explorer-shell (panels, popup)
  js/
    config.js             Layer catalog (LAYERS): id, label, ramp, paint. `source` = GIBS raster, `kind: 'scene'` + `sceneId` = data scene. Neither = "Pendiente"
    catalog/scenes.js     Scene catalog (SCENES): id, dataUrl (static folder or API), species (id, label, color), `live`
    data/scene-data.js    loadScene(baseUrl) (manifest + .f32, checks size and sha256), sampleAt() (interpolated, for sound), cellValueAt() (exact cell, for the popup), createResampler()
    core/layers.js        isSceneLayer(), isLayerAvailable()
    api/client.js         apiGet()/getPoint(): fetch to relative /api, ApiError, 8 s timeout, AbortSignal (currently unused)
    data/scene-cache.js   getScene(sceneId): one shared download per scene
    data/point-reading.js readPm25(), readAerosols(), levelOf(): the reading of a clicked point
    pages/                Page entry points (landing.js, explorer.js); explorer.js wires the UI and the click → /api/point flow
    map/                  globe-map.js (createGlobeMap → {map, flyTo, isOnGlobe, showPopup, destroy}), series-layer.js (scene → canvas → raster layer), gibs.js,
                          night-lights.js, land-dots.js, hover-glow.js, auto-spin.js
    ui/                   layer-panel, player (audio UI), waveform, point-card (click popup), mode-toggle, dialog, icons, globe-status
    audio/                audio-engine.js (Web Audio: value 0..1 → 110 Hz × 2^(3v), level), simulated-source.js
    state/                store.js (tiny pub/sub store), app-store.js (layers, opacity, nightMode, species, sceneStep, scenePlaying)
    effects/              starfield.js, dotted-globe.js + globe/* (Three.js landing globe and shaders)
    core/                 animation-loop, motion (reduced motion), resize, pointer-parallax, css-tokens
  assets/                 fonts (woff2), images/earth-water.png (land mask), tiles/nightlights/{z}/{x}/{y}.webp (z0–4, 341 tiles)
  nginx/                  default.conf.template + dev.conf / prod.conf (included as /etc/nginx/snippets/mode.conf)
  Dockerfile  .dockerignore
backend/                  uv project (package = false: an app, run from backend/)
  app/main.py             create_app(settings) factory + module-level `app` (also Vercel's entrypoint)
  app/config.py           Settings (pydantic-settings, env vars only): cors_origins, scene_steps, scene_warmup
  app/schemas.py          Health, PointResponse
  app/api/__init__.py     router with prefix /api; includes health, point, scenes
  app/api/params.py       Shared Lat/Lon Query types (ge/le validation → 422)
  app/api/health.py       GET /api/health → {status, version}
  app/api/point.py        GET /api/point?lat&lon → {ok, lat, lon, message}
  app/api/scenes.py       GET /api/scenes (list), /api/scenes/{scene_id}/manifest.json (503 while building) and /{scene_id}/{version}/{species}.f32
  app/services/scenes.py  Scene, SceneSource protocol (check() → version, build()), SceneStore (in-memory, background refresh, keeps previous version), manifest helpers
  app/services/http.py    http_get with retries (urllib)
  app/services/geosfp.py  GEOS-FP OPeNDAP client (urllib + numpy): parse_das, parse_dods, GeosFpClient
  app/services/aerosol_scene.py  AerosolSource → scene `aerosol-latest` (GEOS-FP, 5 species, last SCENE_STEPS steps)
  app/services/svs.py     SVS client: page JSON (`/api/{id}`), frame listing, downloads
  app/services/colour_scale.py   Colour → value: read a colour bar, invert it on an image, reject thin lines, drop islands, downsample, fill small gaps (numpy + Pillow)
  app/services/pm25_scene.py     Pm25Source → scene `pm25-latest` (EIC daily visualization SVS 5151)
  app/services/exr.py            read_rgb(bytes): OpenEXR frame → linear float32 RGB
  app/services/fire_scene.py     FireSource → scene `fires-latest` (EIC daily visualization SVS 5113)
  geosfp/  tools/         Alex's OFFLINE pipeline (xarray + pydap): download episodes, build static scenes. Not imported by app/. Run: `uv run --group pipeline python -m tools.<script>`
  tests/                  conftest (client fixture with explicit Settings and a fake NASA), fakes.py (FakeGeosFp), fake_svs.py (FakeSvs with a synthetic frame and colour bar), test_app.py, test_point.py, test_scenes.py, test_pm25_scene.py
  pyproject.toml  uv.lock  .python-version (3.13)  Dockerfile  .dockerignore
tools/make-night-tiles.py PEP 723 script: `uv run tools/make-night-tiles.py <earth_nightlights_10K.tif>` → frontend/assets/tiles/nightlights
compose.yaml              Production-like: backend (prod) + frontend (prod), only 127.0.0.1:${FRONTEND_PORT:-8080} published
compose.dev.yaml          Overrides: dev targets, repo bind-mounted at /workspace, read-only frontend file mounts, 127.0.0.1:8000 for the API
.devcontainer/            devcontainer.json + compose.devcontainer.yaml (resets published ports; VS Code forwards them)
.vscode/                  launch.json (API: FastAPI, API: tests, Frontend: Chrome, Full stack), extensions.json
```

## Architecture

- **Two images, one origin.** nginx (frontend) serves static files and reverse-proxies `/api/*` to `backend:8000`. The frontend only uses **relative `/api` URLs**, so there is no CORS and no API URL config in JS. The backend never serves frontend files. Keep it that way: it is what makes the design portable (Compose, Vercel rewrites, any reverse proxy).
- **Backend is stateless**; all config comes from env vars (no `.env` lookup inside the app; Compose injects them, or `uv run --env-file ../.env`). An in-memory cache is fine only as an optimization, because serverless instances don't keep memory.
- All API routes live under `/api` (including `/api/docs` and `/api/openapi.json`; ReDoc is disabled), because nginx only forwards `/api/`.
- CORS middleware is added **only** if `CORS_ORIGINS` is non-empty.
- Frontend has **no build step**: plain ES modules. Three.js comes from an importmap (jsdelivr `three@0.186.0`). MapLibre is imported by URL (`https://unpkg.com/maplibre-gl@6.16.0/dist/maplibre-gl.mjs`; it spawns its worker from unpkg via a `blob:` URL, which matters for any future CSP). Bootstrap 5.3.8 CSS comes from jsdelivr with SRI.
- External runtime services (no keys): OpenFreeMap style `https://tiles.openfreemap.org/styles/dark` (unversioned), NASA GIBS WMTS (Blue Marble basemap, layer tiles), CDNs. All send CORS `*`.
- Globe layer order (bottom → top): GIBS Blue Marble basemap → night lights (local tiles) → NASA data layers from config.js → land dots (GeoJSON from earth-water.png) → labels. OpenFreeMap vector layers are hidden except place, water_name and boundary.
- State: `app-store.js` holds `{layers, opacity, nightMode, selectedMarker, species, sceneStep, scenePlaying}`; UI modules subscribe and re-render. No framework.

### Data scenes (the common data format)

A **scene** is how gridded data reaches the browser, whatever its source. It was designed by Alex (`backend/tools/build_scene.py`) and is the contract between backend and frontend:

- `manifest.json` (`schema_version: 2`, `kind: "grid-series"`): `time.stamps_utc`, `grid` (`lat_min`, `lat_step`, `lon_min`, `lon_step`, `n_lat`, `n_lon`, `lon_periodic`), and per species `file`, `sha256`, `min`, `max`, `display_scale_max`.
- One `.f32` per species: float32 little-endian, order `[step][lat][lon]`, south to north, west to east.

There are two scenes, both built by the backend at runtime and wired in `app/main.py default_scenes()`:

- `pm25-latest`, the **field**: the newest frame of the EIC daily visualization PM2.5 (SVS 5151, GEOS-CF). Colours are converted back to µg/m³ with the page's colour bar (log scale 0.4–409.6), 2×2 pixel blocks are averaged to a 512 × 256 grid, coastlines and borders are removed by shape (bright features under 3 px) and filled, and the logo and date boxes stay NaN. Eight steps 3 hours apart; the last stamp is NASA's publication time (the spacing between steps is exact, the absolute hour is not, because each frame's own hour is only printed on the image). The manifest carries `scale: {kind: "log", min, max, ramp}` with NASA's ramp colours, and `series-layer.js` paints it with that ramp (transparent in clean air).
- `aerosol-latest`, the **probe** source: GEOS-FP species, described next.
- `fires-latest`: the EIC daily visualization of VIIRS active fires (SVS 5113), species `frp` in MW. It uses the equirectangular "SoaS" frames (EXR, 4096 × 2048, about 6.5 MB each, one per day; each shows a 5-day moving window). `frp_from_rgb()` maps the linear red channel to fire radiative power with the colour bar read once from the frame legend (constants in `fire_scene.py`; background red ≤ 0.02, fires > 0.2), and each grid cell keeps the strongest fire of its 8 × 8 pixel block (512 × 256 grid, `scale: {kind: "linear", min: 0, max: 8, ramp}`). **The newest frames arrive empty or half-filled**, so the source downloads `steps + 5` frames and drops trailing ones with fewer than 0.6× the median fire-pixel count (on 15 Nov 2026 it skipped 4 and used 2–9 Nov). The version is the `Last-Modified` of the newest frame (a HEAD request), because the page's `update_date` does not change with the daily render. Frame dates are inferred: newest published frame = render date − 1 day, one frame per day (checked against the dated version for the last frames). Each rebuild downloads about 85 MB from NASA, once a day. The "Incendios" layer has a single button ("EIC Incendios"); fires are not yet in the point card or the sound.

In the panel the Aerosoles layer has one button per species across both scenes (`config.js`: `scenes`, each species tagged with its `sceneId`); **PM2.5 is first and the default**. A scene is fetched the first time one of its species is selected with the layer on, and each scene gets its own map layer (`aerosol-<sceneId>`). The panel note shows the source and date of what is on screen (`sceneInfo` in the store).

Flow for the live aerosol scene (`aerosol-latest`):

1. Backend `SceneStore` asks GEOS-FP for its time axis (`.das`); if there is a newer 3-hour step it fetches each species for the last `SCENE_STEPS` steps on a 1° × 1.25° global grid (one `.dods` request per species, about 3 s each) and builds the scene in memory. It rechecks every 15 min, retries after 30 s on failure, and keeps serving the last good scene.
2. `.f32` URLs include the scene version (`…/20261114T1330Z/dust.f32`), so they are immutable and cacheable; the previous version stays available.
3. Frontend loads the scene the first time the layer is switched on (`globe-map.js loadScenesOnDemand`, retry every 5 s on 503), `series-layer.js` paints it to an off-screen canvas re-projected to Web Mercator (alpha grows with the value) and adds it as a MapLibre `canvas` source. For `live` scenes the newest step is shown.
4. Sound and popup are meant to read values locally with `sampleAt()` / `cellValueAt()`: no server round trip per click.

Rules: do not commit scene data to git (it is built at runtime, or by the offline tools into git-ignored `data/`). New gridded sources should become new scenes in this same format, not new formats.

### Click → reading → popup and sound (explorer)

No server round trip per click: values are read locally from the scenes.

`explorer.js initPointProbe(globe)`, on `map.on('click')`:
1. ignores the click if `!globe.isOnGlobe(event)`; calls `event.lngLat.wrap()`; rounds to 5 decimals;
2. builds a **reading** (`data/point-reading.js`): `{point, pm25: {status, value, position, level, stamp}, live: {status, species[{id,label,color,value,share}], total, trend{direction, change, hours}, stamp}}`, with both parts `loading`;
3. asks `data/scene-cache.js getScene()` for `pm25-latest` and `aerosol-latest` (one shared download per scene, also used by the map layers; a failed request is not cached, so the next click retries). Each part fills in on its own: if one source fails the other still shows;
4. on every update renders the popup card (`ui/point-card.js`, `textContent` only) and stores the reading with `setReading()`; a later click wins (`latest` guard).

Roles are fixed: **PM2.5 from the EIC visualization says how much** (µg/m³, plus a level word from its position on NASA's log scale: it is relative to that scale, not an air-quality index); **GEOS-FP says what it is made of** (share of each species' optical depth at the newest step) **and where it is going** (change of the 5-species total over the available steps; beyond ±10% is "en aumento"/"en descenso").

Sound (`ui/player.js` + `audio/audio-engine.js`): the player follows `state.reading`. One datum drives one parameter:

| Data | Source | Sound parameter |
|---|---|---|
| PM2.5 position on NASA's scale (0..1) | EIC scene | pitch (110 Hz × 2^(3v)) and level |
| species shares | GEOS-FP scene | timbre: gain of one voice per species (sea salt = pure sine, sulfate = bright, brown carbon = hollow/odd harmonics, black carbon = rough, dust = beating pair) |
| trend direction | GEOS-FP scene | a three-note cue (rising, falling or repeated) when the data for a point arrives or playback starts |

Without live data a neutral voice plays (plainer but still correct). Until the first click, or where the EIC image has no data (NaN under NASA's logo and date boxes), the simulated demo signal plays and the top chip reads "Modo demostración" instead of "Datos de la NASA". The card is shown in the corner panel described below.

`GET /api/point` still exists (echoes coordinates) but the frontend no longer calls it; `api/client.js` is unused for now.

### Animation and the point card

- **Both scenes are series of `SCENE_STEPS` steps (default 8) spaced 3 hours**, so each covers the last 21 hours: GEOS-FP's last 8 steps, and for PM2.5 one hourly frame out of every 3, ending at the newest (`Pm25Source(steps, frame_spacing=3, factor=4)` → 512 × 256 grid, about 4 MB; the aerosol scene is about 8 MB).
- `map/scene-animation.js` is a clock that loops 0 → 1 in 9 s, holds 2.2 s on the newest step and restarts (20 fps). `globe-map.js` runs it while `state.scenePlaying` is true and a scene layer is visible, and calls `series.setProgress(p)` on every layer directly; the store only gets `sceneProgress` in 24 coarse ticks, for the panel label. Pausing returns to the newest step. `scenePlaying` starts false when the user prefers reduced motion.
- `series-layer.js` paints each step once into its own canvas (cache per species) and cross-fades the two neighbouring steps with canvas compositing (`lighter` with weights), so a frame of animation costs two `drawImage` calls, not a per-pixel loop.
- The panel shows a pause/play button and a label ("Últimas 21 h · 8 h antes"); it has no `aria-live` because it changes several times per second.
- **The point card is not a map popup.** It lives in a fixed panel in the bottom-right corner (`.ej-point-dock`, created in `explorer.js`) so it never covers the globe; the clicked point gets a `maplibregl.Marker` (`globe.showMarker()` / `hideMarker()`). The card and the sound always describe the newest step, whatever the animation is showing; the trend covers all the steps of the scene.

## Docker

- **backend/Dockerfile** stages:
  - `uv` (ghcr.io/astral-sh/uv:0.11.8);
  - `base` (python:3.13-slim-trixie + uv, `UV_PYTHON_DOWNLOADS=0`, `UV_LINK_MODE=copy`);
  - `builder` (`uv sync --locked --no-install-project --no-dev` with cache/bind mounts);
  - **`prod`**: copies only `/app/.venv` and `app/`, user `app` (uid 10001), HEALTHCHECK via Python urllib, CMD `uvicorn … --port $PORT --log-level $LOG_LEVEL --proxy-headers --forwarded-allow-ips='*'`;
  - **`dev`**: git/curl/procps, user `vscode` (uid 1000), venv at **`/opt/venv`** (`UV_PROJECT_ENVIRONMENT`, outside the bind mount), `UV_COMPILE_BYTECODE=0`, CMD `uvicorn --reload --reload-dir app`.
- **frontend/Dockerfile**: `nginxinc/nginx-unprivileged:1.30.5-alpine` (uid 101, port 8080). `ENV BACKEND_URL`, `NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1`. The template goes to `/etc/nginx/templates/`, and the entrypoint's envsubst only substitutes *defined* env vars. The `dev` target uses dev.conf (no-store, sendfile off); the `prod` target uses prod.conf and copies index.html, explorer.html, css, js and assets explicitly.
- Images: backend prod ~327 MB (numpy), dev ~519 MB before numpy; frontend prod ~107 MB.

## Commands

```bash
# Backend (host, from backend/)
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run --env-file ../.env uvicorn app.main:app --reload

# Stacks (from repo root)
docker compose up --build -d                                       # prod-like → http://localhost:8080
docker compose -f compose.yaml -f compose.dev.yaml up -d --build   # dev → :8080 (nginx) and :8000 (API)
docker compose -f compose.yaml -f compose.dev.yaml down

# Devcontainer from the CLI (the same engine VS Code uses), useful for validation
node ~/.vscode/extensions/ms-vscode-remote.remote-containers-*/dist/spec-node/devContainersSpecCLI.js up --workspace-folder <repo>
# then tear down: docker compose -p earth-jukebox -f compose.yaml -f compose.dev.yaml -f .devcontainer/compose.devcontainer.yaml down
```

The Compose project name is `earth-jukebox` (containers `earth-jukebox-backend-1`, `earth-jukebox-frontend-1`). The dev stack and the devcontainer share it, so starting one recreates the other's containers.

## Testing and verification approach

- Backend: pytest with FastAPI's TestClient (needs **`httpx2`**, which Starlette 1.10 prefers; plain `httpx` is deprecated there). Tests build the app with explicit `Settings(...)` so the host environment can't leak in.
- Frontend: no test framework in the repo. Verification so far used throwaway scripts in the session scratchpad:
  - Node ESM tests of `client.js` with a `fetch` wrapper that prefixes `http://127.0.0.1:8080` (Node has no page origin);
  - end-to-end tests with Playwright driving the installed Chrome, with no browser download: `uv run --no-project --with playwright python -I script.py`, `chromium.launch(channel="chrome", args=["--use-angle=swiftshader","--enable-unsafe-swiftshader"])`, wait for `.globe--ready`, then click the canvas.
- When waiting for a service, use `curl -sf`: without `-f`, a 502 counts as success.

## Gotchas (learned the hard way)

- **MapLibre globe clicks in empty space still return coordinates** (a point on the far edge). `globe.isOnGlobe(event)` projects the returned point back to the screen and rejects it if it lands more than 2 px from the click. This was verified: the cut-off is the same globe radius in all directions.
- **Auto-spin** (`auto-spin.js`) decrements the longitude forever, so always use `lngLat.wrap()` before sending coordinates.
- Clicks on the popup itself don't reach the map, which is expected. (E2E tests must click away from the popup.)
- **nginx:**
  - an `add_header` inside a `location` drops all server-level `add_header`s, so prod caching uses `expires`, not `add_header`;
  - `/api/` uses `location ^~` so the extension regex locations can't capture API paths;
  - `proxy_pass $backend` (a variable, no URI) plus `resolver ${NGINX_LOCAL_RESOLVERS} valid=10s` re-resolves the backend, so recreated containers keep working (tested).
- **Windows bind mounts** don't deliver file-change events, so `WATCHFILES_FORCE_POLLING=true` (set in compose.dev.yaml and in launch.json) and `--reload-dir app` (polling all of backend/ including a Windows `.venv` would be slow).
- Single-file read-only mounts (index.html, explorer.html) **do** pick up atomic editor saves on Docker Desktop for Windows (tested).
- `COMPOSE_BAKE=false` is **not** needed: builds work on Compose v5.6.1, because the build contexts are subfolders and don't reach up into a parent directory.
- `.devcontainer/compose.devcontainer.yaml` uses `ports: !reset []` so VS Code `forwardPorts` doesn't clash with published ports.
- `overrideCommand: true` in devcontainer.json: the backend only sleeps, and F5 starts uvicorn (so `/api` gives 502 until then). Breakpoints after an auto-reload under debugpy are untested; if they fail, drop `--reload` from the launch config.
- Opening the devcontainer in the same VS Code window loses the Claude Code session and memory, which stay on the Windows host. Use a separate window for the devcontainer.
- **Git Bash on Windows:**
  - `git show branch:.file` and `curl -w "/path"` get mangled by MSYS path conversion, so use `MSYS_NO_PATHCONV=1`;
  - `time` is not available inside `sh -c` in slim containers;
  - the console shows `°` and `·` as `�`. That is a display issue only.
- **PowerShell:** `curl` is an alias for a different command, so use `curl.exe`.
- Line endings: the machine has `core.autocrlf=true`. `.gitattributes` forces LF for sh, conf, template, Dockerfile, yaml, toml, lock and py files, and marks images, fonts, npy and tif as binary. `core.filemode=false` is in the repo config (shared with the container).
- In the VS Code Dockerfile linter, comments inside a multi-line `ENV` show as false errors. Keep comments above the instruction.

## Known issues and tech debt

- `frontend/assets/images/earth-water.png` is 16200×8100 (4.7 MB) but only used downscaled to 720×360, on both pages. Decoding it takes about 525 MB of RAM, which is a risk on mobile. A 1440×720 version would do.
- Sound: no spatial sweep around the point yet (notebooks 03/04 of the exploration repo have the idea), and playback does not start by itself on click (the user presses play).
- `/api/point`, `api/client.js` and the `.ej-point__message` CSS are leftovers from the first click prototype.
- NASA is a runtime dependency: if GEOS-FP is down when the backend starts, the aerosol layer stays empty until it recovers (no on-disk copy of the last scene). The in-memory scene is per process, so a serverless host would rebuild it on every cold start.
- GEOS-FP "assim" data runs about 12 hours behind real time.
- `gibs.js` is currently unused (no layer has a GIBS `source`); it will be needed again for fires.
- The explorer panel note still reads "PENDIENTE"; the rain layer has no data.
- `SCENE_STEPS` and `SCENE_WARMUP` are not in `.env.example` (Claude cannot edit it).

## Verified NASA facts (probed 14-15 Nov 2026)

More detail and evidence live in the sibling exploration repo `D:\nasa-sonification` (its CLAUDE.md and `explore/` notebooks).

- **GEOS-FP OPeNDAP** (`https://opendap.nccs.nasa.gov/dods/GEOS-5/fp/0.25_deg/assim/tavg3_2d_aer_Nx`, no key): 3-hourly, 0.25° × 0.3125° (721 × 1152). AOD per species: `brexttau`, `bcexttau`, `duexttau`, `ssexttau`, `suexttau`, plus `ocexttau`, `niexttau`, `totexttau`; surface `pm25`. Fill value 1e15. Sometimes answers 502/504.
- **EIC daily visualization PM2.5 (SVS 5151)**: 372 hourly PNG frames, 2048×1024, equirectangular, re-rendered daily, from GEOS-CF (not GEOS-FP). Logo, timestamp (US Eastern) and coastlines are burned in. Colour bar is a log ramp 0.4–409.6 µg/m³ (`PM2.5_colorbar_plain.png`); colours convert back to values (the notebooks do it). JSON metadata: `https://svs.gsfc.nasa.gov/api/5151`.
- **EIC fires (SVS 5113)**: `VIIRS_fires_latest.png` is an oval projection with date and legend burned in, so it cannot be draped on the globe. The equirectangular version exists only as EXR frames and a 51 MB MP4.
- **SVS sends `Access-Control-Allow-Origin` for one unrelated site only**, so the browser cannot load SVS images into MapLibre or a canvas: they must go through the backend.
- **GIBS** has `VIIRS_NOAA20_Thermal_Anomalies_375m_All` (vector tiles, `GoogleMapsCompatible_Level8`, daily through today, no key).
- **FIRMS** needs a free MAP_KEY.

## Next steps (agreed plan)

Design principle: the **EIC daily visualization is the field** (complete global picture: where, and how much) and the **near-real-time API is the probe** (exact values at a point: composition and trend). Never drive the same visual or sound property from two sources. Both reach the browser as scenes.

- **Phase B, bring in the daily visualization: DONE** (see "Data scenes"). What was planned:
  1. Backend: a `pm25-latest` scene that decodes the newest SVS 5151 frame (colour → value, fill gaps under logo/timestamp/coastlines) into the scene format. Reuse `SceneStore`; port the decoding from `D:\nasa-sonification\explore\nasa_sources.py` (`gradient_from_colour_bar`, `invert_gradient`). Adds Pillow.
  2. Globe: draw it through `series-layer.js` with a colour-ramp mode (NASA's ramp, alpha by value). **Decided (option B):** the species buttons stay and gain a first "PM2.5" button (default) that shows the EIC scene; the other five still draw that live GEOS-FP species.
- **Phase C, live data at a point: DONE** (see "Click → reading → popup and sound"). What was planned:
  1. Popup: PM2.5 value, species breakdown and trend over the last 3 steps, read locally from the scenes.
  2. Sound: replace the simulated source. PM2.5 → pitch and level; species shares → timbre; trend → a short cue. Mapping ideas are in the notebooks 03/04 of the exploration repo.
- **Phase D, fires: the globe part is DONE** with the EIC visualization (not GIBS tiles). Still open: fires in the point card and the sound; live numbers near the click need a FIRMS key.

The earlier idea of migrating Gabriel's backend from `D:\NASA-Proyecto` (NASA POWER, EONET, `/api/layers`) is on hold: this plan replaces it. Do not bring its Mapbox token machinery, `requirements*.txt` or root Dockerfile in any case.
