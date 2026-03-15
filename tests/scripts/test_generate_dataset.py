from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType


def _load_script_module(script_name: str) -> ModuleType:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / script_name
    spec = spec_from_file_location(script_name.replace(".py", ""), script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module for {script_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_rows_is_deterministic_and_schema_compliant():
    module = _load_script_module("generate_dataset.py")

    rows_first = module.build_rows()
    rows_second = module.build_rows()

    assert rows_first == rows_second
    assert len(rows_first) == module.TOTAL_RUNS == 100

    first = rows_first[0]
    last = rows_first[-1]
    assert first["run_id"] == "001"
    assert last["run_id"] == "100"

    for row in rows_first:
        assert set(row.keys()) == set(module.OUTPUT_COLUMNS)
        assert row["closed_port"] in set(module.PORT_CHOICES)
        assert 5000 <= int(row["total_teu"]) <= 50000
        assert 0.5 <= float(row["capacity_multiplier"]) <= 1.2
        assert row["alert_text"].startswith(f"Port of {row['closed_port']} is closed.")
