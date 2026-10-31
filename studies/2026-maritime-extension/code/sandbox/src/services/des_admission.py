"""Fail-closed DES admission for accepted R2 allocation artifacts."""

from dataclasses import dataclass

from src.services.allocation_reference import ReferenceResult
from src.services.artifact_validator import ValidationResult


@dataclass(frozen=True)
class AdmissionDecision:
    admitted: bool
    reason: str | None


def admit_to_des(
    validation: ValidationResult, strict_reference: ReferenceResult
) -> AdmissionDecision:
    """Admit only an evaluator-valid artifact with an OPTIMAL strict reference."""
    if not validation.schema_valid or not validation.semantic_valid or not validation.feasible:
        return AdmissionDecision(False, "EVALUATOR_REJECTED")
    if strict_reference.status != "OPTIMAL" or strict_reference.total_cost is None:
        return AdmissionDecision(False, "STRICT_REFERENCE_NOT_COST_VALID")
    if strict_reference.shortfall_by_lot:
        return AdmissionDecision(False, "STRICT_REFERENCE_SHORTFALL")
    return AdmissionDecision(True, None)
