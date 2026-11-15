import csv
from collections import defaultdict
from pathlib import Path

SOURCE = Path("data/processed/episodes/brexttau_europe_2026-07.csv")


def main() -> None:
    days = defaultdict(list)
    with SOURCE.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            days[row["time_utc"][:10]].append(row)

    print("fecha        media_iberia  max_iberia  max_europa")
    for day, rows in sorted(days.items()):
        mean = sum(float(r["iberia_mean"]) for r in rows) / len(rows)
        iberia_max = max(float(r["iberia_max"]) for r in rows)
        europe_max = max(float(r["europe_max"]) for r in rows)
        print(f"{day}   {mean:11.4f}  {iberia_max:10.3f}  {europe_max:10.3f}")


if __name__ == "__main__":
    main()
