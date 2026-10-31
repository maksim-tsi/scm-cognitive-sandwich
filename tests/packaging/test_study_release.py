import importlib.util
from pathlib import Path
import zipfile
import io
import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("study_release", ROOT / "release-candidates/build.py")
assert SPEC and SPEC.loader
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def test_archive_is_deterministic_and_order_independent():
    first = release.archive_bytes({"b.txt": b"b", "a.txt": b"a"})
    assert first == release.archive_bytes({"a.txt": b"a", "b.txt": b"b"})
    with zipfile.ZipFile(io.BytesIO(first)) as z:
        assert z.namelist() == ["a.txt", "b.txt"]
        assert z.testzip() is None


def test_option_like_revision_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        release.build("--help", tmp_path)


def test_sensitive_examples_are_detected():
    assert release.SENSITIVE.search(b"http://192.168.1.2/private")
    assert release.SENSITIVE.search(b"/Users/example/config")
    assert not release.SENSITIVE.search(b"https://example.invalid")
