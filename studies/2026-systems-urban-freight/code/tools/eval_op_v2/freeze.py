"""Candidate content manifest; an approval receipt pins its exact hash later."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2].parent / "data"
MANIFEST = ROOT / "research/eval-op-v2/manifest.json"


def manifest():
    files = [
        ROOT / "evidence/stage1/geography/selected-sites.csv",
        ROOT / "evidence/stage2/geography/distance-matrix.csv",
        ROOT / "research/streetview/screenshot-inventory.json",
        ROOT / "research/streetview/second-pass-observations.json",
    ]
    for folder in (
        "research/eval-op-v2",
        "tools/eval_op_v2",
        "tools/p5_interactive",
        "tools/openai_extension",
        "tools/mistral_pilot",
        "tools/p4_world",
        "tools/padua_pilot",
        "implementation/padua_evidence_v1/stage2/core",
        "implementation/padua_evidence_v1/stage2/runner",
    ):
        files.extend(
            p
            for p in (
                (ROOT / folder).rglob("*")
                if folder == "research/eval-op-v2"
                else (ROOT / folder).glob("*")
            )
            if p.is_file()
            and p.suffix in (".py", ".cpp", ".json", ".md")
            and p != MANIFEST
        )
    return {
        "status": "candidate_not_approved_or_frozen",
        "algorithm": "sha256",
        "files": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(files))
        },
    }


def main():
    MANIFEST.write_text(json.dumps(manifest(), indent=2, sort_keys=True) + "\n")
    print(hashlib.sha256(MANIFEST.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
