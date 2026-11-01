import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("history_reproduction", ROOT / "studies/2026-maritime-extension/reproduction/reproduce.py")
assert SPEC and SPEC.loader
history = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(history)


def test_original_analysis_and_recovered_records():
    result = history.run()
    assert result["analysis_equal"]
    assert result["canonical_responses_hash_checked"] == 27
    assert not result["executed_input_binding_recovered"]
    assert result["new_model_calls"] == 0


def test_corrupted_package_fails_before_analysis(tmp_path, monkeypatch):
    (tmp_path / "provenance").mkdir()
    (tmp_path / "provenance/package-manifest.json").write_text('{"files":[{"path":"payload","sha256":"wrong"}]}')
    (tmp_path / "payload").write_text("tampered")
    monkeypatch.setattr(history, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="identity differs"):
        history.verify_files()
