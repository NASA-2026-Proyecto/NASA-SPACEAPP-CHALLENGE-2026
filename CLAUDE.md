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
    config.js             Layer catalog (LAYERS): id, label, ramp, paint, GIBS source. No `source` = "Pendiente"
    api/client.js         apiGet()/getPoint(): fetch to relative /api, ApiError, 8 s timeout, AbortSignal
    pages/                Page entry points (landing.js, explorer.js); explorer.js wires the UI and the click → /api/point flow
    map/                  globe-map.js (createGlobeMap → {map, flyTo, isOnGlobe, showPopup, destroy}), gibs.js,
                          night-lights.js, land-dots.js, hover-glow.js, auto-spin.js
    ui/                   layer-panel, player (audio UI), waveform, point-card (click popup), mode-toggle, dialog, icons, globe-status
    audio/                audio-engine.js (Web Audio: value 0..1 → 110 Hz × 2^(3v), level), simulated-source.js
    state/                store.js (tiny pub/sub store), app-store.js (layers, opacity, nightMode)
    effects/              starfield.js, dotted-globe.js + globe/* (Three.js landing globe and shaders)
    core/                 animation-loop, motion (reduced motion), resize, pointer-parallax, css-tokens
  assets/                 fonts (woff2), images/earth-water.png (land mask), tiles/nightlights/{z}/{x}/{y}.webp (z0–4, 341 tiles)
  nginx/                  default.conf.template + dev.conf / prod.conf (included as /etc/nginx/snippets/mode.conf)
  Dockerfile  .dockerignore
backend/                  uv project (package = false: an app, run from backend/)
  app/main.py             create_app(settings) factory + module-level `app` (also Vercel's entrypoint)
  app/config.py           Settings (pydantic-settings, env vars only): cors_origins
  app/schemas.py          Health, PointResponse
  app/api/__init__.py     router with prefix /api; includes health, point
  app/api/params.py       Shared Lat/Lon Query types (ge/le validation → 422)
  app/api/health.py       GET /api/health → {status, version}
  app/api/point.py        GET /api/point?lat&lon → {ok, lat, lon, message}
  tests/                  conftest (client fixture with explicit Settings), test_app.py, test_point.py
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
- State: `app-store.js` holds `{layers, opacity, nightMode, selectedMarker}`; UI modules subscribe and re-render. No framework.

### Click → API flow (explorer)

`explorer.js initPointProbe(globe)`: on `map.on('click')` it
1. ignores the click if `!globe.isOnGlobe(event)`;
2. calls `event.lngLat.wrap()`;
3. rounds to 5 decimals;
4. aborts the previous request (AbortController);
5. calls `card.pending()` + `globe.showPopup()`;
6. awaits `getPoint()` → `card.success(reply)` or `card.error(point, msg)`.

The popup is a single reused `maplibregl.Popup` (`closeOnClick: false`, `focusAfterOpen: false`, class `ej-popup`). Card text is set via `textContent` only.

## Docker

- **backend/Dockerfile** stages:
  - `uv` (ghcr.io/astral-sh/uv:0.11.8);
  - `base` (python:3.13-slim-trixie + uv, `UV_PYTHON_DOWNLOADS=0`, `UV_LINK_MODE=copy`);
  - `builder` (`uv sync --locked --no-install-project --no-dev` with cache/bind mounts);
  - **`prod`**: copies only `/app/.venv` and `app/`, user `app` (uid 10001), HEALTHCHECK via Python urllib, CMD `uvicorn … --port $PORT --log-level $LOG_LEVEL --proxy-headers --forwarded-allow-ips='*'`;
  - **`dev`**: git/curl/procps, user `vscode` (uid 1000), venv at **`/opt/venv`** (`UV_PROJECT_ENVIRONMENT`, outside the bind mount), `UV_COMPILE_BYTECODE=0`, CMD `uvicorn --reload --reload-dir app`.
- **frontend/Dockerfile**: `nginxinc/nginx-unprivileged:1.30.5-alpine` (uid 101, port 8080). `ENV BACKEND_URL`, `NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1`. The template goes to `/etc/nginx/templates/`, and the entrypoint's envsubst only substitutes *defined* env vars. The `dev` target uses dev.conf (no-store, sendfile off); the `prod` target uses prod.conf and copies index.html, explorer.html, css, js and assets explicitly.
- Images: backend prod ~234 MB, dev ~519 MB; frontend prod ~107 MB.

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
- `config.js` aerosol layer: GIBS `MODIS_Terra_Aerosol`, date fixed at `2014-04-09` (a known-good sample).
- The sonification player uses `createSimulatedSource()`; it is not yet connected to API data.
- The explorer panel note still reads "PENDIENTE"; the fire and rain layers have no `source`.

## Next steps (planned)

Migrate the rest of the earlier backend from `D:\NASA-Proyecto`, branch `origin/BackEnd---Gabriel` (commit 4239d15). It has a clean FastAPI design and 63 tests.
- **Bring over:**
  - `catalog.py` (layer specs);
  - providers (`DataProvider` protocol, `SimulatedProvider`, `PowerProvider` for NASA POWER, no key);
  - `services/` (TTL cache, urllib HTTP client, land/ocean/ice `geo.py` + `data/land_mask.npy`, normalize, status phrases);
  - `services/events.py` + `api/events.py` (NASA EONET);
  - `api/layers.py` (`/api/layers`, `/{id}/value`, `/{id}/series`), reusing `app/api/params.py` Lat/Lon;
  - the tests. It adds **numpy**.
- **Do not bring over** any of these, because the new frontend uses MapLibre + OpenFreeMap and needs no token:
  - the Mapbox token machinery (`MAPBOX_TOKEN`, `/js/config.local.js`, `write_config_local.py`);
  - `_mount_frontend`;
  - `requirements*.txt`;
  - the root Dockerfile;
  - `render.yaml`.
- **Fix during migration:**
  - rebuild `land_mask.npy` from the new earth-water.png with `scripts/build_land_mask.py` (0.41% of cells differ);
  - the layer ids differ (backend: fire, rain, temp, wind, humidity; frontend config.js: fire, rain, aerosol). `test_layers_match_frontend_catalog` looks for `REPO_ROOT/js/config.js`, which is now `frontend/js/config.js`, so it would silently skip.
- Then connect the click popup and the audio player to `/api/layers/{id}/value` and `/series`.
- Victor's old branch `feature/containerize-frontend--victor` was the base for the nginx setup (already migrated).
