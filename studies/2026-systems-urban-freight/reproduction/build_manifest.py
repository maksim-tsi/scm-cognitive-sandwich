"""Build a hash manifest for a reviewed public package, excluding transient caches."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "provenance/package-manifest.json"


def build():
    files = []
    for path in sorted(ROOT.rglob("*")):
        if path == OUTPUT or not path.is_file() or any(p.startswith(".") or p == "__pycache__" for p in path.relative_to(ROOT).parts):
            continue
        if path.is_symlink():
            raise ValueError("Symlinks are not public package artifacts")
        files.append({"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    OUTPUT.write_text(json.dumps({"schema_version": 1, "files": files}, indent=2) + "\n")
    return len(files)


if __name__ == "__main__":
    print(build())
