"""Offline byte-identical proposal replay; no provider, credentials or retries."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from .runtime import apply_decision, released_packet


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> Any:
    raise ValueError("nonfinite JSON constant")


def replay(packet: dict[str, Any], original: bytes) -> dict[str, Any]:
    """Parse once, pass identical copies to S2/S3, retain exact original hash.

    JSON/UTF-8 errors and non-object outputs are failed attempts, never referrals.
    This function makes no claim that a well-shaped proposal is correct.
    """
    digest = hashlib.sha256(original).hexdigest()
    result: dict[str, Any] = {
        "original_sha256": digest,
        "original_bytes": len(original),
    }
    try:
        proposal = json.loads(
            original.decode("utf-8"),
            object_pairs_hook=_object,
            parse_constant=_constant,
        )
        if not isinstance(proposal, dict):
            raise TypeError("proposal must be a JSON object")
    except (ValueError, UnicodeError, TypeError):
        failed = {
            "attempt_status": "malformed_output",
            "admitted": False,
            "final_decision": None,
        }
        return {**result, "s2": copy.deepcopy(failed), "s3": copy.deepcopy(failed)}
    public = released_packet(packet)
    s2 = apply_decision(public, copy.deepcopy(proposal), False)
    s3 = apply_decision(public, copy.deepcopy(proposal), True)
    assert s2["proposal_hash"] == s3["proposal_hash"]
    return {**result, "shared_proposal_hash": s2["proposal_hash"], "s2": s2, "s3": s3}
