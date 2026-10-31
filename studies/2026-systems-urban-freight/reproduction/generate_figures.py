"""Reproduce the figure and result tables directly from retained analysis JSON."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {'r1': ('results/r1/analysis.json', '6bd2c1dc74ae50d7e1a1cedc2bc80f06f9f25e938f3f0f7f3bece86ce18caa9c'), 'eval30': ('results/eval30/analysis.json', '91e655c3d0993e5786f3f34bdb85eb0065d5a514c644f083e1247c7148f14839'), 'luna': ('results/luna-eval30/analysis.json', 'b04776e4986501b7677c554e0102676cb7c419fb2c9a0a7404ce1e8f2fbd393a')}
ROUTES = [
    ("qwen", "Qwen"),
    ("deepseek", "DeepSeek"),
    ("mistral", "Mistral"),
    ("openai", "Luna"),
    ("dint", "D-INT"),
]


def load():
    result = {}
    for key, (path, expected) in SOURCES.items():
        raw = (ROOT / path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Source identity differs: " + path)
        result[key] = json.loads(raw)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    target = args.output
    (target / "figures").mkdir(parents=True, exist_ok=True)
    (target / "generated").mkdir(parents=True, exist_ok=True)
    source = load()
    providers = source["r1"]["providers"]
    cases = [x["case_id"] for x in providers["qwen"]["pairs"]]
    assert len(cases) == 6
    fig, ax = plt.subplots(figsize=(7.2, 3.35), layout="constrained")
    colors = {
        (1, 1): "#baded1",
        (0, 0): "#e2e7ed",
        (1, 0): "#f3c888",
        (0, 1): "#b9cfe8",
    }
    for row, (route, label) in enumerate(ROUTES):
        pairs = providers[route]["pairs"]
        assert [p["case_id"] for p in pairs] == cases
        for col, p in enumerate(pairs):
            a, b = p["control"], p["enriched"]
            assert a in (0, 1) and b in (0, 1)
            ax.add_patch(
                Rectangle(
                    (col, row),
                    1,
                    1,
                    facecolor=colors[(a, b)],
                    edgecolor="white",
                    linewidth=2,
                )
            )
            ax.text(
                col + 0.5,
                row + 0.5,
                f"{a} → {b}",
                ha="center",
                va="center",
                fontsize=11,
                color="#20242a",
            )
    ax.set_xlim(0, 6)
    ax.set_ylim(5, 0)
    ax.set_aspect("equal")
    ax.set_xticks([i + 0.5 for i in range(6)], [s.replace("OPV2-", "") for s in cases])
    ax.set_yticks([i + 0.5 for i in range(5)], [label for _, label in ROUTES])
    ax.set_xlabel("Matched case")
    ax.tick_params(length=0)
    [sp.set_visible(False) for sp in ax.spines.values()]
    fig.savefig(
        target / "figures/paired-outcomes.pdf",
        metadata={
            "Title": "R1 matched control and enriched correctness",
            "Creator": "EVAL-OP-V2-R1 figure generator",
            "CreationDate": None,
            "ModDate": None,
        },
    )
    plt.close(fig)
    lines = []
    for route, label in ROUTES:
        x = providers[route]
        c = x["standalone_enriched_components"]
        assert x["standalone_assigned"] == 16
        lines.append(
            f"{label} & {x['standalone_correct']}/16 & {c['appropriate_insufficiency']} & {c['unnecessary_insufficient_full_reference']} & {c['unsupported_numeric_commitments']}/{c['numeric_denominator']} & {c['reference_physical_errors']}/{c['reference_physical_checked']} & {c['numeric_semantic_transition_errors']}/{c['numeric_denominator']} & {c['useful_i2']}/{c['useful_i3']} \\\\"
        )
    (target / "generated/r1-table.tex").write_text(
        "\n".join(lines) + "\n\\bottomrule\n"
    )
    old = source["eval30"]["summaries"]
    new = source["luna"]["summaries"]["openai"]
    historical = []
    for route, label in [
        ("qwen", "Qwen"),
        ("deepseek", "DeepSeek"),
        ("mistral", "Mistral"),
        ("openai", "Luna (later extension)"),
        ("deterministic", "D-INT"),
    ]:
        v = new if route == "openai" else old[route]
        historical.append(
            f"{label} & {v['completed']}/30 & {v['correct']}/30 & {v['useful_I2']}/{v['useful_I3']} \\\\"
        )
    (target / "generated/eval30-table.tex").write_text(
        "\n".join(historical) + "\n\\bottomrule\n"
    )
    print("Generated paired outcome figure and two evidence-derived tables.")


if __name__ == "__main__":
    main()
