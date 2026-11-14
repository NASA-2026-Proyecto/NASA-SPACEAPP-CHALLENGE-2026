from pathlib import Path

from geosfp.normalize import normalize

SOURCE = Path("data/raw/geosfp_aer_iberia_20261101T0430Z.nc")
DESTINATION = Path("data/processed/aerosols_iberia_20261101T0430Z.json")


def main() -> None:
    document = normalize(SOURCE, DESTINATION)
    grid = document["grid"]
    print(f"Creado {DESTINATION} ({DESTINATION.stat().st_size / 1024:.1f} KB)")
    print(f"Rejilla: {grid['n_lat']} x {grid['n_lon']}")
    for key, item in document["species"].items():
        print(f"  {key}: min={item['min']:.4g} max={item['max']:.4g} n={len(item['values'])}")


if __name__ == "__main__":
    main()
