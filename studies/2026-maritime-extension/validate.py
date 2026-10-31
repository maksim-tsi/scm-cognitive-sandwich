"""Read-only verification of the curated historical export; no new analysis."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent


def main():
    manifest = json.loads((ROOT / "provenance/public-export.json").read_text())
    for entry in manifest["files"]:
        raw = (ROOT / entry["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"] == entry["source_sha256"]
    terminals = [json.loads(line) for line in (ROOT / "evidence/terminals.jsonl").read_text().splitlines()]
    replications = [json.loads(line) for line in (ROOT / "evidence/des-replications.jsonl").read_text().splitlines()]
    assert len(terminals) == 60 and len(replications) == 15400
    print(json.dumps({"files_checked": len(manifest["files"]), "incidents": len(terminals), "retained_DES_rows": len(replications), "new_runs": 0}))


if __name__ == "__main__":
    if not __debug__:
        raise RuntimeError("Validation requires assertions enabled")
    main()
