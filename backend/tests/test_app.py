import importlib
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import __version__
from app.factory import create_app, default_scenes
from app.services.aerosol_scene import AerosolSource
from app.services.scenes import SceneStore
from tests.conftest import make_settings
from tests.fakes import FakeGeosFp


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_docs_live_under_api_prefix(client):
    # nginx solo reenvía /api/*: la documentación tiene que estar ahí
    assert client.get("/api/docs").status_code == 200
    paths = client.get("/api/openapi.json").json()["paths"]
    assert {"/api/health", "/api/scenes", "/api/scenes/{scene_id}/manifest.json"} <= paths.keys()


def test_manifest_contract_is_published_in_openapi(client):
    schemas = client.get("/api/openapi.json").json()["components"]["schemas"]
    assert {"Manifest", "GridBlock", "TimeAxis", "SpeciesEntry", "Scale"} <= schemas.keys()
    assert set(schemas["Manifest"]["required"]) >= {"scene_id", "version", "time", "grid", "species"}


def test_no_cors_by_default(client):
    response = client.get("/api/health", headers={"Origin": "http://example.org"})
    assert "access-control-allow-origin" not in response.headers


def test_cors_when_configured():
    origin = "http://localhost:5500"
    client = TestClient(create_app(make_settings(cors_origins=[origin]), scenes={}))
    response = client.get("/api/health", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin


# --- Ajustes -----------------------------------------------------------------------


@pytest.mark.parametrize("steps", [0, -1, 25])
def test_scene_steps_out_of_range_are_rejected(steps):
    with pytest.raises(ValidationError, match="scene_steps"):
        make_settings(scene_steps=steps)


def test_settings_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("SCENE_STEPS", "4")
    monkeypatch.setenv("SCENE_WARMUP", "false")
    monkeypatch.setenv("CORS_ORIGINS", '["https://example.org"]')
    from app.config import Settings

    settings = Settings()
    assert (settings.scene_steps, settings.scene_warmup) == (4, False)
    assert settings.cors_origins == ["https://example.org"]


def test_explicit_settings_ignore_a_broken_environment(monkeypatch):
    # Los tests construyen sus ajustes a mano: el entorno de quien los ejecuta no los rompe
    monkeypatch.setenv("CORS_ORIGINS", "not-json")
    monkeypatch.setenv("SCENE_STEPS", "muchos")
    assert make_settings().scene_steps == 8


# --- Aplicación por defecto --------------------------------------------------------


def test_default_scenes_cover_the_three_sources(settings):
    stores = default_scenes(settings)
    assert sorted(stores) == ["aerosol-latest", "fires-latest", "pm25-latest"]
    assert all(store.scene_id == scene_id for scene_id, store in stores.items())


def test_main_exposes_the_application(monkeypatch):
    for name, value in {"CORS_ORIGINS": "[]", "SCENE_STEPS": "8", "SCENE_WARMUP": "false"}.items():
        monkeypatch.setenv(name, value)
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        module = importlib.import_module("app.main")
        assert isinstance(module.app, FastAPI)
        assert module.app.state.scenes.keys() == {"aerosol-latest", "fires-latest", "pm25-latest"}
    finally:
        get_settings.cache_clear()


def test_warmup_prepares_the_scenes_in_the_background_at_startup():
    store = SceneStore(AerosolSource(FakeGeosFp().client(), steps=2))
    app = create_app(make_settings(scene_warmup=True), scenes={"aerosol-latest": store})

    with TestClient(app) as client:  # entrar en el contexto ejecuta el arranque
        deadline = time.monotonic() + 5
        while store.get() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert client.get("/api/scenes/aerosol-latest/manifest.json").status_code == 200


def test_without_warmup_nothing_is_fetched_until_the_first_request():
    nasa = FakeGeosFp()
    store = SceneStore(AerosolSource(nasa.client(), steps=2), spawn=lambda task: None)
    app = create_app(make_settings(scene_warmup=False), scenes={"aerosol-latest": store})

    with TestClient(app):
        assert nasa.requests == []
