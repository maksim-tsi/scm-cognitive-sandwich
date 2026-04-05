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
EVENT_CHOICES = ["TOTAL_CLOSURE", "SEVERE_CONGESTION", "OPERATIONAL_RESTRICTION"]
EVENT_TEMPLATES = {
    "TOTAL_CLOSURE": (
        "{port} is completely inaccessible due to a 48-hour labor strike. "
        "All operations suspended immediately."
    ),
    "SEVERE_CONGESTION": (
        "{port} reports 92% yard utilization. Severe congestion at terminal gates. "
        "Recommended throughput capped at 20% to prevent total gridlock."
    ),
    "OPERATIONAL_RESTRICTION": (
        "{port} maintenance alert: Two STS cranes are offline for emergency repair. "
        "Berth capacity reduced by 50% for the next 72 hours."
    ),
}
OUTPUT_COLUMNS = [
    "run_id",
    "total_teu",
    "primary_port",
    "primary_event",
    "secondary_port",
    "secondary_event",
    "capacity_multiplier",
    "alert_text",
]


def build_rows() -> list[dict[str, str | int | float]]:
    random.seed(SEED)
    rows: list[dict[str, str | int | float]] = []

    for run_num in range(1, TOTAL_RUNS + 1):
        total_teu = random.randint(5000, 50000)
        primary_port = random.choice(PORT_CHOICES)
        primary_event = random.choice(EVENT_CHOICES)

        secondary_port = ""
        secondary_event = ""
        if random.random() < 0.3:
            candidate_ports = [port for port in PORT_CHOICES if port != primary_port]
            secondary_port = random.choice(candidate_ports)
            secondary_event = random.choice(EVENT_CHOICES)

        capacity_multiplier = round(random.uniform(0.5, 1.2), 4)

        primary_template = EVENT_TEMPLATES[primary_event].format(port=primary_port)
        secondary_template = (
            EVENT_TEMPLATES[secondary_event].format(port=secondary_port) if secondary_port else ""
        )
        alert_text = f"{total_teu} TEU must be rerouted. {primary_template}"
        if secondary_template:
            alert_text = f"{alert_text} {secondary_template}"

        rows.append(
            {
                "run_id": f"{run_num:03d}",
                "total_teu": total_teu,
                "primary_port": primary_port,
                "primary_event": primary_event,
                "secondary_port": secondary_port,
                "secondary_event": secondary_event,
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
