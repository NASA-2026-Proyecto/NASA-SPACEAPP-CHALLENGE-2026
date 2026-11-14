# syntax=docker/dockerfile:1
# API de Earth Jukebox (FastAPI) gestionada con uv. Contexto de build: backend/
#   docker build --target prod -t earth-jukebox-backend .
#   docker build --target dev  -t earth-jukebox-backend:dev .

ARG PYTHON_VERSION=3.13
ARG UV_VERSION=0.11.8

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ---------- base: Python del sistema + uv ----------
FROM python:${PYTHON_VERSION}-slim-trixie AS base

COPY --from=uv /uv /uvx /usr/local/bin/

# UV_PYTHON_DOWNLOADS=0: usar el Python de la imagen, nunca descargar otro.
# UV_LINK_MODE=copy: la caché de uv vive en un montaje de BuildKit, copiar en vez de enlazar.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PYTHON_DOWNLOADS=0 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# ---------- builder: dependencias de producción en /app/.venv ----------
FROM base AS builder

WORKDIR /app

# Solo pyproject + lock: esta capa se reutiliza mientras no cambien las dependencias.
# El proyecto no es un paquete (package = false), así que basta con instalar dependencias.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# ---------- prod: imagen final mínima, sin uv ni herramientas de desarrollo ----------
FROM python:${PYTHON_VERSION}-slim-trixie AS prod

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/app/.venv/bin:$PATH \
    PORT=8000 \
    LOG_LEVEL=info

RUN useradd --system --no-create-home --uid 10001 app

WORKDIR /app

# El código queda en propiedad de root: el usuario de la app solo puede leerlo
COPY --from=builder /app/.venv /app/.venv
COPY app ./app

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/health', timeout=2)"]

# $PORT lo fijan algunas plataformas (Render, Cloud Run...); por defecto 8000.
# --proxy-headers: la API va detrás de nginx, que añade X-Forwarded-*; en la red de
# Compose solo nginx llega al backend (no publica puertos), de ahí el "*".
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\" --log-level \"$LOG_LEVEL\" --proxy-headers --forwarded-allow-ips='*'"]

# ---------- dev: dependencias de desarrollo, código montado desde el host ----------
FROM base AS dev

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl procps \
    && rm -rf /var/lib/apt/lists/*

# Usuario sin privilegios para trabajar (y para el devcontainer del paso siguiente)
ARG USERNAME=vscode
ARG USER_UID=1000
RUN useradd --create-home --shell /bin/bash --uid ${USER_UID} ${USERNAME}

# El venv vive FUERA del repo montado: así no choca con un .venv creado en Windows.
# Sin precompilar: en desarrollo solo ralentizaría cada "uv run" (~1000 ficheros).
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    UV_COMPILE_BYTECODE=0

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project \
    && chown -R ${USERNAME}:${USERNAME} /opt/venv

USER ${USERNAME}
WORKDIR /workspace/backend
EXPOSE 8000

# --reload-dir app: vigilar solo el código (con sondeo, vigilar todo backend/ sería caro)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "app"]
