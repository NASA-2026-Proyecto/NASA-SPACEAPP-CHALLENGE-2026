import csv
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from backend.geosfp.client import load_in_chunks, nearest_index, open_remote, time_axis

START = datetime(2026, 7, 14, tzinfo=timezone.utc)
END = datetime(2026, 7, 31, tzinfo=timezone.utc)
VARIABLE = "brexttau"
EUROPE = {"lat": slice(35.0, 60.0), "lon": slice(-15.0, 20.0)}
IBERIA = {"lat": slice(36.0, 44.0), "lon": slice(-10.0, 4.0)}
FILL_LIMIT = 1.0e14
OUT = Path("data/processed/episodes/brexttau_europe_2026-07.csv")


def main() -> None:
    ds = open_remote()
    times = time_axis(ds["time"].attrs, ds.sizes["time"])
    first, last = nearest_index(times, START), nearest_index(times, END)
    steps = times[first:last + 1]
    print(f"Pasos: {len(steps)} | {steps[0]:%Y-%m-%d %H:%M} -> {steps[-1]:%Y-%m-%d %H:%M} UTC")

    europe = load_in_chunks(ds[VARIABLE].isel(time=slice(first, last + 1)).sel(EUROPE))
    print(f"Recorte Europa: {dict(europe.sizes)}")
    values = europe.values.astype("float64")
    bad = int((~np.isfinite(values) | (values >= FILL_LIMIT)).sum())
    print(f"Celdas no válidas: {bad} de {values.size}")
    if bad:
        raise SystemExit("Hay valores ausentes: revisar antes de continuar.")

    iberia = europe.sel(IBERIA).values.astype("float64")
    rows = []
    for i, moment in enumerate(steps):
        rows.append({
            "time_utc": f"{moment:%Y-%m-%dT%H:%M}Z",
            "europe_max": float(values[i].max()),
            "iberia_mean": float(iberia[i].mean()),
            "iberia_max": float(iberia[i].max()),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Tabla guardada en {OUT}")

    print("\nTop 8 pasos por media sobre Iberia:")
    for row in sorted(rows, key=lambda r: r["iberia_mean"], reverse=True)[:8]:
        print(f"  {row['time_utc']}  media={row['iberia_mean']:.4f}  "
              f"máx={row['iberia_max']:.4f}  Europa máx={row['europe_max']:.4f}")


if __name__ == "__main__":
    main()