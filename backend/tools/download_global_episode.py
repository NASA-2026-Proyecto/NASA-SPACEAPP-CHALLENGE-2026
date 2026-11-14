from datetime import UTC, datetime
from pathlib import Path

from geosfp.episode import download_episode

START = datetime(2026, 7, 24, 1, 0, tzinfo=UTC)
END = datetime(2026, 7, 28, 23, 0, tzinfo=UTC)
VARIABLES = ["brexttau", "bcexttau", "duexttau", "suexttau", "ssexttau"]
OUT = Path("data/raw/geosfp_aer_global_1deg_20260724_20260728.nc")

if __name__ == "__main__":
    download_episode(START, END, VARIABLES, OUT, lat_stride=4, lon_stride=4)
