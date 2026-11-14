# Earth Jukebox

**Listen to our planet.** An interactive 3D globe that turns NASA Earth observation data into sound.

Project for the **NASA Space Apps Challenge 2026**. Not an official NASA product.

## The challenge

NASA's **Earth Information Center (EIC)** publishes compelling visualizations of our planet's vital signs: global temperature, sea level, ice, wildfires and more. They are almost entirely visual (maps, images and charts), which leaves out people who cannot rely on sight, including people who are blind or have low vision.

**Our goal:** build an *Earth Jukebox*, an immersive, real-time **sonification** experience that translates real Earth data from NASA and the EIC into sound. Pitch, rhythm and volume follow the data, so anyone can *hear* how the planet is changing, not only see it.

## How it works

1. **Observe:** Earth observation layers are drawn on a 3D globe (NASA GIBS imagery).
2. **Explore:** rotate the globe, switch layers on and off, and click any point on Earth.
3. **Listen:** each variable becomes sound. Higher values give a higher pitch and more intensity.

### Current status (prototype)

| Feature | Status |
|---|---|
| 3D globe with NASA Blue Marble basemap, night lights and a test aerosol layer (MODIS Terra) | ✅ Working |
| Sonification player (pitch, level, live waveform) | ✅ Working, with a **simulated** signal |
| Click on the globe → coordinates sent to the API → reply shown on the globe | ✅ Working |
| API: `/api/health`, `/api/point` | ✅ Working |
| Real data per point (NASA POWER rain, temperature, wind and humidity; NASA EONET events) | 🔜 Next: migrating from an earlier prototype |
| Wildfires and precipitation layers on the globe | 🔜 Pending |

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
                    │ backend · FastAPI (uv)    │  stateless, configured by env vars
                    │   /api/health, /api/point │
                    └──────────────────────────┘
```

- **Two images served from one origin.** nginx serves the site and forwards `/api/*` to the API, so the frontend only uses relative URLs (`/api/...`). The same frontend code works locally, in Docker and on any host that can route `/api` to the backend.
- **Stateless backend** with its configuration in environment variables, ready to scale out or to run as a serverless function.
- **Self-documenting API:** interactive OpenAPI docs at `/api/docs`.

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
  app/                   main.py, config.py, schemas.py, api/ (routes)
  tests/                 pytest
  pyproject.toml  uv.lock  Dockerfile
tools/                 One-off scripts (night-lights tile generator)
compose.yaml           Production-like stack
compose.dev.yaml       Development overrides (live code, auto-reload)
.devcontainer/         VS Code devcontainer (backend + frontend)
.vscode/launch.json    Debug configurations (F5)
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
uv run pytest               # tests
uv run ruff check .         # lint
uv run ruff format .        # format
```

Inside the devcontainer, run the same commands from `/workspace/backend`. The Python test panel in VS Code is preconfigured.

### Trying the API

```bash
curl http://localhost:8080/api/health
# {"status":"ok","version":"0.1.0"}

curl "http://localhost:8080/api/point?lat=40.4168&lon=-3.7038"
# {"ok":true,"lat":40.4168,"lon":-3.7038,"message":"Coordenadas recibidas: lat 40.4168, lon -3.7038"}

curl "http://localhost:8080/api/point?lat=91&lon=0"
# 422 with detail "Input should be less than or equal to 90"
```

On Windows PowerShell, use `curl.exe` (plain `curl` there is an alias for a different command).

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
| `PORT` | `8000` | backend image | API port inside the container (some platforms set it automatically) |
| `BACKEND_URL` | `http://backend:8000` | frontend image | Where nginx forwards `/api/*` |

No API keys are required: NASA GIBS and OpenFreeMap are open services.

### Hosting

The app is currently run locally. Because the frontend only calls relative `/api` URLs and the backend is stateless, it can move to any host that serves the static site and routes `/api/*` to the API:

- **Any container host** (a VM with Docker Compose, Render, Fly.io, Google Cloud Run…): deploy the two images as they are.
- **Vercel:** serve `frontend/` as a static site. FastAPI runs as a Python function (`backend/app/main.py` exposes `app`, and Vercel reads `pyproject.toml` + `uv.lock`). A rewrite then sends `/api/*` to that function. *Not set up yet.*
- **Supabase** cannot host the Python API (its Edge Functions run TypeScript on Deno). It could be added later as a database or for user accounts.

## Data sources and credits

- [NASA GIBS](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api): Blue Marble shaded relief and bathymetry; MODIS Terra aerosol optical depth
- [NASA Earth Observatory](https://earthobservatory.nasa.gov/): *Earth at Night* (night lights)
- [OpenFreeMap](https://openfreemap.org/), [OpenMapTiles](https://openmaptiles.org/) and [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors: map labels and boundaries
- [MapLibre GL JS](https://maplibre.org/), [Three.js](https://threejs.org/), [Bootstrap](https://getbootstrap.com/), [FastAPI](https://fastapi.tiangolo.com/)
- Planned: [NASA POWER](https://power.larc.nasa.gov/) (daily climate variables) and [NASA EONET](https://eonet.gsfc.nasa.gov/) (natural events)
