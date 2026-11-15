# syntax=docker/dockerfile:1
# Front de Earth Jukebox (HTML/CSS/JS estático, sin build) servido con nginx sin root.
# nginx también reenvía /api/* al backend. Contexto de build: frontend/
#   docker build --target prod -t earth-jukebox-frontend .
#   docker build --target dev  -t earth-jukebox-frontend:dev .

ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:1.30.5-alpine

# ---------- base: común a dev y prod ----------
FROM ${NGINX_IMAGE} AS base

# NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1: el entrypoint lee /etc/resolv.conf y exporta
# NGINX_LOCAL_RESOLVERS, que usa la plantilla para volver a resolver el backend.
ENV BACKEND_URL=http://backend:8000 \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1

COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:8080/ || exit 1

# ---------- dev: los ficheros del front se montan desde el host (compose.dev.yaml) ----------
FROM base AS dev
COPY nginx/dev.conf /etc/nginx/snippets/mode.conf

# ---------- prod: imagen autocontenida con el front ----------
FROM base AS prod
COPY nginx/prod.conf /etc/nginx/snippets/mode.conf
# Lista explícita: Dockerfile, nginx/ y demás ficheros de la carpeta no se publican
COPY index.html explorer.html /usr/share/nginx/html/
COPY css /usr/share/nginx/html/css
COPY js /usr/share/nginx/html/js
COPY assets /usr/share/nginx/html/assets
