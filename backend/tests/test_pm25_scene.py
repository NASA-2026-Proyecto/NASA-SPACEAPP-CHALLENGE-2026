import hashlib
from io import BytesIO

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.factory import create_app
from app.services.colour_scale import (
    downsample,
    drop_islands,
    fill_small_gaps,
    gradient_from_colour_bar,
    invert_gradient,
    reject_thin_features,
)
from app.services.pm25_scene import SCALE_MAX, SCALE_MIN, Pm25Source
from app.services.scenes import SceneStore
from tests.conftest import make_settings
from tests.fake_svs import (
    COAST_COLUMN,
    HEIGHT,
    RAMP,
    WIDTH,
    FakeSvs,
    colour_bar_png,
    frame_png,
    true_position,
)


@pytest.fixture
def svs() -> FakeSvs:
    return FakeSvs()


@pytest.fixture
def store(svs) -> SceneStore:
    return SceneStore(Pm25Source(svs.client(), steps=1, factor=2))


def to_ugm3(position):
    return SCALE_MIN * (SCALE_MAX / SCALE_MIN) ** position


# --- De color a valor --------------------------------------------------------------


def test_ramp_is_read_from_the_colour_bar_without_its_border():
    ramp = gradient_from_colour_bar(Image.open(BytesIO(colour_bar_png())))
    assert np.array_equal(ramp, RAMP)


def test_colours_convert_back_to_positions():
    frame = Image.open(BytesIO(frame_png()))
    position = invert_gradient(frame, RAMP)
    truth = true_position()

    assert position.shape == (HEIGHT, WIDTH)
    data = np.isfinite(position)
    assert np.allclose(position[data], truth[data], atol=1 / 255)
    # Lo que no es dato (logotipo y costa) no se convierte en un valor
    assert not data[:8, :12].any()
    assert not data[:, COAST_COLUMN].any()
    assert data.mean() > 0.9


def test_downsample_averages_blocks_and_ignores_gaps():
    values = np.array([[1.0, 3.0, np.nan, np.nan], [5.0, np.nan, np.nan, np.nan]], dtype="float32")
    result = downsample(values, 2)
    assert result.shape == (1, 2)
    assert result[0, 0] == pytest.approx(3.0)  # media de 1, 3 y 5
    assert np.isnan(result[0, 1])  # un bloque sin datos sigue sin datos


def test_small_gaps_are_filled_but_large_ones_are_not():
    values = np.ones((9, 9), dtype="float32")
    values[:, 4] = np.nan  # línea fina
    assert np.isfinite(fill_small_gaps(values)).all()

    values = np.ones((9, 9), dtype="float32")
    values[2:7, 2:7] = np.nan  # hueco de 5 x 5
    filled = fill_small_gaps(values)
    assert np.isnan(filled[4, 4])  # el centro sigue vacío
    assert np.isfinite(filled[2, 2])  # el borde se estrecha una celda


def test_ramp_ignores_a_frame_wider_than_one_pixel():
    bar = np.zeros((20, 300, 4), dtype="uint8")
    bar[5:15, 19:279] = (255, 255, 255, 255)  # dos píxeles blancos opacos a cada lado
    bar[5:15, 21:277, :3] = RAMP[None, :, :]
    buffer = BytesIO()
    Image.fromarray(bar, "RGBA").save(buffer, format="PNG")
    ramp = gradient_from_colour_bar(Image.open(buffer))
    assert np.array_equal(ramp[-1], RAMP[-1])  # el extremo alto es de la rampa, no blanco
    assert len(ramp) >= len(RAMP) - 2


def test_line_blended_with_the_data_is_not_read_as_an_extreme_value():
    # Negro al 60 % sobre un naranja de mitad de rampa: un marrón oscuro, cercano al extremo alto
    blended = np.round(RAMP[120] * 0.4).astype("uint8")
    pixels = np.tile(RAMP[120], (4, 4, 1))
    pixels[:, 2] = blended
    position = invert_gradient(Image.fromarray(pixels, "RGB"), RAMP)
    assert np.isnan(position[:, 2]).all()
    assert np.allclose(position[:, 0], 120 / 255, atol=1 / 255)


def test_islands_of_data_inside_a_gap_are_dropped():
    values = np.ones((30, 30), dtype="float32")
    values[5:20, 5:20] = np.nan  # un rótulo...
    values[11:13, 10:14] = 7.0  # ...con una "letra" que parece dato
    values[:, 25] = np.nan  # y una línea fina en otra parte
    result = drop_islands(values)
    assert np.isnan(result[11:13, 10:14]).all()
    assert (
        np.isfinite(result[:, 24]).all() and np.isfinite(result[:, 26]).all()
    )  # junto a la línea no se pierde nada
    assert np.isfinite(result[25, 2])


def test_thin_bright_lines_are_removed_but_wider_features_are_kept():
    position = np.full((20, 20), 0.2, dtype="float32")
    position[:, 5] = 0.8  # una frontera de 1 píxel
    position[12, :] = 0.7  # y otra horizontal
    position[2:6, 12:16] = 0.9  # un foco real de 4 x 4
    position[16:18, 16] = np.nan  # un hueco previo no estorba

    result = reject_thin_features(position)
    assert np.isnan(result[:, 5]).all() and np.isnan(result[12, :]).all()
    assert np.array_equal(result[2:6, 12:16], position[2:6, 12:16])
    assert result[8, 8] == pytest.approx(0.2)


# --- Escena ------------------------------------------------------------------------


def test_scene_matches_the_frontend_format(store):
    store.refresh()
    scene = store.get()
    manifest = scene.manifest.model_dump(exclude_none=True)

    assert manifest["schema_version"] == 2
    assert manifest["kind"] == "grid-series"
    assert manifest["scene_id"] == "pm25-latest"
    assert manifest["time"]["steps"] == len(manifest["time"]["stamps_utc"]) == 1
    assert manifest["time"]["stamps_utc"] == ["2026-11-14T07:00Z"]  # 02:00 -05:00 en UTC
    assert scene.version == "20261114T0700Z"

    grid = manifest["grid"]  # el fotograma de 64 x 32 se reduce a la mitad
    assert (grid["n_lat"], grid["n_lon"]) == (16, 32)
    assert (grid["lat_step"], grid["lon_step"]) == (11.25, 11.25)
    assert (grid["lat_min"], grid["lon_min"]) == (-84.375, -174.375)  # centros de celda
    assert grid["lon_periodic"] is True

    entry = manifest["species"]["pm25"]
    data = scene.files["pm25.f32"]
    assert len(data) == 1 * 16 * 32 * 4
    assert entry["sha256"] == hashlib.sha256(data).hexdigest()
    assert entry["file"] == f"{scene.version}/pm25.f32"
    assert entry["unit"] == "ug/m3"
    scale = entry["scale"]
    assert (scale["kind"], scale["min"], scale["max"]) == ("log", SCALE_MIN, SCALE_MAX)
    assert len(scale["ramp"]) == 17  # colores de la barra de la NASA, de menos a más
    assert scale["ramp"][0] == "#fff5d7" and scale["ramp"][-1] == "#6e1905"
    (frame_url,) = manifest["provenance"]["source_frames"]
    assert frame_url.endswith("00000003.png")  # el más reciente
    assert frame_url.startswith("https://")


def test_values_are_ugm3_from_south_to_north(store):
    store.refresh()
    values = np.frombuffer(store.get().files["pm25.f32"], dtype="<f4").reshape(16, 32)

    # Bloques de 2 x 2 píxeles; la fila 0 de la escena es el sur (última fila de la imagen)
    truth = true_position().reshape(16, 2, 32, 2).mean(axis=(1, 3))[::-1]
    # Se comparan las celdas con dato directo: ni la costa ni el borde del logotipo (rellenados)
    direct = np.ones_like(values, dtype=bool)
    direct[:, COAST_COLUMN // 2] = False
    direct[12:, :6] = False
    assert np.allclose(values[direct], to_ugm3(truth[direct]), rtol=0.05)

    assert values[0, 31] > values[15, 6]  # sureste, lo más contaminado; noroeste, lo más limpio
    assert np.isfinite(values[:, COAST_COLUMN // 2]).all()  # la costa no deja hueco
    assert np.isnan(values[14, 2])  # bajo el logotipo no hay dato
    assert np.nanmin(values) >= SCALE_MIN and np.nanmax(values) <= SCALE_MAX


def test_series_takes_spaced_frames_ending_at_the_newest():
    svs = FakeSvs(frames=10)
    store = SceneStore(Pm25Source(svs.client(), steps=3, frame_spacing=4, factor=4))
    store.refresh()
    scene = store.get()
    manifest = scene.manifest.model_dump(exclude_none=True)

    # De 10 fotogramas horarios, uno de cada 4 acabando en el último: 2, 6 y 10
    used = [url.rsplit("/", 1)[1] for url in manifest["provenance"]["source_frames"]]
    assert used == ["00000002.png", "00000006.png", "00000010.png"]

    time = manifest["time"]
    assert (time["steps"], time["step_minutes"]) == (3, 240)
    assert time["stamps_utc"] == ["2026-11-13T23:00Z", "2026-11-14T03:00Z", "2026-11-14T07:00Z"]

    grid = manifest["grid"]  # 64 x 32 píxeles en bloques de 4
    assert (grid["n_lat"], grid["n_lon"]) == (8, 16)
    values = np.frombuffer(scene.files["pm25.f32"], dtype="<f4").reshape(3, 8, 16)
    # Cada fotograma del falso está más contaminado que el anterior: el orden es cronológico
    cell = values[:, 2, 12]
    assert cell[0] < cell[1] < cell[2]


def test_series_uses_what_exists_when_there_are_few_frames():
    store = SceneStore(Pm25Source(FakeSvs(frames=3).client(), steps=8, frame_spacing=3))
    store.refresh()
    manifest = store.get().manifest.model_dump(exclude_none=True)
    assert manifest["time"]["steps"] == 1
    assert manifest["provenance"]["source_frames"][0].endswith("00000003.png")


def test_scene_is_rebuilt_only_when_nasa_publishes_a_new_render(store, svs):
    store.refresh()
    first = store.get()
    svs.requests.clear()

    store.refresh()  # misma fecha de actualización: solo se consulta la página
    assert len(svs.requests) == 1
    assert store.get() is first

    svs.updated = "2026-11-15T02:00:40-05:00"
    store.refresh()
    assert store.get().version == "20261115T0700Z"
    assert store.file(first.version, "pm25.f32") == first.files["pm25.f32"]


def test_unreadable_frame_is_not_published(store, svs):
    buffer = BytesIO()
    Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 255)).save(buffer, format="PNG")  # azul: fuera de la rampa
    svs.broken_frame = buffer.getvalue()
    store.refresh()
    assert store.get() is None
    assert "Solo se pudo leer" in store.error


def test_failure_keeps_the_last_good_scene(store, svs):
    store.refresh()
    good = store.get()
    svs.fail = True
    store.refresh()
    assert store.get() is good
    assert "SVS no responde" in store.error


# --- API ---------------------------------------------------------------------------


def test_scene_is_served_by_the_same_endpoints(store):
    store.refresh()
    api = TestClient(create_app(make_settings(), scenes={"pm25-latest": store}))

    assert api.get("/api/scenes").json() == {"scenes": ["pm25-latest"]}
    manifest = api.get("/api/scenes/pm25-latest/manifest.json").json()
    entry = manifest["species"]["pm25"]
    file = api.get(f"/api/scenes/pm25-latest/{entry['file']}")
    assert file.status_code == 200
    assert hashlib.sha256(file.content).hexdigest() == entry["sha256"]

    assert api.get("/api/scenes/unknown/manifest.json").status_code == 404
