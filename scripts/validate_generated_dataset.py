import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"

ALLOWED_PORTS = {"NLRTM", "DEHAM", "BEANR", "GBFXT", "DEBRV", "SGSIN", "MYPKG", "MYTPP", "CNSHA"}
ALLOWED_CARGO_TYPES = {"GENERAL", "REEFER", "HAZMAT"}
ALLOWED_PRIORITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
TEU_MIN = 1500
TEU_MAX = 18000

REQUIRED_TOP_KEYS = {
    "incident_id",
    "timestamp",
    "event_type",
    "severity_level",
    "affected_nodes",
    "cargo_demand",
    "estimated_duration_hours",
    "raw_alert_text",
}
REQUIRED_CARGO_KEYS = {"disrupted_teu", "cargo_type", "priority"}

# Additional durations intentionally allowed in generated variants even if absent in base templates.
ALLOWED_DURATION_EXTENSIONS = {24}


@dataclass
class ValidationSummary:
    total_files: int
    unique_ids: int
    error_count: int
    teu_min_obs: int | None
    teu_max_obs: int | None
    teu_avg_obs: float | None
    ports: Counter[str]
    cargo_types: Counter[str]
    priorities: Counter[str]
    durations: Counter[int]


def _is_utc_iso8601_z(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _load_allowed_durations(base_incidents_path: Path) -> set[int]:
    base = json.loads(base_incidents_path.read_text(encoding="utf-8"))
    durations = {
        row.get("estimated_duration_hours")
        for row in base
        if isinstance(row, dict) and isinstance(row.get("estimated_duration_hours"), int)
    }
    if not durations:
        raise ValueError(f"No valid estimated_duration_hours found in {base_incidents_path}")
    return durations | ALLOWED_DURATION_EXTENSIONS


def _validate_file(path: Path, allowed_durations: set[int], seen_ids: set[str]) -> tuple[list[str], dict[str, Any] | None]:
    errors: list[str] = []

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path.name}: invalid JSON ({exc})"], None

    if not isinstance(obj, dict):
        return [f"{path.name}: top-level JSON must be an object"], None

    missing_top = sorted(REQUIRED_TOP_KEYS - set(obj.keys()))
    if missing_top:
        errors.append(f"{path.name}: missing top-level keys {missing_top}")

    incident_id = obj.get("incident_id")
    if not isinstance(incident_id, str) or not incident_id.strip():
        errors.append(f"{path.name}: incident_id must be non-empty string")
    elif incident_id in seen_ids:
        errors.append(f"{path.name}: duplicate incident_id {incident_id}")
    else:
        seen_ids.add(incident_id)

    if not _is_utc_iso8601_z(obj.get("timestamp")):
        errors.append(f"{path.name}: timestamp must be ISO8601 UTC ending with Z")

    affected_nodes = obj.get("affected_nodes")
    if not isinstance(affected_nodes, list) or not affected_nodes:
        errors.append(f"{path.name}: affected_nodes must be non-empty list")
    else:
        first_node = affected_nodes[0]
        if not isinstance(first_node, dict):
            errors.append(f"{path.name}: affected_nodes[0] must be an object")
        else:
            port = first_node.get("port_code")
            impact_type = first_node.get("impact_type")
            if port not in ALLOWED_PORTS:
                errors.append(f"{path.name}: invalid port_code {port}")
            if not isinstance(impact_type, str) or not impact_type:
                errors.append(f"{path.name}: affected_nodes[0].impact_type must be non-empty string")
            if isinstance(incident_id, str) and isinstance(port, str) and f"-{port}-" not in incident_id:
                errors.append(f"{path.name}: incident_id does not include port token {port}")

    cargo_demand = obj.get("cargo_demand")
    if not isinstance(cargo_demand, dict):
        errors.append(f"{path.name}: cargo_demand must be an object")
    else:
        missing_cargo = sorted(REQUIRED_CARGO_KEYS - set(cargo_demand.keys()))
        if missing_cargo:
            errors.append(f"{path.name}: cargo_demand missing keys {missing_cargo}")

        teu = cargo_demand.get("disrupted_teu")
        if not isinstance(teu, int) or not (TEU_MIN <= teu <= TEU_MAX):
            errors.append(f"{path.name}: disrupted_teu must be integer in [{TEU_MIN}, {TEU_MAX}]")

        cargo_type = cargo_demand.get("cargo_type")
        if cargo_type not in ALLOWED_CARGO_TYPES:
            errors.append(f"{path.name}: invalid cargo_type {cargo_type}")

        priority = cargo_demand.get("priority")
        if priority not in ALLOWED_PRIORITIES:
            errors.append(f"{path.name}: invalid priority {priority}")

    duration = obj.get("estimated_duration_hours")
    if duration not in allowed_durations:
        errors.append(
            f"{path.name}: estimated_duration_hours {duration} not in base template set {sorted(allowed_durations)}"
        )

    raw_text = obj.get("raw_alert_text")
    if not isinstance(raw_text, str) or not raw_text.strip():
        errors.append(f"{path.name}: raw_alert_text must be non-empty string")

    return errors, obj


def _validate_dataset(dataset_dir: Path, base_incidents_path: Path) -> tuple[ValidationSummary, list[str]]:
    if not dataset_dir.exists() or not dataset_dir.is_dir():
        raise FileNotFoundError(f"Dataset directory not found: {dataset_dir}")
    if not base_incidents_path.exists():
        raise FileNotFoundError(f"Base incidents file not found: {base_incidents_path}")

    files = sorted(path for path in dataset_dir.iterdir() if path.suffix.lower() == ".json")
    if not files:
        raise ValueError(f"No JSON files found in dataset directory: {dataset_dir}")

    allowed_durations = _load_allowed_durations(base_incidents_path)

    seen_ids: set[str] = set()
    errors: list[str] = []
    teu_values: list[int] = []
    ports: Counter[str] = Counter()
    cargo_types: Counter[str] = Counter()
    priorities: Counter[str] = Counter()
    durations: Counter[int] = Counter()

    for path in files:
        file_errors, obj = _validate_file(path, allowed_durations=allowed_durations, seen_ids=seen_ids)
        errors.extend(file_errors)
        if file_errors or obj is None:
            continue

        first_node = obj["affected_nodes"][0]
        cargo_demand = obj["cargo_demand"]

        ports[first_node["port_code"]] += 1
        cargo_types[cargo_demand["cargo_type"]] += 1
        priorities[cargo_demand["priority"]] += 1
        durations[obj["estimated_duration_hours"]] += 1
        teu_values.append(cargo_demand["disrupted_teu"])

    summary = ValidationSummary(
        total_files=len(files),
        unique_ids=len(seen_ids),
        error_count=len(errors),
        teu_min_obs=min(teu_values) if teu_values else None,
        teu_max_obs=max(teu_values) if teu_values else None,
        teu_avg_obs=(sum(teu_values) / len(teu_values)) if teu_values else None,
        ports=ports,
        cargo_types=cargo_types,
        priorities=priorities,
        durations=durations,
    )

    return summary, errors


def _print_summary(summary: ValidationSummary, errors: list[str]) -> None:
    print(f"TOTAL_FILES={summary.total_files}")
    print(f"UNIQUE_IDS={summary.unique_ids}")
    print(f"ERRORS={summary.error_count}")

    if summary.teu_min_obs is not None:
        print(f"TEU_MIN_OBS={summary.teu_min_obs}")
        print(f"TEU_MAX_OBS={summary.teu_max_obs}")
        if summary.teu_avg_obs is not None:
            print(f"TEU_AVG={summary.teu_avg_obs:.1f}")

    print(f"PORT_DISTRIBUTION={dict(sorted(summary.ports.items()))}")
    print(f"CARGO_DISTRIBUTION={dict(sorted(summary.cargo_types.items()))}")
    print(f"PRIORITY_DISTRIBUTION={dict(sorted(summary.priorities.items()))}")
    print(f"DURATION_DISTRIBUTION={dict(sorted(summary.durations.items()))}")

    if errors:
        print("\nValidation errors:")
        for err in errors:
            print(f"- {err}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated incident dataset semantics and schema constraints.")
    parser.add_argument(
        "--dataset-dir",
        default=str(DATA_DIR / "batch_incidents_production"),
        help="Directory containing generated incident JSON files.",
    )
    parser.add_argument(
        "--base-incidents",
        default=str(DATA_DIR / "base_incidents.json"),
        help="Path to base incidents JSON used to derive allowed duration values.",
    )
    args = parser.parse_args()

    summary, errors = _validate_dataset(
        dataset_dir=Path(args.dataset_dir),
        base_incidents_path=Path(args.base_incidents),
    )
    _print_summary(summary, errors)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
