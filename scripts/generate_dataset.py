import csv
import os
import random
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Ensure src directory is in path for consistency with other script entry points.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

_dotenv_path = find_dotenv(usecwd=True) or str(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(_dotenv_path, override=True)

SEED = 42
TOTAL_RUNS = 100
PORT_CHOICES = ["NLRTM", "BEANR", "DEHAM", "DEBRV"]
OUTPUT_COLUMNS = ["run_id", "total_teu", "closed_port", "capacity_multiplier", "alert_text"]


def build_rows() -> list[dict[str, str | int | float]]:
    random.seed(SEED)
    rows: list[dict[str, str | int | float]] = []

    for run_num in range(1, TOTAL_RUNS + 1):
        total_teu = random.randint(5000, 50000)
        closed_port = random.choice(PORT_CHOICES)
        capacity_multiplier = round(random.uniform(0.5, 1.2), 4)
        alert_text = f"Port of {closed_port} is closed. {total_teu} TEU must be rerouted."

        rows.append(
            {
                "run_id": f"{run_num:03d}",
                "total_teu": total_teu,
                "closed_port": closed_port,
                "capacity_multiplier": capacity_multiplier,
                "alert_text": alert_text,
            }
        )

    return rows


def main() -> None:
    root_dir = Path(__file__).resolve().parents[1]
    data_dir = root_dir / "data"
    output_path = data_dir / "scenarios_idwl_v1.csv"

    data_dir.mkdir(parents=True, exist_ok=True)

    rows = build_rows()
    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows)} scenarios at {output_path}")


if __name__ == "__main__":
    main()
