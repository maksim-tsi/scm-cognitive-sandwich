from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_incident_files(incidents_dir: Path) -> list[Path]:
    if not incidents_dir.exists():
        raise FileNotFoundError(f"Incidents directory does not exist: {incidents_dir}")
    if not incidents_dir.is_dir():
        raise ValueError(f"--incidents-dir must point to a directory: {incidents_dir}")

    files = sorted(path for path in incidents_dir.iterdir() if path.suffix.lower() == ".json")
    if not files:
        raise ValueError(f"No incident JSON files found in {incidents_dir}")
    return files


def _flatten_payload(payload: dict[str, Any]) -> dict[str, Any]:
    affected_nodes = payload.get("affected_nodes")
    if not isinstance(affected_nodes, list):
        raise ValueError("affected_nodes must be a list")

    payload["affected_nodes"] = [
        node["port_code"] if isinstance(node, dict) else node
        for node in affected_nodes
    ]

    cargo_demand = payload.get("cargo_demand")
    if isinstance(cargo_demand, dict):
        payload["cargo_demand"] = cargo_demand["disrupted_teu"]

    if not isinstance(payload.get("cargo_demand"), int):
        raise ValueError("cargo_demand must resolve to an int")

    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Flatten production incident fields to match IncidentTrigger schema."
    )
    parser.add_argument(
        "--incidents-dir",
        default="data/batch_incidents_production",
        help="Directory containing incident JSON files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max number of incidents to process.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing files.",
    )
    args = parser.parse_args()

    incident_files = _load_incident_files(Path(args.incidents_dir))
    if args.limit is not None:
        if args.limit <= 0:
            raise ValueError("--limit must be greater than 0 when provided")
        incident_files = incident_files[: min(args.limit, len(incident_files))]

    success_count = 0
    error_count = 0

    for incident_file in incident_files:
        try:
            payload = json.loads(incident_file.read_text(encoding="utf-8"))
            flattened = _flatten_payload(payload)

            if args.dry_run:
                print(
                    f"DRY-RUN {incident_file.name}: "
                    f"affected_nodes={flattened['affected_nodes']} "
                    f"cargo_demand={flattened['cargo_demand']}"
                )
            else:
                incident_file.write_text(
                    json.dumps(flattened, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                print(f"PATCHED {incident_file.name}")

            success_count += 1
        except Exception as exc:  # noqa: BLE001
            error_count += 1
            print(f"ERROR {incident_file.name}: {type(exc).__name__}: {exc}")

    print(
        f"Done. processed={len(incident_files)} "
        f"success={success_count} errors={error_count} dry_run={args.dry_run}"
    )


if __name__ == "__main__":
    main()
