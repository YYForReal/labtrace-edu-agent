"""Data contracts for evidence-grounded grading and teacher review."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class ContractError(ValueError):
    """Raised when a grading trace violates an auditable invariant."""


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    kind: str
    source_file: str
    locator: str
    excerpt: str
    reliability: float
    verification: str = "model_observed"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceRef":
        return cls(
            evidence_id=str(data["evidence_id"]),
            kind=str(data["kind"]),
            source_file=str(data["source_file"]),
            locator=str(data["locator"]),
            excerpt=str(data.get("excerpt", "")),
            reliability=float(data["reliability"]),
            verification=str(data.get("verification", "model_observed")),
        )

    def validate(self) -> None:
        if not self.evidence_id.strip():
            raise ContractError("evidence_id must not be empty")
        if not self.source_file.strip() or not self.locator.strip():
            raise ContractError(
                f"{self.evidence_id}: source_file and locator are required"
            )
        if not 0 <= self.reliability <= 1:
            raise ContractError(
                f"{self.evidence_id}: reliability must be between 0 and 1"
            )


@dataclass(frozen=True)
class CriterionDecision:
    criterion_id: str
    criterion_name: str
    max_score: float
    score: float
    reason: str
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CriterionDecision":
        return cls(
            criterion_id=str(data["criterion_id"]),
            criterion_name=str(data["criterion_name"]),
            max_score=float(data["max_score"]),
            score=float(data["score"]),
            reason=str(data.get("reason", "")),
            evidence_ids=tuple(str(item) for item in data.get("evidence_ids", [])),
            confidence=float(data.get("confidence", 0)),
        )

    def validate(self) -> None:
        if not self.criterion_id.strip():
            raise ContractError("criterion_id must not be empty")
        if self.max_score <= 0:
            raise ContractError(f"{self.criterion_id}: max_score must be positive")
        if not 0 <= self.score <= self.max_score:
            raise ContractError(
                f"{self.criterion_id}: score {self.score} is outside 0..{self.max_score}"
            )
        if not self.reason.strip():
            raise ContractError(f"{self.criterion_id}: reason is required")
        if not 0 <= self.confidence <= 1:
            raise ContractError(
                f"{self.criterion_id}: confidence must be between 0 and 1"
            )
        if self.score > 0 and not self.evidence_ids:
            raise ContractError(
                f"{self.criterion_id}: a positive score requires evidence"
            )


@dataclass(frozen=True)
class ReviewDecision:
    status: str
    reviewer_role: str
    final_score: float | None = None
    note: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewDecision":
        final_score = data.get("final_score")
        return cls(
            status=str(data["status"]),
            reviewer_role=str(data.get("reviewer_role", "teacher")),
            final_score=float(final_score) if final_score is not None else None,
            note=str(data.get("note", "")),
        )

    def validate(self) -> None:
        allowed = {"pending", "approved", "adjusted", "rejected"}
        if self.status not in allowed:
            raise ContractError(f"review status must be one of {sorted(allowed)}")
        if self.status == "adjusted" and self.final_score is None:
            raise ContractError("adjusted review requires final_score")
        if self.status in {"adjusted", "rejected"} and not self.note.strip():
            raise ContractError(f"{self.status} review requires a note")


@dataclass(frozen=True)
class GradeTrace:
    trace_id: str
    rubric_id: str
    submission_alias: str
    evidence: tuple[EvidenceRef, ...]
    criteria: tuple[CriterionDecision, ...]
    model_total_score: float
    needs_human_review: bool
    review_reasons: tuple[str, ...]
    review: ReviewDecision

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GradeTrace":
        trace = cls(
            trace_id=str(data["trace_id"]),
            rubric_id=str(data["rubric_id"]),
            submission_alias=str(data["submission_alias"]),
            evidence=tuple(
                EvidenceRef.from_dict(item) for item in data.get("evidence", [])
            ),
            criteria=tuple(
                CriterionDecision.from_dict(item) for item in data.get("criteria", [])
            ),
            model_total_score=float(data["model_total_score"]),
            needs_human_review=bool(data.get("needs_human_review", False)),
            review_reasons=tuple(str(item) for item in data.get("review_reasons", [])),
            review=ReviewDecision.from_dict(data.get("review", {"status": "pending"})),
        )
        trace.validate()
        return trace

    def validate(self) -> None:
        if not self.trace_id.strip() or not self.rubric_id.strip():
            raise ContractError("trace_id and rubric_id are required")
        if not self.submission_alias.strip():
            raise ContractError(
                "submission_alias is required; do not use a public real identity"
            )

        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ContractError("evidence_id values must be unique")
        for item in self.evidence:
            item.validate()

        criterion_ids = [item.criterion_id for item in self.criteria]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ContractError("criterion_id values must be unique")
        for item in self.criteria:
            item.validate()
            unknown = set(item.evidence_ids) - set(evidence_ids)
            if unknown:
                raise ContractError(
                    f"{item.criterion_id}: unknown evidence references {sorted(unknown)}"
                )

        calculated = sum(item.score for item in self.criteria)
        if abs(calculated - self.model_total_score) > 0.01:
            raise ContractError(
                f"model_total_score {self.model_total_score} does not match {calculated}"
            )
        if self.needs_human_review and not self.review_reasons:
            raise ContractError("human review flag requires at least one reason")

        self.review.validate()
        max_total = sum(item.max_score for item in self.criteria)
        if (
            self.review.final_score is not None
            and not 0 <= self.review.final_score <= max_total
        ):
            raise ContractError(f"final_score must be between 0 and {max_total}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
