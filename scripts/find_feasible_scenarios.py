import argparse
import csv
from pathlib import Path

ALL_PORTS = ["NLRTM", "BEANR", "DEHAM", "DEBRV"]
BASE_CAPACITY = 15000

EVENT_TOTAL_CLOSURE = "TOTAL_CLOSURE"
EVENT_SEVERE_CONGESTION = "SEVERE_CONGESTION"
EVENT_OPERATIONAL_RESTRICTION = "OPERATIONAL_RESTRICTION"


def compute_total_available_capacity(row: dict[str, str]) -> int:
    multiplier = float(row["capacity_multiplier"])
    capacities = {port: int(BASE_CAPACITY * multiplier) for port in ALL_PORTS}

    disruptions = [
        (row["primary_port"].strip().upper(), row["primary_event"].strip().upper()),
        (row.get("secondary_port", "").strip().upper(), row.get("secondary_event", "").strip().upper()),
    ]

    for port, event in disruptions:
        if not port or not event:
            continue
        if event == EVENT_TOTAL_CLOSURE:
            capacities[port] = 0
        elif event == EVENT_SEVERE_CONGESTION:
            capacities[port] = int(BASE_CAPACITY * 0.2)
        elif event == EVENT_OPERATIONAL_RESTRICTION:
            capacities[port] = int(BASE_CAPACITY * 0.5)

    return sum(max(value, 0) for value in capacities.values())


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def filter_candidates(
    rows: list[dict[str, str]],
    max_teu: int,
    min_multiplier: float,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for row in rows:
        total_teu = int(row["total_teu"])
        multiplier = float(row["capacity_multiplier"])
        if total_teu >= max_teu:
            continue
        if multiplier <= min_multiplier:
            continue

        total_available = compute_total_available_capacity(row)
        candidates.append(
            {
                "run_id": str(row["run_id"]).zfill(3),
                "total_teu": total_teu,
                "capacity_multiplier": multiplier,
                "primary_event": row["primary_event"],
                "secondary_event": row.get("secondary_event", ""),
                "total_available": total_available,
                "is_feasible": total_available >= total_teu,
            }
        )

    return sorted(candidates, key=lambda item: item["run_id"])


def print_table(title: str, rows: list[dict[str, str]]) -> None:
    print(title)
    if not rows:
        print("  No candidates found")
        print()
        return

    print(
        "  run_id  total_teu  multiplier  primary_event            "
        "secondary_event          total_available  feasible"
    )
    for row in rows:
        print(
            f"  {row['run_id']:>6}  {row['total_teu']:>9}  {row['capacity_multiplier']:>10.4f}  "
            f"{row['primary_event']:<22} {row['secondary_event']:<22} {row['total_available']:>15}  "
            f"{str(row['is_feasible']):>8}"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Find feasible scenario cohorts for targeted batch runs.")
    parser.add_argument(
        "--scenarios-path",
        type=Path,
        default=Path("data/scenarios_idwl_v1.csv"),
        help="Path to scenarios CSV",
    )
    parser.add_argument("--strict-max-teu", type=int, default=15000)
    parser.add_argument("--strict-min-multiplier", type=float, default=1.0)
    parser.add_argument("--relaxed-max-teu", type=int, default=20000)
    parser.add_argument("--relaxed-min-multiplier", type=float, default=1.0)
    args = parser.parse_args()

    rows = load_rows(args.scenarios_path)

    strict = filter_candidates(rows, args.strict_max_teu, args.strict_min_multiplier)
    strict_feasible = [row for row in strict if row["is_feasible"]]

    relaxed = filter_candidates(rows, args.relaxed_max_teu, args.relaxed_min_multiplier)
    relaxed_feasible = [row for row in relaxed if row["is_feasible"]]

    print_table(
        (
            "Strict filter candidates "
            f"(total_teu < {args.strict_max_teu}, capacity_multiplier > {args.strict_min_multiplier})"
        ),
        strict_feasible,
    )
    print_table(
        (
            "Relaxed filter candidates "
            f"(total_teu < {args.relaxed_max_teu}, capacity_multiplier > {args.relaxed_min_multiplier})"
        ),
        relaxed_feasible,
    )

    strict_ids = [row["run_id"] for row in strict_feasible]
    relaxed_ids = [row["run_id"] for row in relaxed_feasible]

    print("Strict feasible run_ids:", ",".join(strict_ids) if strict_ids else "<none>")
    print("Relaxed feasible run_ids:", ",".join(relaxed_ids) if relaxed_ids else "<none>")


if __name__ == "__main__":
    main()
