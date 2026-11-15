# CLAUDE.md: Earth Jukebox

Context for AI coding sessions. Read this before exploring the code; open source files only when this file doesn't answer the question. Keep it updated when architecture or conventions change.

## Project

- **Earth Jukebox**, for the NASA Space Apps Challenge 2026: a 3D globe that turns NASA Earth observation data into sound (sonification), for accessibility (blind and low-vision users). See [README.md](README.md) for the pitch.
- Hackathon goal: the team is aiming for the award for **most plausible concept and design**, so architecture quality, clean structure and a credible path to scale matter as much as features. Avoid overbuilding: no DB, queue or cache server unless asked.
- The UI, code comments, docstrings and error messages are in **Spanish**. Identifiers and docs (README, this file) are in English.
- Local-only for now, as one API instance. **Supabase cannot host the Python API** (Edge Functions are TypeScript/Deno only). A serverless host does not fit the API as it stands (see "Known issues").

## Working rules (from the user)

- **Never commit, push, pull, merge or tag** unless the user asks in that message. Work on feature branches, not `main`.
- **No AI attribution anywhere**: no "Co-Authored-By", "generated with" or similar in commits, PRs, README or comments.
- Analysis requests are read-only. For bigger tasks, propose a plan and wait for approval.
- Python tooling is **uv** (never pip or requirements.txt).
- **Code standard (the owner's words): readable, pythonic, well organised; no spaghetti; docstrings and type hints; unit tests.** It is enforced by tooling (see "Quality gates"): do not weaken those settings to make something pass.
- Do not commit data to git (scene files, downloads). No dead code and no stale docs: when something stops being used, delete it and update this file and the README in the same change.
- Before claiming a library feature exists, check the version pinned here (lockfile, CDN URL).
- A permission rule blocks Claude from reading or writing `.env*` files (including `.env.example`). Ask the user to edit them.
- Current focus is the **backend**. Frontend refactoring, frontend tests and keyboard access are deferred (see "Deferred frontend work").

## Layout

```
frontend/                 Static site = nginx web root (relative paths everywhere)
  index.html              Landing page: Three.js dotted globe (js/pages/landing.js)
  explorer.html           Main app: MapLibre globe (js/pages/explorer.js)
  css/                    tokens.css (design tokens), base, components, landing, explorer, explorer-shell (panels, point card)
  js/
    config.js             Layer catalog (LAYERS): id, label, icon, ramp, defaultOpacity. `kind: 'scene'` + `scenes` = data scenes
                          (species = the buttons, each tagged with its sceneId; the first is the default). `source` = GIBS raster. Neither = "Pendiente"
    catalog/scenes.js     Scene catalog (SCENES): id, dataUrl (the API), source and stampLabel (shown in the panel), species (id, label, color)
    core/layers.js        isSceneLayer(), isLayerAvailable(), sceneIdOf()
    data/scene-data.js    loadScene(baseUrl) (manifest + .f32, checks size and sha256), cellValueAt() (exact cell), sampleAt() (interpolated; not used yet), createResampler()
    data/scene-cache.js   getScene(sceneId): one shared download per scene; failures are not cached
    data/point-reading.js readPm25(), readAerosols(), levelOf(): the reading of a clicked point
    pages/                Page entry points (landing.js, explorer.js); explorer.js wires the panels, the click → reading flow and the point card
    map/                  globe-map.js (createGlobeMap → {map, flyTo, isOnGlobe, showMarker, hideMarker, destroy}), series-layer.js (scene → canvases → raster layer),
                          scene-animation.js (loop clock), gibs.js, night-lights.js, land-dots.js, hover-glow.js, auto-spin.js
    ui/                   layer-panel, player (audio UI), waveform, point-card, mode-toggle, dialog, icons, globe-status
    audio/                audio-engine.js (Web Audio: pitch/level from a value, one voice per aerosol species, trend cue), simulated-source.js
    state/                store.js (tiny pub/sub store), app-store.js
    effects/              starfield.js, dotted-globe.js + globe/* (Three.js landing globe and shaders)
    core/                 animation-loop, motion (reduced motion), resize, pointer-parallax, css-tokens
  assets/                 fonts (woff2), images/earth-water.png (land mask), tiles/nightlights/{z}/{x}/{y}.webp (z0–4, 341 tiles)
  nginx/                  default.conf.template + dev.conf / prod.conf (included as /etc/nginx/snippets/mode.conf)
  Dockerfile  .dockerignore
backend/                  uv project (package = false: an app, run from backend/)
  app/main.py             Entry point: `app = create_app()` (`uvicorn app.main:app`). Nothing else
  app/factory.py          create_app(settings, scenes) and default_scenes(settings): the only place where the app is wired
  app/config.py           Settings (pydantic-settings, env vars only): cors_origins, scene_steps (1–24, default 8), scene_warmup
  app/schemas.py          API contract (Pydantic): Health, SceneList, Manifest, TimeAxis, GridBlock, Scale, SpeciesEntry
  app/api/__init__.py     router with prefix /api; includes health and scenes
  app/api/health.py       GET /api/health → {status, version}
  app/api/scenes.py       GET /api/scenes, /api/scenes/{scene_id}/manifest.json (503 + Retry-After while building), /{scene_id}/{version}/{species}.f32
  app/services/http.py    http_get, http_last_modified: retries; check_url (https, host allow-list, no user info or odd ports), also applied to redirects (urllib only)
  app/services/scenes.py  Scene, SceneSource protocol, SceneStore; the manifest builders (build_manifest, encode_species, grid_block, whole_globe_grid, time_axis)
  app/services/geosfp.py  GEOS-FP OPeNDAP client (urllib + numpy): parse_das, parse_dods, GeosFpClient
  app/services/svs.py     SVS client: parse_page (`/api/{id}` JSON), parse_frame_listing, SvsClient
  app/services/colour_scale.py   Colour → value on images: read a colour bar, invert it, reject thin lines, drop islands, downsample, max_pool, fill small gaps
  app/services/exr.py     read_rgb(bytes): OpenEXR frame → linear float32 RGB
  app/services/aerosol_scene.py  AerosolSource → `aerosol-latest` (GEOS-FP, 5 species)
  app/services/pm25_scene.py     Pm25Source → `pm25-latest` (EIC daily visualization SVS 5151)
  app/services/fire_scene.py     FireSource → `fires-latest` (EIC daily visualization SVS 5113)
  geosfp/                 OFFLINE pipeline library (xarray + pydap; needs `--group pipeline`): client (remote access with chunked, retried loads),
                          episode (download to NetCDF), timeline (GrADS time axis, pure), stats (per-step statistics and CSV, pure),
                          validation, grid (grid description, reuses app.services.scenes), cli (argparse helpers)
  tools/                  OFFLINE command-line scripts: find_episode, summarize_episode, download_global_episode, build_scene
  tests/                  pytest. conftest (isolated settings, fixtures), fakes.py / fake_svs.py / fake_fires.py (fake NASA), fixtures/ (real NASA responses),
                          test_app, test_http, test_scene_store, test_scenes (aerosol), test_pm25_scene, test_fire_scene, test_format_changes,
                          test_real_responses, test_pipeline_* (offline pipeline)
  pyproject.toml  uv.lock  .python-version (3.13)  Dockerfile  .dockerignore
tools/make-night-tiles.py PEP 723 script: `uv run tools/make-night-tiles.py <earth_nightlights_10K.tif>` → frontend/assets/tiles/nightlights
compose.yaml              Production-like: backend (prod) + frontend (prod), only 127.0.0.1:${FRONTEND_PORT:-8080} published
compose.dev.yaml          Overrides: dev targets, repo bind-mounted at /workspace, read-only frontend file mounts, 127.0.0.1:8000 for the API
.devcontainer/            devcontainer.json + compose.devcontainer.yaml (resets published ports; VS Code forwards them)
.vscode/                  launch.json (API: FastAPI, API: tests, Frontend: Chrome, Full stack), extensions.json
.github/workflows/ci.yml  Backend checks on every PR and on main: ruff, mypy, pytest with coverage
```

## Architecture

- **Two images, one origin.** nginx (frontend) serves static files and reverse-proxies `/api/*` to `backend:8000`. The frontend only uses **relative `/api` URLs**, so there is no CORS and no API URL config in JS. The backend never serves frontend files. Keep it that way: it is what makes the design portable.
- All config comes from env vars (no `.env` lookup inside the app; Compose injects them, or `uv run --env-file ../.env`). CORS middleware is added **only** if `CORS_ORIGINS` is non-empty.
- All API routes live under `/api` (including `/api/docs` and `/api/openapi.json`; ReDoc is disabled), because nginx only forwards `/api/`.
- **The backend is not stateless.** It has no database and no user data, but each process holds the scenes it has built in memory and refreshes them from a background thread. It is designed for **one long-lived instance**. See "Scene store".
- Frontend has **no build step**: plain ES modules. Three.js comes from an importmap (jsdelivr `three@0.186.0`). MapLibre is imported by URL (`https://unpkg.com/maplibre-gl@6.16.0/dist/maplibre-gl.mjs`; it spawns its worker from unpkg via a `blob:` URL, which matters for any future CSP). Bootstrap 5.3.8 CSS comes from jsdelivr with SRI.
- External services used by the browser (no keys): OpenFreeMap style `https://tiles.openfreemap.org/styles/dark` (unversioned), NASA GIBS WMTS (Blue Marble basemap), CDNs. Used by the backend: `svs.gsfc.nasa.gov` and `opendap.nccs.nasa.gov`, nothing else (`ALLOWED_HOSTS` in `http.py`).
- Globe layer order (bottom → top): GIBS Blue Marble basemap → night lights (local tiles) → data layers → land dots (GeoJSON from earth-water.png) → labels. OpenFreeMap vector layers are hidden except place, water_name and boundary.
- Frontend state: `app-store.js` holds `{layers, opacity, nightMode, species, scenePlaying, sceneProgress, sceneInfo, reading}`; UI modules subscribe and re-render. No framework.

### Backend module map

Dependency direction is one way: `main → factory → api → services → schemas`. Services never import `api`. `schemas.py` and `config.py` import nothing from the app.

| Layer | Modules | Job |
|---|---|---|
| Wiring | `factory.py`, `main.py` | Build the FastAPI app; choose which scenes exist |
| HTTP routes | `api/health.py`, `api/scenes.py` | Translate requests to store calls; no logic |
| Contract | `schemas.py` | Pydantic models of every response, including the scene manifest |
| Scene machinery | `services/scenes.py` | `SceneSource` protocol, `SceneStore`, and the only functions that build manifests |
| Scene sources | `services/aerosol_scene.py`, `pm25_scene.py`, `fire_scene.py` | One class per scene: `check()` and `build()` |
| NASA clients | `services/geosfp.py`, `services/svs.py`, `services/http.py` | Fetch and parse; injected `get` functions so tests never use the network |
| Image decoding | `services/colour_scale.py`, `services/exr.py` | Pure numpy/Pillow/OpenEXR functions |

**Adding a new scene:** write a class with `scene_id`, `check() -> (version, context)` and `build(version, context) -> Scene` in `services/<name>_scene.py`, building the manifest with `build_manifest`, `encode_species`, `time_axis` and a grid helper (never a hand-made dict); add it to `default_scenes()` in `factory.py`; add a fake source of data and tests; then add the scene to `frontend/js/catalog/scenes.js` and to a layer in `config.js`.

### Data scenes (the common data format)

A **scene** is how gridded data reaches the browser, whatever its source. The format was designed by Alex and is the contract between backend and frontend, typed in `app/schemas.py` (`Manifest`) and published in OpenAPI:

- `manifest.json` (`schema_version: 2`, `kind: "grid-series"`): `scene_id`, `version`, `generated_utc`, `layer`, `provenance` (free-form text, numbers and URL lists), `time` (`steps`, `step_minutes`, `stamps_utc`, `note`), `grid` (`lat_min`, `lat_step`, `lon_min`, `lon_step`, `n_lat`, `n_lon`, `lon_periodic`, …) and per species `file`, `sha256`, `min`, `max`, `unit`, `display_scale_max` and optionally `scale: {kind: "log" | "linear", min, max, ramp}` and `missing`. Optional fields are omitted when empty (`response_model_exclude_none`).
- One `.f32` per species: float32 little-endian, order `[step][lat][lon]`, south to north, west to east. Its URL is `…/{scene_id}/{version}/{species}.f32`: the version is in the path, so files are immutable and cacheable.

The three scenes, all built at runtime (`factory.default_scenes()`), each with `SCENE_STEPS` steps (default 8):

- **`pm25-latest`, the field** (how much, everywhere): the EIC daily visualization PM2.5 (SVS 5151, GEOS-CF model). NASA re-renders 372 hourly frames once a day; the source takes one frame out of every 3, ending at the newest, so 8 steps cover 21 hours. Colours are converted back to µg/m³ with the page's own colour bar (log scale 0.4–409.6, constants in `pm25_scene.py`), coastlines and borders are removed by shape (bright features under 3 px) and filled from neighbours, 4 × 4 pixel blocks are averaged on the log scale to a 512 × 256 grid, and the logo and date boxes stay NaN. The last stamp is NASA's publication time: the spacing between steps is exact, the absolute hour is not, because each frame's own hour is only printed on the image. The manifest carries NASA's ramp colours so the frontend paints with them.
- **`aerosol-latest`, the probe source** (what it is made of, where it is going): GEOS-FP optical depth for 5 species (`SPECIES` in `aerosol_scene.py`), the last 8 three-hourly steps on a 1° × 1.25° global grid (one `.dods` request per species, 1 cell out of 4). Colour scales are fixed constants so colours stay comparable between updates.
- **`fires-latest`**: the EIC daily visualization of VIIRS active fires (SVS 5113), species `frp` in MW. It uses the equirectangular "SoaS" frames (EXR, 4096 × 2048, about 6.5 MB each, one per day; each shows a 5-day moving window). `frp_from_rgb()` maps the linear red channel to fire radiative power with the colour bar read once from the frame legend (constants in `fire_scene.py`; background red ≤ 0.02, fires > 0.2); each cell keeps the strongest fire of its 8 × 8 pixel block (512 × 256 grid, linear scale 0–8 MW). **The newest frames arrive empty or half-filled**, so the source downloads `steps + 5` frames and `frames_with_data()` drops trailing ones with fewer than 0.6× the median fire-pixel count (on 15 Nov 2026 it skipped 4 and used 2–9 Nov). The version is the `Last-Modified` of the newest frame (a HEAD request), because the page's `update_date` does not change with the daily render. Frame dates are inferred: newest published frame = render date − 1 day, one frame per day. Each rebuild downloads about 85 MB from NASA, once a day.

### Scene store (`services/scenes.py`)

- `SceneStore.get()` never waits: it returns the current scene (or None) and, if the check interval has passed and no refresh is running, starts one in a daemon thread. So a scene is checked **only when someone asks for it** (a manifest request, or the warm-up at startup), every 15 minutes at most; after a failure it retries after 30 seconds and keeps serving the last good scene.
- A refresh calls `source.check()` (cheap) and only calls `source.build()` when the version changed. Only one refresh runs at a time (`_claim` / `_release` under a lock, released in `finally`). `refresh()` is the blocking variant, used by tests.
- The store keeps the previous scene too, so a browser holding the old manifest can still download its files.
- `clock` and `spawn` are injectable for tests. `error` holds the last failure for diagnostics and logs; the 503 response sent to clients has a fixed message and does not expose it.
- Scenes live in process memory: about 4 MB (pm25), 8 MB (aerosol), 4 MB (fires), doubled while the previous version is kept. Building peaks at about 105 MB per PM2.5 frame and about 235 MB per fire frame (measured), one frame at a time.

### Frontend: layers, animation, click and sound

- **Layers.** Each layer of `config.js` with `kind: 'scene'` has a collapsible "Tipo" selector (a full-width row under the layer; closed by default, shows the current species) with one radio button per species across its scenes; arrow keys move the selection. Aerosoles: "EIC PM 2.5" (first, default, from `pm25-latest`) and the five GEOS-FP species (from `aerosol-latest`). Incendios: "EIC Incendios". A scene is fetched the first time one of its species is selected with the layer on (`globe-map.js loadScenesOnDemand`, retry every 5 s on any error), and each scene gets its own map layer (`<layer>-<sceneId>`). The panel note shows the source and date of what is on screen (`sceneInfo` in the store).
- **Drawing.** `series-layer.js` paints each step once into its own canvas, re-projected to Web Mercator: with the manifest's ramp when there is one (log: transparent in clean air; linear: any value above zero shows), else with a single colour per species whose opacity grows with the value. It cross-fades the two neighbouring steps with canvas compositing (`lighter` with weights).
- **Animation.** `scene-animation.js` loops 0 → 1 in 9 s, holds 2.2 s on the newest step and restarts (20 fps). `globe-map.js` runs it while `state.scenePlaying` is true and a scene layer is visible, calling `series.setProgress(p)` directly; the store only gets `sceneProgress` in 24 coarse ticks for the panel label ("Últimas 21 h · 8 h antes", or in days for fires). Pausing returns to the newest step. `scenePlaying` starts false when the user prefers reduced motion.
- **Click → reading.** `explorer.js initPointProbe`: ignores clicks off the globe (`globe.isOnGlobe`), wraps and rounds the coordinates, builds a reading (`data/point-reading.js`) and fills it from `getScene('pm25-latest')` and `getScene('aerosol-latest')` independently, with no server round trip per click. The card (`ui/point-card.js`, `textContent` only) sits in a fixed panel in the bottom-right corner (`.ej-point-dock`) and the point gets a `maplibregl.Marker`. Card and sound always describe the newest step; the trend covers all the steps of the scene (21 hours).
- **Roles are fixed:** PM2.5 from the EIC visualization says **how much** (µg/m³, plus a level word from its position on NASA's log scale: relative to that scale, not an air-quality index); GEOS-FP says **what it is made of** (share of each species' optical depth at the newest step) and **where it is going** (change of the 5-species total; beyond ±10% is "en aumento"/"en descenso"). Never drive the same visual or sound property from two sources.
- **Sound** (`ui/player.js` + `audio/audio-engine.js`): the player follows `state.reading`. PM2.5 position on NASA's scale → pitch (110 Hz × 2^(3v)) and level; species shares → timbre (gain of one voice per species: sea salt = pure sine, sulfate = bright, brown carbon = odd harmonics, black carbon = rough, dust = beating pair); trend → a three-note cue. Without live data a neutral voice plays. Until the first click, or where the EIC image has no data, the simulated demo signal plays and the top chip reads "Modo demostración" instead of "Datos de la NASA".

## Quality gates (backend)

All four must pass before a change is done; CI runs the same commands (`.github/workflows/ci.yml`, with `--group pipeline` so the pipeline tests run too).

```bash
cd backend
uv run ruff check .            # E, F, I, UP, B, SIM + D (docstrings, google convention) + ANN (type annotations)
uv run ruff format --check .
uv run mypy                    # strict, on app/
uv run pytest --cov            # coverage of app/ with branches; fails under 95% (it is at 100%)
```

- Docstrings are required on every public module, class, function and method (`D107` is ignored: `__init__` arguments are documented in its own docstring when they need explaining). Tests are exempt from `D` and `ANN`: the test name says what is checked.
- Type hints: no bare `dict`/`list`/`tuple`, no untyped parameters; `Any` only at the edges (parsed JSON, `SceneStore[Any]` in the app's registry).
- Tests never touch the network. `tests/conftest.make_settings()` builds settings that ignore the host environment. NASA is replaced by fakes with injected `get` functions; `tests/fixtures/` has real responses (GEOS-FP `.das`, SVS pages 5151 and 5113) so a format change at NASA fails a test. `test_format_changes.py` covers every "NASA changed something" error branch: none may publish a wrongly decoded scene.
- mypy covers `app/` only. `geosfp/` and `tools/` are linted and tested but not type-checked (xarray and pydap are not installed by default) and are outside the coverage figure.

## Offline pipeline (`backend/geosfp`, `backend/tools`)

Not part of the API and not in its image. It downloads a *past* GEOS-FP episode with xarray + pydap and freezes it as a static scene. Run from `backend/` with `uv run --group pipeline python -m tools.<script> --help`: `find_episode` (scan a period, write per-step statistics to CSV), `summarize_episode` (daily table from that CSV), `download_global_episode` (episode → NetCDF in `data/raw/`), `build_scene` (NetCDF → scene in `data/processed/`, built with `app.services.scenes` so it is the same format the API serves). `backend/data/` is git-ignored. Nothing in the app reads these outputs today: there is no static scene in the frontend catalog.

## Docker

- **backend/Dockerfile** stages:
  - `uv` (ghcr.io/astral-sh/uv:0.11.8);
  - `base` (python:3.13-slim-trixie + uv, `UV_PYTHON_DOWNLOADS=0`, `UV_LINK_MODE=copy`);
  - `builder` (`uv sync --locked --no-install-project --no-dev` with cache/bind mounts);
  - **`prod`**: copies only `/app/.venv` and `app/`, user `app` (uid 10001), HEALTHCHECK via Python urllib, CMD `uvicorn … --port $PORT --log-level $LOG_LEVEL --proxy-headers --forwarded-allow-ips='*'`;
  - **`dev`**: git/curl/procps, user `vscode` (uid 1000), venv at **`/opt/venv`** (`UV_PROJECT_ENVIRONMENT`, outside the bind mount), `UV_COMPILE_BYTECODE=0`, CMD `uvicorn --reload --reload-dir app`.
- **frontend/Dockerfile**: `nginxinc/nginx-unprivileged:1.30.5-alpine` (uid 101, port 8080). `ENV BACKEND_URL`, `NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1`. The template goes to `/etc/nginx/templates/`, and the entrypoint's envsubst only substitutes *defined* env vars. The `dev` target uses dev.conf (no-store, sendfile off); the `prod` target uses prod.conf (gzip, including `application/octet-stream` for the scene files) and copies index.html, explorer.html, css, js and assets explicitly.
- The backend prod image is 364 MB (numpy, Pillow, OpenEXR); it has no `geosfp/`, `tools/`, tests or pipeline libraries (checked). Compose passes `LOG_LEVEL`, `CORS_ORIGINS`, `SCENE_STEPS` and `SCENE_WARMUP` to the backend.

## Commands

```bash
# Backend (host, from backend/)
uv sync
uv run --env-file ../.env uvicorn app.main:app --reload
uv run --group pipeline pytest          # everything, including the offline pipeline tests

# Stacks (from repo root)
docker compose up --build -d                                       # prod-like → http://localhost:8080
docker compose -f compose.yaml -f compose.dev.yaml up -d --build   # dev → :8080 (nginx) and :8000 (API)
docker compose -f compose.yaml -f compose.dev.yaml down

# Devcontainer from the CLI (the same engine VS Code uses), useful for validation
node ~/.vscode/extensions/ms-vscode-remote.remote-containers-*/dist/spec-node/devContainersSpecCLI.js up --workspace-folder <repo>
# then tear down: docker compose -p earth-jukebox -f compose.yaml -f compose.dev.yaml -f .devcontainer/compose.devcontainer.yaml down
```

The Compose project name is `earth-jukebox` (containers `earth-jukebox-backend-1`, `earth-jukebox-frontend-1`). The dev stack and the devcontainer share it, so starting one recreates the other's containers.

## Verifying the frontend

There is no frontend test framework in the repo yet. Verification so far used throwaway end-to-end scripts in the session scratchpad: Playwright driving the installed Chrome, with no browser download: `uv run --no-project --with playwright python -X utf8 -I script.py`, `chromium.launch(channel="chrome", args=["--use-angle=swiftshader","--enable-unsafe-swiftshader"])`, wait for `.globe--ready`, then click the canvas. The headless browser has no GPU, so it says nothing about animation smoothness, and nobody can listen to the audio there.

When waiting for a service, use `curl -sf`: without `-f`, a 502 counts as success.

## Gotchas (learned the hard way)

- **MapLibre globe clicks in empty space still return coordinates** (a point on the far edge). `globe.isOnGlobe(event)` projects the returned point back to the screen and rejects it if it lands more than 2 px from the click.
- **Auto-spin** (`auto-spin.js`) decrements the longitude forever, so always use `lngLat.wrap()` before using coordinates.
- **SVS frame folders list their files in two ways**: relative links (`0001.png`, PM2.5) or absolute paths (`/vis/.../frame.001.exr`, fires). `parse_frame_listing` handles both and sorts by the numbers in the file name.
- **pydantic-settings parses the environment even when a value is passed explicitly**, so a broken `CORS_ORIGINS` on the host would break `Settings(cors_origins=[])`. Tests therefore use `make_settings()`, whose class reads no environment at all.
- **A black line over orange is brown**, and brown is the top of NASA's PM2.5 colour ramp: borders cannot be told from heavy pollution by colour, only by shape (`reject_thin_features`).
- **nginx:**
  - an `add_header` inside a `location` drops all server-level `add_header`s, so prod caching uses `expires`, not `add_header`;
  - `/api/` uses `location ^~` so the extension regex locations can't capture API paths;
  - `proxy_pass $backend` (a variable, no URI) plus `resolver ${NGINX_LOCAL_RESOLVERS} valid=10s` re-resolves the backend, so recreated containers keep working (tested).
- **Windows bind mounts** don't deliver file-change events, so `WATCHFILES_FORCE_POLLING=true` (set in compose.dev.yaml and in launch.json) and `--reload-dir app` (polling all of backend/ including a Windows `.venv` would be slow).
- Single-file read-only mounts (index.html, explorer.html) **do** pick up atomic editor saves on Docker Desktop for Windows (tested).
- `.devcontainer/compose.devcontainer.yaml` uses `ports: !reset []` so VS Code `forwardPorts` doesn't clash with published ports.
- `overrideCommand: true` in devcontainer.json: the backend only sleeps, and F5 starts uvicorn (so `/api` gives 502 until then). Breakpoints after an auto-reload under debugpy are untested; if they fail, drop `--reload` from the launch config.
- Opening the devcontainer in the same VS Code window loses the Claude Code session and memory, which stay on the Windows host. Use a separate window for the devcontainer.
- **Git Bash on Windows:** `git show branch:.file` and `curl -w "/path"` get mangled by MSYS path conversion (use `MSYS_NO_PATHCONV=1`); the console shows `°` and `·` as `�`, a display issue only; Python prints of non-Latin-1 characters need `-X utf8`.
- **PowerShell:** `curl` is an alias for a different command, so use `curl.exe`.
- Line endings: the machine has `core.autocrlf=true`. `.gitattributes` forces LF for sh, conf, template, Dockerfile, yaml, toml, lock and py files, and marks images, fonts, tif and f32 as binary. `core.filemode=false` is in the repo config (shared with the container).
- In the VS Code Dockerfile linter, comments inside a multi-line `ENV` show as false errors. Keep comments above the instruction.

## Known issues and limits

- **One instance only.** Scenes are per process, so replicas would not agree during an update and a serverless host would rebuild from NASA on every cold start. Lifting this needs the built scenes stored outside the process (disk or object storage).
- **NASA is a runtime dependency.** If its servers are down when the backend starts, the affected layer stays empty until they recover: there is no on-disk copy of the last scene.
- **Data age:** GEOS-FP "assim" runs about 12 hours behind real time; the PM2.5 loop only changes once a day; the newest usable fire frame is several days old.
- **The PM2.5 scale ends (0.4 and 409.6 µg/m³) and the fire colour bar are constants.** If NASA rescales either legend, values would be wrong without any error. Nothing checks them against the page.
- `SCENE_STEPS` applies to all three scenes at once.
- The CI workflow has never run: it was written locally and its action versions (`actions/checkout@v4`, `astral-sh/setup-uv@v5`) are unverified.
- `SCENE_STEPS` and `SCENE_WARMUP` are not in `.env.example` (Claude cannot edit it); Compose has defaults for both.
- `tools/make-night-tiles.py` (repo root) is outside ruff's scope and runs at import.
- `frontend/assets/images/earth-water.png` is 16200×8100 (4.7 MB) but only used downscaled to 720×360, on both pages. Decoding it takes about 525 MB of RAM, a risk on mobile.

## Deferred frontend work

Agreed to leave for later (from the independent review of 15 Nov 2026); do not start these unasked:

- **Keyboard and screen-reader point selection.** A point can only be picked with the mouse. Also: two live regions announce each click.
- **No frontend tests, linter or formatter.** Mixed quote styles and indentation between files. First candidates for unit tests: `data/scene-data.js`, `data/point-reading.js`, the pure parts of `map/series-layer.js`, `data/scene-cache.js`, `state/store.js`.
- **Large closure functions** (114–187 lines) in `series-layer.js`, `globe-map.js`, `dotted-globe.js`, `layer-panel.js`, `audio-engine.js`, `waveform.js`, `player.js`; `globe-map.js` also owns scene loading, retries (forever, every 5 s) and the animation wiring.
- **Duplicated helpers:** date, percent and trend formatting in `layer-panel.js`, `point-card.js` and `player.js`; the land mask in `map/land-dots.js` and `effects/globe/land-mask.js`. Species ids are written in `aerosol_scene.py`, `catalog/scenes.js` and `audio-engine.js` with nothing checking they agree.
- **Not yet removed:** `sampleAt()` (kept for a spatial sweep in sound), the GIBS raster path (`gibs.js`, `addNasaLayers`: no layer has a `source` today; the rain layer would use it), `title`/`reference` in the scene catalog (not shown), unused CSS selectors in `explorer.css`, `components.css`, `base.css` and `explorer-shell.css`, and the "PENDIENTE" note in `explorer.html`.
- MapLibre is a static import from a CDN: if it is unreachable the page fails without a message. Scene fetches have no timeout and the scene cache is never invalidated, so a tab left open never shows newer data.
- Fires are on the globe only: not in the point card or the sound. Sound has no spatial sweep and does not start by itself on click.

## Verified NASA facts (probed 14-15 Nov 2026)

More detail and evidence live in the sibling exploration repo `D:\nasa-sonification` (its CLAUDE.md and `explore/` notebooks).

- **GEOS-FP OPeNDAP** (`https://opendap.nccs.nasa.gov/dods/GEOS-5/fp/0.25_deg/assim/tavg3_2d_aer_Nx`, no key): 3-hourly, 0.25° × 0.3125° (721 × 1152). AOD per species: `brexttau`, `bcexttau`, `duexttau`, `ssexttau`, `suexttau`, plus `ocexttau`, `niexttau`, `totexttau`; surface `pm25`. Fill value 1e15. Sometimes answers 502/504.
- **EIC daily visualization PM2.5 (SVS 5151)**: 372 hourly PNG frames, 2048×1024, equirectangular, re-rendered once a day, from GEOS-CF (not GEOS-FP). Logo, timestamp (US Eastern) and coastlines are burned in. Colour bar is a log ramp 0.4–409.6 µg/m³ (`PM2.5_colorbar_plain.png`). JSON metadata: `https://svs.gsfc.nasa.gov/api/5151`. Against GEOS-FP `pm25` the pattern agrees but GEOS-FP reads 4–6× higher in clean air: never mix their absolute levels.
- **EIC fires (SVS 5113)**: 900 EXR frames per version (EIC = oval projection with date and legend; SoaS = equirectangular, no labels), linear RGB with display = value^(1/2.2). One frame per day near the end of the sequence; the last 3–4 are empty or partial. `VIIRS_fires_latest.png` is the oval version and cannot be draped on the globe.
- **SVS sends `Access-Control-Allow-Origin` for one unrelated site only**, so the browser cannot load SVS images into MapLibre or a canvas: they must go through the backend.
- **GIBS** has `VIIRS_NOAA20_Thermal_Anomalies_375m_All` (vector tiles, `GoogleMapsCompatible_Level8`, daily through today, no key). **FIRMS** needs a free MAP_KEY. Neither is used yet.

## Possible next steps

Not agreed, only candidates: fires in the point card and the sound; live fire numbers near the click (needs a FIRMS key); storing built scenes outside the process; a guard on the legend constants; the deferred frontend work above. The earlier idea of migrating Gabriel's backend from `D:\NASA-Proyecto` (NASA POWER, EONET) was dropped in favour of the scene design.
