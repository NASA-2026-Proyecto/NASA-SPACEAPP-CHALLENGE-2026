"""Convierte un episodio descargado (NetCDF) en una escena estática para la web.

La API prepara sola las escenas "en vivo"; este script sirve para fijar un episodio
concreto (por ejemplo, el humo de un gran incendio) como escena que no cambia. Usa el
mismo formato y las mismas funciones que la API (`app.services.scenes`), así que el
front la carga igual.

Uso, desde backend/ (el NetCDF lo genera `tools.download_global_episode`):

    uv run --group pipeline python -m tools.build_scene --source data/raw/episodio.nc --scene-id mi-escena

Escribe `<out-dir>/<scene-id>/manifest.json` y `<out-dir>/<scene-id>/<versión>/<especie>.f32`.
"""

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import xarray as xr

from app.schemas import ProvenanceValue, SpeciesEntry
from app.services.scenes import Scene, build_manifest, encode_species, time_axis, version_of
from geosfp.grid import describe_grid
from geosfp.timeline import STAMP_FORMAT

logger = logging.getLogger(__name__)

# El episodio que descarga `tools.download_global_episode` con sus valores por defecto
DEFAULT_SOURCE = Path("data/raw/geosfp_aer_global_1deg_20260724_20260728.nc")
DEFAULT_SCENE_ID = "global-aerosols-2026-07"
DEFAULT_OUT_DIR = Path("data/processed")
STEP_MINUTES = 180  # tavg3_2d_aer_Nx: medias de 3 horas
SCALE_PERCENTILE = 99.0
PROVENANCE_ATTRIBUTES = ("product", "source_dataset", "averaging", "subsampling", "data_kind", "units_note")

# Especie de la escena -> variable de GEOS-FP (espesor óptico a 550 nm)
SPECIES = {
    "brown_carbon": "brexttau",
    "black_carbon": "bcexttau",
    "dust": "duexttau",
    "sulfate": "suexttau",
    "sea_salt": "ssexttau",
    "total": "totexttau",
}


def scene_from_dataset(dataset: xr.Dataset, scene_id: str) -> Scene:
    """Construye la escena de un episodio ya descargado.

    Args:
        dataset: Episodio con variables de dimensiones (step, lat, lon) y el atributo
            `time_stamps_utc`, tal como lo escribe `geosfp.episode.download_episode`.
        scene_id: Identificador de la escena.

    Raises:
        ValueError: Si las marcas de tiempo no cuadran con los pasos, una variable no
            tiene la forma esperada o trae valores negativos o no finitos, o el archivo
            no contiene ninguna de las especies conocidas.
    """
    moments = [
        datetime.strptime(text, STAMP_FORMAT).replace(tzinfo=UTC)
        for text in str(dataset.attrs["time_stamps_utc"]).split(",")
    ]
    n_steps = int(dataset.sizes["step"])
    if len(moments) != n_steps:
        raise ValueError("El número de marcas de tiempo no coincide con los pasos.")
    lat, lon = dataset["lat"].values, dataset["lon"].values
    expected = (n_steps, lat.size, lon.size)
    version = version_of(moments[-1])

    files: dict[str, bytes] = {}
    species: dict[str, SpeciesEntry] = {}
    for key, variable in SPECIES.items():
        if variable not in dataset.data_vars:
            logger.info("%s: no está en el archivo, se omite.", key)
            continue
        values = np.ascontiguousarray(dataset[variable].values, dtype=np.float32)
        if values.shape != expected:
            raise ValueError(f"{variable}: forma {values.shape}, se esperaba {expected}.")
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"{variable}: contiene valores no finitos o negativos.")
        files[f"{key}.f32"], species[key] = encode_species(
            version,
            key,
            values,
            source_variable=variable,
            long_name=str(dataset[variable].attrs.get("long_name", "")).strip() or None,
            unit="dimensionless",
            display_scale_max=float(f"{np.percentile(values, SCALE_PERCENTILE):.3g}"),
            display_scale_method=f"p{SCALE_PERCENTILE:g} over all steps and cells of this scene",
        )
    if not species:
        raise ValueError("El archivo no contiene ninguna de las especies conocidas.")

    provenance: dict[str, ProvenanceValue] = {"provider": "NASA GMAO"}
    provenance.update(
        {name: str(dataset.attrs[name]) for name in PROVENANCE_ATTRIBUTES if name in dataset.attrs}
    )
    manifest = build_manifest(
        scene_id=scene_id,
        version=version,
        layer="aerosols",
        provenance=provenance,
        time=time_axis(
            moments,
            step_minutes=STEP_MINUTES,
            note="3-hour time averages; the meaning of each stamp (start or center) is not verified.",
        ),
        grid=describe_grid(lat, lon),
        species=species,
    )
    return Scene(version=version, manifest=manifest, files=files)


def write_scene(scene: Scene, folder: Path) -> Path:
    """Escribe la escena en `folder` con la misma estructura con que la sirve la API.

    Returns:
        La ruta del manifiesto.
    """
    values_folder = folder / scene.version
    values_folder.mkdir(parents=True, exist_ok=True)
    for name, data in scene.files.items():
        (values_folder / name).write_bytes(data)
    manifest_path = folder / "manifest.json"
    manifest_path.write_text(scene.manifest.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
    return manifest_path


def main() -> None:
    """Lee los argumentos, construye la escena y la guarda."""
    parser = argparse.ArgumentParser(description="Convierte una serie NetCDF en una escena para la web.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="NetCDF del episodio")
    parser.add_argument("--scene-id", default=DEFAULT_SCENE_ID, help="identificador de la escena")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="carpeta de salida")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    with xr.open_dataset(args.source, engine="scipy", decode_times=False) as dataset:
        scene = scene_from_dataset(dataset, args.scene_id)
    manifest_path = write_scene(scene, args.out_dir / args.scene_id)

    for key, entry in scene.manifest.species.items():
        megabytes = len(scene.files[f"{key}.f32"]) / 1e6
        print(
            f"{key:13s} min={entry.min:.4g} max={entry.max:.4g} "
            f"escala={entry.display_scale_max} archivo={megabytes:.2f} MB"
        )
    print(f"\nEscena guardada en {manifest_path.parent}")


if __name__ == "__main__":
    main()
