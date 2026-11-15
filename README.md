# Earth Jukebox

**Listen to our planet.** An interactive 3D globe that turns NASA Earth observation data into sound.

Project for the **NASA Space Apps Challenge 2026**. Not an official NASA product.

## The challenge

NASA's **Earth Information Center (EIC)** publishes compelling visualizations of our planet's vital signs: global temperature, sea level, ice, wildfires and more. They are almost entirely visual (maps, images and charts), which leaves out people who cannot rely on sight, including people who are blind or have low vision.

**Our goal:** build an *Earth Jukebox*, an immersive, real-time **sonification** experience that translates real Earth data from NASA and the EIC into sound. Pitch, rhythm and volume follow the data, so anyone can *hear* how the planet is changing, not only see it.

## How it works

1. **Observe:** Earth observation layers are drawn on a 3D globe (NASA GIBS imagery).
2. **Explore:** rotate the globe, switch layers on and off, and click any point on Earth.
3. **Listen:** the active layer becomes sound at the point you click, by fixed rules: more of it gives a denser, louder sound, and it arrives from the side where there is more. A text description says what you are hearing.

### Current status (prototype)

| Feature | Status |
|---|---|
| 3D globe with NASA Blue Marble basemap and night lights | ✅ Working |
| Aerosol layer, default view: the EIC daily visualization *Particulate Matter (PM) 2.5*, decoded from NASA's image back into values and drawn with NASA's own colour scale | ✅ Working |
| Aerosol layer, alternative views: near-real-time NASA GEOS-FP model data (five aerosol types, refreshed every 3 hours) | ✅ Working |
| The aerosol layer is animated: it loops through the last 21 hours of data, with a pause button | ✅ Working |
| Click on the globe → the data of the active layer at that point: PM2.5, aerosol composition and trend (aerosols); the strongest fire nearby and its last days (fires); rain and snow rates and their last hours (precipitation) | ✅ Working |
| Sonification of the clicked point: the active layer is translated into a 15-second sound by fixed rules (air: a drone and dust that grow with PM2.5; rain: drops per second, wind and thunder; fire: crackles and flame that grow with radiative power), with a spoken description of what is heard | ✅ Working |
| One data layer at a time: what you see is what you hear; with no layer on, the app stays silent | ✅ Working |
| API: `/api/health` and `/api/scenes` (`pm25-latest`, `aerosol-latest`, `fires-latest`, `precipitation-latest`) and `/api/sounds` (`air`, `rain`, `fire`), with a typed, documented contract | ✅ Working |
| Fires layer: the EIC daily visualization *Active Fires As Observed by VIIRS*, decoded into fire radiative power (MW) and animated day by day over the last week | ✅ Working |
| Precipitation layer: the EIC visualization *Near Real-Time Global Precipitation* (GPM IMERG), decoded into rain and snow rates (mm/h) and animated over the last 21 hours | ✅ Working |
| Sounds for snow and temperature | 🔜 Pending |

## Architecture

```
            browser
               │  http://localhost:8080   (a single origin: no CORS)
               ▼
   ┌───────────────────────────┐
   │ frontend · nginx          │  static site: HTML, CSS, ES modules (no build step)
   │   /        → files        │
   │   /api/*   → proxy ───────┼──┐
   └───────────────────────────┘  │
                                   ▼
                    ┌──────────────────────────┐
                    │ backend · FastAPI (uv)    │  configured by env vars
                    │   /api/health             │
                    │   /api/scenes/…           │──▶ NASA SVS (EIC daily visualizations)
                    │   /api/sounds/…           │──▶ NASA GEOS-FP (OPeNDAP)
                    └──────────────────────────┘
```

- **Data scenes.** The backend fetches NASA data once per update (not once per click), converts it to a compact *scene* (a JSON manifest plus one binary grid per variable) and keeps it in memory. The browser downloads the scene and draws it on the globe, so interaction never waits on NASA.
- **Sound made from the data.** On a click, the backend reads the point in the scene it already holds and synthesises a 15-second clip with numpy (`/api/sounds`). Each sound hangs on one number computed from the data, with fixed formulas, so the same data always gives the same sound: it is a translation of the measurement, not music. Rendering costs about a second of CPU per click, so at most two clips are rendered at once; a pre-rendered bank of clips is the planned fallback if that does not scale.

- **Two images served from one origin.** nginx serves the site and forwards `/api/*` to the API, so the frontend only uses relative URLs (`/api/...`). The same frontend code works locally, in Docker and on any host that can route `/api` to the backend.
- **No database.** The backend holds no user data; its only state is the scenes it has built, kept in the memory of the process and rebuilt from NASA after a restart. Because of that it is meant to run as **one long-lived instance** for now: several replicas would each build their own copy, and a serverless host would rebuild on every cold start. Persisting the built scenes to shared storage is the step that would lift this.
- **Typed contract and self-documenting API.** The scene manifest is a Pydantic model shared by every data source, published in the interactive OpenAPI docs at `/api/docs`.
- **Only NASA is contacted.** The backend only requests `https` URLs on the two NASA hosts it uses, retries transient failures, and keeps serving the last good scene when NASA is down.

| Part | Stack |
|---|---|
| Frontend | HTML, CSS and vanilla JavaScript modules · [MapLibre GL](https://maplibre.org/) (globe) · [Three.js](https://threejs.org/) (landing page globe) · Web Audio API · Bootstrap 5 |
| Backend | Python 3.13 · [FastAPI](https://fastapi.tiangolo.com/) · Uvicorn · Pydantic Settings · managed with [uv](https://docs.astral.sh/uv/) |
| Infrastructure | Docker (multi-stage builds) · Docker Compose · nginx (non-root) · VS Code Dev Containers |

## Repository layout

```
frontend/              Static site (served as the web root)
  index.html             Landing page
  explorer.html          Globe explorer
  css/  js/  assets/     Styles, ES modules, fonts, images and night-lights tiles
  nginx/                 nginx config: template + dev/prod settings
  Dockerfile
backend/               FastAPI app (uv project)
  app/                   factory.py (builds the app), main.py (entry point), config.py, schemas.py (API contract),
                         api/ (routes), services/ (NASA clients, colour decoding, scenes)
  geosfp/  tools/        Offline pipeline: download a past episode and freeze it as a static scene
  tests/                 pytest (no test touches the network); fixtures/ holds real NASA responses
  pyproject.toml  uv.lock  Dockerfile
tools/                 One-off scripts (night-lights tile generator)
compose.yaml           Production-like stack
compose.dev.yaml       Development overrides (live code, auto-reload)
.devcontainer/         VS Code devcontainer (backend + frontend)
.vscode/launch.json    Debug configurations (F5)
.github/workflows/     CI: lint, type check and tests on every pull request
```

## Development

### Requirements

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [VS Code](https://code.visualstudio.com/) with the **Dev Containers** extension (recommended)
- Optional, to run the backend without Docker: [uv](https://docs.astral.sh/uv/getting-started/installation/)

First, create your local environment file (it is git-ignored):

```bash
cp .env.example .env        # Windows PowerShell: copy .env.example .env
```

### Option A: Dev Container (recommended)

Everything runs in containers, with Python debugging included.

1. Open the repository in VS Code → Command Palette → **Dev Containers: Reopen in Container**. The first build takes a couple of minutes.
2. Press **F5** and choose **API: FastAPI**. It starts uvicorn under the debugger with auto-reload.
3. Open **http://localhost:8080** and click on the globe.

| Debug configuration | What it does |
|---|---|
| `API: FastAPI` | Runs the API with breakpoints and auto-reload |
| `API: tests (pytest)` | Runs the test suite under the debugger |
| `Frontend: Chrome` | Opens the explorer in Chrome with JavaScript debugging |
| `Full stack: API + Chrome` | Both of the above together |

Frontend files are served straight from your disk with caching disabled, so **edit and refresh**. The backend reloads by itself when you edit files in `backend/app/`.

> **Tip:** inside the devcontainer the backend does *not* start by itself. F5 starts it. Until then, `/api/*` returns `502`.

### Option B: Docker Compose

```bash
docker compose -f compose.yaml -f compose.dev.yaml up --build    # start
docker compose -f compose.yaml -f compose.dev.yaml down          # stop
```

- App: http://localhost:8080
- API directly, bypassing nginx: http://localhost:8000/api/docs

### Option C: Backend only, without Docker

```bash
cd backend
uv sync                                                    # create .venv with all dependencies
uv run --env-file ../.env uvicorn app.main:app --reload    # http://127.0.0.1:8000/api/docs
```

### Tests and code quality

```bash
cd backend
uv run pytest --cov         # tests, with coverage (fails under 95%)
uv run ruff check .         # lint, including docstrings and type annotations
uv run ruff format .        # format
uv run mypy                 # strict type check of app/
```

Inside the devcontainer, run the same commands from `/workspace/backend`. The Python test panel in VS Code is preconfigured. The same four checks run in CI on every pull request ([.github/workflows/ci.yml](.github/workflows/ci.yml)).

No test touches the network: NASA is replaced by small fakes, and `backend/tests/fixtures/` holds real NASA responses so that a change of format on their side shows up as a failing test.

### Trying the API

```bash
curl http://localhost:8080/api/health
# {"status":"ok","version":"0.1.0"}

curl http://localhost:8080/api/scenes
# {"scenes":["aerosol-latest","fires-latest","pm25-latest","precipitation-latest"]}

curl http://localhost:8080/api/scenes/aerosol-latest/manifest.json
# The latest aerosol scene: time stamps, grid and one file per aerosol type.
# Returns 503 with a Retry-After header while the backend is still fetching from NASA
# (about half a minute after it starts).
```

On Windows PowerShell, use `curl.exe` (plain `curl` there is an alias for a different command).

### Offline data pipeline (optional)

The API builds its scenes by itself. `backend/geosfp/` and `backend/tools/` are for a different job: downloading a *past* GEOS-FP episode (for example the smoke of a large wildfire) and freezing it as a static scene, in the same format and with the same code the API uses. Their libraries (xarray, pydap, scipy) are in a separate dependency group that the API image does not install:

```bash
cd backend
uv run --group pipeline python -m tools.find_episode --help             # scan a period for the strongest days
uv run --group pipeline python -m tools.summarize_episode --help        # daily summary of that scan
uv run --group pipeline python -m tools.download_global_episode --help  # download the episode (NetCDF)
uv run --group pipeline python -m tools.build_scene --source data/raw/<file>.nc --scene-id <id>
uv run --group pipeline pytest                                          # also runs the pipeline tests
```

Downloads and outputs go to `backend/data/`, which is git-ignored.

### Adding dependencies

```bash
cd backend
uv add <package>            # runtime dependency
uv add --dev <package>      # development only
```

Commit `pyproject.toml` and `uv.lock` together. Rebuild the containers afterwards (in VS Code: **Dev Containers: Rebuild Container**).

## Deployment

### Production-like stack with Docker Compose

```bash
docker compose up --build -d
```

- Builds slim production images: the API runs as a non-root user without dev tools; the frontend is nginx (non-root) with gzip and cache headers.
- Only port `8080` is published, and only on `127.0.0.1`. The API is reachable only through nginx. To expose the app on your local network, remove `127.0.0.1:` from the `ports` entry in `compose.yaml`.
- Both containers have health checks and restart automatically.

### Configuration

Environment variables are read from `.env` (see [.env.example](.env.example)):

| Variable | Default | Used by | Description |
|---|---|---|---|
| `FRONTEND_PORT` | `8080` | Compose | Host port where the app is published |
| `LOG_LEVEL` | `info` | backend | Uvicorn log level: `critical`, `error`, `warning`, `info` or `debug` |
| `CORS_ORIGINS` | `[]` | backend | JSON list of origins allowed to call the API directly. Not needed when going through nginx. |
| `SCENE_STEPS` | `8` | backend | How many 3-hour steps each scene holds (8 = the last day, which the globe plays in a loop) |
| `SCENE_WARMUP` | `true` | backend | Start fetching the scenes at startup instead of on the first request |
| `PORT` | `8000` | backend image | API port inside the container (some platforms set it automatically) |
| `BACKEND_URL` | `http://backend:8000` | frontend image | Where nginx forwards `/api/*` |

No API keys are required: NASA SVS, GEOS-FP, GIBS and OpenFreeMap are open services. `SCENE_STEPS` accepts 1 to 24.

### Hosting

The app is currently run locally. Because the frontend only calls relative `/api` URLs, it can move to any host that serves the static site and routes `/api/*` to the API. The API should run as a single long-lived instance (see Architecture):

- **Any container host** (a VM with Docker Compose, Render, Fly.io…): deploy the two images as they are, with one API instance. The API image needs about 512 MB of memory or more while it decodes NASA's frames.
- **Serverless hosts (Vercel, Cloud Run scaled to zero):** the static site fits, but the API in its current form does not fit well: every cold start would rebuild the scenes from NASA. It would first need the built scenes stored outside the process. *Not set up.*
- **Supabase** cannot host the Python API (its Edge Functions run TypeScript on Deno). It could be added later as a database or for user accounts.

## Data sources and credits

- [NASA GIBS](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api): Blue Marble shaded relief and bathymetry
- [NASA Scientific Visualization Studio](https://svs.gsfc.nasa.gov/5151/): the Earth Information Center daily visualization *Particulate Matter (PM) 2.5* (GEOS-CF model)
- [NASA GMAO GEOS-FP](https://gmao.gsfc.nasa.gov/): aerosol optical depth by type (model analysis, every 3 hours), read through its public OPeNDAP service
- [NASA Earth Observatory](https://earthobservatory.nasa.gov/): *Earth at Night* (night lights)
- [OpenFreeMap](https://openfreemap.org/), [OpenMapTiles](https://openmaptiles.org/) and [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors: map labels and boundaries
- [MapLibre GL JS](https://maplibre.org/), [Three.js](https://threejs.org/), [Bootstrap](https://getbootstrap.com/), [FastAPI](https://fastapi.tiangolo.com/)
- [NASA Scientific Visualization Studio](https://svs.gsfc.nasa.gov/5113/): the Earth Information Center daily visualization *Active Fires As Observed by VIIRS*
- [NASA Scientific Visualization Studio](https://svs.gsfc.nasa.gov/4285/): the Earth Information Center visualization *Near Real-Time Global Precipitation from the Global Precipitation Measurement Constellation* (IMERG)
- Planned: live VIIRS fire detections ([NASA GIBS](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api), [FIRMS](https://firms.modaps.eosdis.nasa.gov/))
