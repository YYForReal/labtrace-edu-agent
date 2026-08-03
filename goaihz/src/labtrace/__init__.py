"""Reusable competition modules for the LabTrace education agent."""

from .contracts import (
    ContractError,
    CriterionDecision,
    EvidenceRef,
    GradeTrace,
    ReviewDecision,
)
from .diagnosis import build_class_diagnosis
from .privacy import find_sensitive_data, pseudonymize

__all__ = [
    "ContractError",
    "CriterionDecision",
    "EvidenceRef",
    "GradeTrace",
    "ReviewDecision",
    "build_class_diagnosis",
    "find_sensitive_data",
    "pseudonymize",
]
