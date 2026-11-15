"""El script que fija un episodio como escena estática (necesita el grupo `pipeline`)."""

import hashlib
import json

import numpy as np
import pytest

xr = pytest.importorskip("xarray", reason="requiere `uv run --group pipeline pytest`")
from tools.build_scene import scene_from_dataset, write_scene  # noqa: E402

STAMPS = ["2026-07-24T01:30Z", "2026-07-24T04:30Z", "2026-07-24T07:30Z"]


def episode(variables=("duexttau", "brexttau"), stamps=STAMPS) -> "xr.Dataset":
    """Un episodio pequeño con la forma que escribe `geosfp.episode.download_episode`."""
    lat = np.array([34.0, 35.0, 36.0, 37.0])
    lon = np.array([-10.0, -8.75, -7.5, -6.25, -5.0])
    data = {}
    for order, name in enumerate(variables):
        values = np.arange(3 * 4 * 5, dtype="float32").reshape(3, 4, 5) / 100 + order
        data[name] = (("step", "lat", "lon"), values, {"long_name": f" {name} optical depth "})
    return xr.Dataset(
        data,
        coords={"step": np.arange(3), "lat": lat, "lon": lon},
        attrs={
            "time_stamps_utc": ",".join(stamps),
            "product": "GEOS FP tavg3_2d_aer_Nx",
            "source_dataset": "https://opendap.nccs.nasa.gov/dods/x",
            "data_kind": "unverified",
        },
    )


def test_scene_has_the_same_format_as_the_api_scenes():
    scene = scene_from_dataset(episode(), "smoke-test")
    manifest = scene.manifest.model_dump(exclude_none=True)

    assert (manifest["schema_version"], manifest["kind"], manifest["scene_id"]) == (
        2,
        "grid-series",
        "smoke-test",
    )
    assert scene.version == "20260724T0730Z"
    assert manifest["time"] == {
        "steps": 3,
        "step_minutes": 180,
        "stamps_utc": STAMPS,
        "note": manifest["time"]["note"],
    }
    assert (manifest["grid"]["n_lat"], manifest["grid"]["n_lon"]) == (4, 5)
    assert manifest["provenance"] == {
        "provider": "NASA GMAO",
        "product": "GEOS FP tavg3_2d_aer_Nx",
        "source_dataset": "https://opendap.nccs.nasa.gov/dods/x",
        "data_kind": "unverified",
    }

    # Solo las especies presentes en el archivo, con su nombre de escena
    assert set(manifest["species"]) == {"dust", "brown_carbon"}
    dust = manifest["species"]["dust"]
    data = scene.files["dust.f32"]
    assert len(data) == 3 * 4 * 5 * 4
    assert dust["sha256"] == hashlib.sha256(data).hexdigest()
    assert dust["file"] == "20260724T0730Z/dust.f32"
    assert dust["long_name"] == "duexttau optical depth"
    assert dust["min"] == 0.0 and dust["max"] == pytest.approx(0.59)
    assert dust["display_scale_max"] == pytest.approx(0.584, abs=0.001)  # percentil 99


def test_values_keep_step_lat_lon_order():
    scene = scene_from_dataset(episode(), "smoke-test")
    values = np.frombuffer(scene.files["dust.f32"], dtype="<f4").reshape(3, 4, 5)
    assert values[2, 1, 3] == pytest.approx((2 * 20 + 1 * 5 + 3) / 100)


@pytest.mark.parametrize(
    "broken, message",
    [
        (lambda ds: ds.assign_attrs(time_stamps_utc="2026-07-24T01:30Z"), "marcas de tiempo"),
        (lambda ds: ds.assign(duexttau=ds["duexttau"] - 1), "no finitos o negativos"),
        (lambda ds: ds.assign(duexttau=ds["duexttau"].where(ds["duexttau"] > 0.3)), "no finitos o negativos"),
        (lambda ds: ds.drop_vars(["duexttau", "brexttau"]), "ninguna de las especies"),
    ],
    ids=["marcas de menos", "valores negativos", "huecos", "sin especies"],
)
def test_bad_episodes_are_rejected(broken, message):
    with pytest.raises(ValueError, match=message):
        scene_from_dataset(broken(episode()), "smoke-test")


def test_scene_is_written_like_the_api_serves_it(tmp_path):
    scene = scene_from_dataset(episode(), "smoke-test")
    manifest_path = write_scene(scene, tmp_path / "smoke-test")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest == json.loads(scene.manifest.model_dump_json(exclude_none=True))
    for entry in manifest["species"].values():
        # El front pide `<carpeta de la escena>/<file>`: el archivo tiene que estar ahí
        data = (manifest_path.parent / entry["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
