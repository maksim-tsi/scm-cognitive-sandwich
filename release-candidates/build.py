"""Build study-specific, deterministic release candidates from committed Git objects.

Never creates a tag/release, reads private sources, or calls model endpoints.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {
    "idwl-2026-v1": ("2026-idwl", "Published antecedent; navigation/source-anchor package, preserved code at pinned public commit"),
    "maritime-extension-2026-v1": ("2026-maritime-extension", "Unpublished research extension; retained-summary reproduction, execution gaps documented"),
    "systems-urban-freight-2026-v1": ("2026-systems-urban-freight", "Systems manuscript, not accepted/published; results and I2/I3 replay offline"),
}
BLOCKED_SUFFIXES = {".bin", ".sqlite", ".db", ".png", ".jpg", ".jpeg", ".gguf", ".env"}
SENSITIVE = re.compile(rb"/Users/|192\.168\.\d+\.\d+|https?://[^\s]+\.lab\.|BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|sk-[A-Za-z0-9_-]{20,}")


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def entries(revision: str, folder: str) -> dict[str, bytes]:
    result = {}
    extra = ["docs/legacy-maritime-quickstart.md"] if folder.endswith("2026-idwl") else []
    tree = git("ls-tree", "-r", revision, "--", folder, "LICENSE", *extra).decode()
    for line in tree.splitlines():
        spec, name = line.split("\t", 1)
        mode, kind, oid = spec.split()
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError("Nonregular release entry")
        if Path(name).suffix.lower() in BLOCKED_SUFFIXES or any(p.startswith(".") for p in Path(name).parts):
            raise ValueError("Prohibited release material: " + name)
        raw = git("cat-file", "blob", oid)
        if SENSITIVE.search(raw):
            raise ValueError("Sensitive source requires review: " + name)
        result[name] = raw
    if not any(name.startswith(folder + "/") for name in result):
        raise ValueError("Study not present in selected revision")
    return result


def archive_bytes(files: dict[str, bytes]) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    return target.getvalue()


def build(revision: str, output: Path) -> dict:
    if revision.startswith("-"):
        raise ValueError("Revision must be a Git name, not an option")
    commit = git("rev-parse", "--verify", revision + "^{commit}").decode().strip()
    output.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"source_commit": commit, "status": "prepared_candidates_not_published_releases", "files": []}
    for tag, (study, status) in PACKAGES.items():
        files = entries(commit, "studies/" + study)
        identity: dict[str, Any] = {"proposed_tag": tag, "source_commit": commit, "publication_status": status,
                    "files": [{"path": p, "sha256": hashlib.sha256(b).hexdigest()} for p, b in sorted(files.items())]}
        files["RELEASE-MANIFEST.json"] = (json.dumps(identity, indent=2) + "\n").encode()
        files["RELEASE-README.md"] = ("# " + tag + "\n\n" + status + "\n\nRead studies/" + study + "/README.md.\nNo inference, final release or tag is authorized by this archive.\n").encode()
        raw = archive_bytes(files)
        path = output / (tag + ".zip")
        if path.exists() and path.read_bytes() != raw:
            raise FileExistsError("Refusing to replace a different candidate")
        path.write_bytes(raw)
        with zipfile.ZipFile(path) as check:
            assert check.testzip() is None
            for record in identity["files"]:
                assert hashlib.sha256(check.read(record["path"])).hexdigest() == record["sha256"]
        manifest["files"].append({"name": path.name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "proposed_tag": tag, "publication_status": status})
    (output / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    if not __debug__:
        raise RuntimeError("Verification requires assertions enabled")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.revision, args.output), indent=2))


if __name__ == "__main__":
    main()
