import hashlib
from datetime import UTC, datetime

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.geosfp import parse_dods
from app.services.scenes import SPECIES, SceneStore
from tests.fakes import FakeGeosFp, dods

MANIFEST = "/api/scenes/aerosol-latest/manifest.json"


@pytest.fixture
def nasa() -> FakeGeosFp:
    return FakeGeosFp(n_times=10)


@pytest.fixture
def store(nasa) -> SceneStore:
    return SceneStore(nasa.client(), steps=3)


@pytest.fixture
def api(store) -> TestClient:
    return TestClient(create_app(Settings(cors_origins=[]), scenes=store))


# --- Cliente GEOS-FP ---------------------------------------------------------------


def test_grid_is_read_from_the_das(nasa):
    grid = nasa.client().grid()
    assert (grid.lat_min, grid.lat_step, grid.n_lat) == (-90.0, 22.5, 9)
    assert (grid.lon_min, grid.lon_step, grid.n_lon) == (-180.0, 22.5, 16)
    assert grid.n_times == 10
    assert grid.time_at(0) == datetime(2026, 2, 27, 1, 30, tzinfo=UTC)
    assert grid.time_at(9) == datetime(2026, 2, 28, 4, 30, tzinfo=UTC)


def test_dods_is_decoded_as_little_endian_float32():
    original = np.arange(24, dtype="float32").reshape(2, 3, 4) / 7
    decoded = parse_dods(dods(original), (2, 3, 4))
    assert decoded.dtype == np.dtype("<f4")
    assert np.array_equal(decoded, original)


def test_dods_with_unexpected_size_is_rejected():
    with pytest.raises(ValueError, match="se esperaban"):
        parse_dods(dods(np.zeros(5, dtype="float32")), (2, 3))


# --- Escena ------------------------------------------------------------------------


def test_scene_matches_the_frontend_format(store):
    store.refresh()
    scene = store.get()
    manifest = scene.manifest

    # Lo que valida frontend/js/data/scene-data.js
    assert manifest["schema_version"] == 2
    assert manifest["kind"] == "grid-series"
    assert manifest["time"]["steps"] == len(manifest["time"]["stamps_utc"]) == 3
    assert manifest["time"]["stamps_utc"] == [
        "2026-02-27T22:30Z",
        "2026-02-28T01:30Z",
        "2026-02-28T04:30Z",
    ]
    assert manifest["time"]["step_minutes"] == 180

    grid = manifest["grid"]  # 1 de cada 4 celdas de una malla de 9 x 16
    assert (grid["n_lat"], grid["n_lon"]) == (3, 4)
    assert (grid["lat_min"], grid["lat_step"]) == (-90.0, 90.0)
    assert (grid["lon_min"], grid["lon_step"]) == (-180.0, 90.0)
    assert grid["lon_periodic"] is True

    assert set(manifest["species"]) == set(SPECIES)
    expected_bytes = 3 * 3 * 4 * 4
    for key, entry in manifest["species"].items():
        data = scene.files[f"{key}.f32"]
        assert len(data) == expected_bytes
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
        assert entry["file"] == f"{scene.version}/{key}.f32"
        assert entry["display_scale_max"] == SPECIES[key][1]


def test_values_keep_step_lat_lon_order(store):
    store.refresh()
    scene = store.get()
    values = np.frombuffer(scene.files["dust.f32"], dtype="<f4").reshape(3, 3, 4)
    # El falso codifica: len("duexttau") + paso*0.1 + fila*0.01 + columna*0.0001
    # Último paso (9), segunda latitud (fila 4 de la malla original), tercera longitud (columna 8)
    assert values[2, 1, 2] == pytest.approx(8 + 0.9 + 0.04 + 0.0008, abs=1e-5)


def test_one_request_per_species_and_none_when_nothing_changed(store, nasa):
    store.refresh()
    assert len(nasa.requests) == 1 + len(SPECIES)  # .das + una por especie

    nasa.requests.clear()
    version = store.get().version
    store.refresh()  # mismo paso: solo se consulta el .das
    assert len(nasa.requests) == 1
    assert store.get().version == version


def test_new_step_replaces_the_scene_and_keeps_the_previous_files(store, nasa):
    store.refresh()
    old = store.get()

    nasa.n_times = 11
    store.refresh()
    new = store.get()

    assert new.version != old.version
    assert new.manifest["time"]["stamps_utc"][-1] == "2026-02-28T07:30Z"
    assert store.file(old.version, "dust.f32") == old.files["dust.f32"]
    assert store.file(new.version, "dust.f32") == new.files["dust.f32"]


def test_failure_keeps_the_last_good_scene(store, nasa):
    store.refresh()
    good = store.get()

    nasa.fail = True
    nasa.n_times = 11
    store.refresh()

    assert store.get() is good
    assert "NASA no responde" in store.error


@pytest.mark.parametrize("bad", [float("nan"), 1.0e15, -0.5])
def test_invalid_values_are_not_published(store, nasa, bad):
    nasa.bad_value = bad
    store.refresh()
    assert store.get() is None
    assert "no válidos" in store.error


# --- API ---------------------------------------------------------------------------


def test_manifest_is_503_while_the_scene_is_not_ready(nasa):
    nasa.fail = True
    store = SceneStore(nasa.client())
    store.refresh()
    api = TestClient(create_app(Settings(cors_origins=[]), scenes=store))

    response = api.get(MANIFEST)
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert response.json()["status"] == "building"


def test_manifest_and_files_are_served(api, store):
    store.refresh()

    response = api.get(MANIFEST)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    manifest = response.json()

    for entry in manifest["species"].values():
        file = api.get(f"/api/scenes/aerosol-latest/{entry['file']}")
        assert file.status_code == 200
        assert file.headers["content-type"] == "application/octet-stream"
        assert "immutable" in file.headers["cache-control"]
        assert hashlib.sha256(file.content).hexdigest() == entry["sha256"]


@pytest.mark.parametrize("path", ["20000101T0000Z/dust.f32", "{version}/unknown.f32"])
def test_unknown_version_or_species_is_404(api, store, path):
    store.refresh()
    path = path.format(version=store.get().version)
    assert api.get(f"/api/scenes/aerosol-latest/{path}").status_code == 404
