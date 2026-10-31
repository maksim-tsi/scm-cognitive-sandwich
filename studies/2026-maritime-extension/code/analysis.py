#!/usr/bin/env python3
"""Provider-free R4-v5 analysis over sanitized incident-terminal records."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import random
from statistics import mean
from typing import Any, Callable

EXPECTED_INCIDENTS = 60
BOOTSTRAP_SEED = 202604
SIGN_FLIP_SEED = 202605
BOOTSTRAP_RESAMPLES = 10_000
SIGN_FLIP_PERMUTATIONS = 100_000
NON_ESTIMABLE = "NON_ESTIMABLE_NO_ANALYZABLE_PAIRS"


class AnalysisError(RuntimeError):
    """Raised when the frozen v5 analysis surface drifts."""


def _seed(base: int, label: str) -> int:
    return int.from_bytes(
        hashlib.sha256(f"{base}:{label}".encode()).digest()[:8], "big"
    )


def cluster_bootstrap(
    values: list[float], *, label: str, resamples: int = BOOTSTRAP_RESAMPLES
) -> tuple[float, float]:
    if not values or resamples != BOOTSTRAP_RESAMPLES:
        raise AnalysisError("cluster bootstrap denominator or resample drift")
    rng = random.Random(_seed(BOOTSTRAP_SEED, label))
    draws = [
        mean(values[rng.randrange(len(values))] for _ in values)
        for _ in range(resamples)
    ]
    draws.sort()
    return (
        draws[int(0.025 * (len(draws) - 1))],
        draws[int(0.975 * (len(draws) - 1))],
    )


def paired_sign_flip(
    values: list[float], *, label: str, permutations: int = SIGN_FLIP_PERMUTATIONS
) -> float:
    if not values or permutations != SIGN_FLIP_PERMUTATIONS:
        raise AnalysisError("sign-flip denominator or permutation drift")
    observed = abs(mean(values))
    rng = random.Random(_seed(SIGN_FLIP_SEED, label))
    exceed = 0
    for _ in range(permutations):
        candidate = abs(
            mean(value if rng.getrandbits(1) else -value for value in values)
        )
        exceed += candidate >= observed
    return (exceed + 1) / (permutations + 1)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise AnalysisError("terminal JSONL contains a non-object row")
        rows.append(value)
    return rows


def _condition_is_analyzable(value: dict[str, Any]) -> bool:
    return bool(
        value.get("science_outcome_available")
        and value.get("unit_terminal_reason")
        in {"ACCEPTED", "FAIL_CLOSED_VALIDATION"}
        and value.get("observability_reason") is None
    )


def _comparison(
    rows: list[dict[str, Any]], *, comparator: str, label: str
) -> dict[str, Any]:
    observed: list[float] = []
    cluster_bounds: list[tuple[float, float]] = []
    missing_reasons: dict[str, int] = {}
    for row in rows:
        structured = row["conditions"]["structured_repair"]
        baseline = row["conditions"][comparator]
        if _condition_is_analyzable(structured) and _condition_is_analyzable(
            baseline
        ):
            difference = float(structured["accepted"]) - float(
                baseline["accepted"]
            )
            observed.append(difference)
            cluster_bounds.append((difference, difference))
            continue
        cluster_bounds.append((-1.0, 1.0))
        reasons = {
            str(value)
            for value in (
                structured.get("unit_terminal_reason"),
                baseline.get("unit_terminal_reason"),
                structured.get("primary_provider_reason"),
                baseline.get("primary_provider_reason"),
                structured.get("observability_reason"),
                baseline.get("observability_reason"),
            )
            if value
        }
        reason = "+".join(sorted(reasons)) or "UNCLASSIFIED_MISSING_PAIR"
        missing_reasons[reason] = missing_reasons.get(reason, 0) + 1

    lower = mean(item[0] for item in cluster_bounds)
    upper = mean(item[1] for item in cluster_bounds)
    result: dict[str, Any] = {
        "estimand": f"structured_repair - {comparator}",
        "incident_clusters_expected": EXPECTED_INCIDENTS,
        "incident_clusters_analyzable": len(observed),
        "incident_clusters_missing": EXPECTED_INCIDENTS - len(observed),
        "cluster_level_worst_case_bounds": [lower, upper],
        "missing_pairs_by_reason": missing_reasons,
    }
    if not observed:
        result.update(
            {
                "status": NON_ESTIMABLE,
                "mean_difference": None,
                "cluster_bootstrap_95_ci": None,
                "paired_sign_flip_p_value": None,
            }
        )
        return result
    result.update(
        {
            "status": "ESTIMATED",
            "mean_difference": mean(observed),
            "cluster_bootstrap_95_ci": list(
                cluster_bootstrap(observed, label=label)
            ),
            "paired_sign_flip_p_value": paired_sign_flip(observed, label=label),
        }
    )
    return result


def analyze_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) != EXPECTED_INCIDENTS:
        raise AnalysisError("v5 terminal denominator must be exactly 60 incidents")
    incident_ids = [str(row.get("incident_id")) for row in rows]
    if len(set(incident_ids)) != EXPECTED_INCIDENTS:
        raise AnalysisError("v5 terminal incident clusters are not unique")
    for row in rows:
        if set(row.get("conditions", {})) != {
            "llm_only",
            "gate_only",
            "structured_repair",
        }:
            raise AnalysisError("v5 terminal condition set drift")

    generated = sum(
        bool(
            row["conditions"]["llm_only"].get("response_attributed")
            and row["conditions"]["llm_only"].get("artifact_sha256")
        )
        for row in rows
    )
    validation_outcomes = sum(
        bool(condition.get("validation_outcome_recorded"))
        for row in rows
        for condition in row["conditions"].values()
    )
    primary = _comparison(rows, comparator="gate_only", label="primary")
    h2 = _comparison(rows, comparator="llm_only", label="h2")
    overall = (
        NON_ESTIMABLE
        if primary["status"] == NON_ESTIMABLE
        and h2["status"] == NON_ESTIMABLE
        else "ANALYZED"
    )
    return {
        "schema_version": "1.0",
        "contract_version": "R4-DEEPSEEK-DIRECT-v5",
        "status": overall,
        "denominators": {
            "frozen_incidents": EXPECTED_INCIDENTS,
            "attempted_incidents": EXPECTED_INCIDENTS,
            "generated_initial_artifacts": generated,
            "validation_outcomes_recorded": validation_outcomes,
        },
        "primary": primary,
        "h2_exploratory": h2,
        "analysis_contract": {
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "sign_flip_permutations": SIGN_FLIP_PERMUTATIONS,
            "sign_flip_seed": SIGN_FLIP_SEED,
            "bounds_unit": "incident_cluster",
        },
    }


def analyze(
    *, terminal_path: Path, output_path: Path, before_write: Callable[[], None] | None = None
) -> dict[str, Any]:
    result = analyze_rows(_read_jsonl(terminal_path))
    if before_write is not None:
        before_write()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def validate_numeric_result(result: dict[str, Any]) -> None:
    """Reject NaN/inf before a sanitized analysis summary is accepted."""
    stack: list[Any] = [result]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
        elif isinstance(value, float) and not math.isfinite(value):
            raise AnalysisError("non-finite analysis value")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--terminals", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = analyze(terminal_path=args.terminals, output_path=args.output)
    validate_numeric_result(value)
    print(json.dumps(value, sort_keys=True))
