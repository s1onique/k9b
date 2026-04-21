"""Schema helpers for review-enrichment advisory payloads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ReviewEnrichmentPayloadError(ValueError):
    """Raised when review-enrichment payload validation fails."""


# Valid values for the used_for field in alert evidence references
_ALERT_EVIDENCE_USED_FOR_VALUES = frozenset({
    "top_concern",
    "next_check",
    "summary",
    "triage_order",
    "focus_note",
})


@dataclass(frozen=True)
class AlertmanagerEvidenceReference:
    """A bounded, inspectable reference to Alertmanager evidence used by the provider.

    This distinguishes provider-assisted interpretation from raw alert evidence.
    Each reference cites specific evidence that was present in the run artifacts.
    """
    cluster: str
    matched_dimensions: tuple[str, ...]
    reason: str
    used_for: str

    def __post_init__(self) -> None:
        if self.used_for not in _ALERT_EVIDENCE_USED_FOR_VALUES:
            raise ReviewEnrichmentPayloadError(
                f"AlertmanagerEvidenceReference.used_for must be one of {sorted(_ALERT_EVIDENCE_USED_FOR_VALUES)}, "
                f"got {self.used_for!r}"
            )


class ReviewEnrichmentShapeClassification(StrEnum):
    """Classification of review-enrichment payload shapes."""

    BOUNDED_REVIEW_ENRICHMENT = "bounded-review-enrichment"
    ASSESSMENT_SHAPED_PAYLOAD = "assessment-shaped-payload"
    MIXED_PAYLOAD = "mixed-payload"
    EMPTY_BOUNDED_PAYLOAD = "empty-bounded-payload"
    UNRECOGNIZED_PAYLOAD = "unrecognized-payload"


def _type_name(value: Any) -> str:
    if value is None:
        return "NoneType"
    return type(value).__name__


def _normalize_optional_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ReviewEnrichmentPayloadError(
            f"{path} expected a string but got {_type_name(value)}"
        )
    trimmed = value.strip()
    return trimmed if trimmed else None


def _normalize_string_sequence(value: Any, path: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items: list[str] = []
        for index, entry in enumerate(value):
            if not isinstance(entry, str):
                raise ReviewEnrichmentPayloadError(
                    f"{path}[{index}] expected a string but got {_type_name(entry)}"
                )
            trimmed = entry.strip()
            if not trimmed:
                raise ReviewEnrichmentPayloadError(
                    f"{path}[{index}] must be a non-empty string"
                )
            items.append(trimmed)
        return tuple(items)
    raise ReviewEnrichmentPayloadError(
        f"{path} expected a list of strings but got {_type_name(value)}"
    )


def _extract_list(raw: Mapping[str, Any], *keys: str) -> tuple[str, ...]:
    for key in keys:
        if key in raw:
            return _normalize_string_sequence(raw[key], key)
    return ()


def _normalize_alertmanager_references(
    value: Any, path: str
) -> tuple[AlertmanagerEvidenceReference, ...]:
    """Parse alertmanagerEvidenceReferences array from raw payload."""
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ReviewEnrichmentPayloadError(
            f"{path} expected a list but got {_type_name(value)}"
        )
    refs: list[AlertmanagerEvidenceReference] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, Mapping):
            raise ReviewEnrichmentPayloadError(
                f"{path}[{index}] expected an object but got {_type_name(entry)}"
            )
        cluster = _normalize_optional_string(entry.get("cluster"), f"{path}[{index}].cluster")
        if not cluster:
            raise ReviewEnrichmentPayloadError(
                f"{path}[{index}].cluster must be a non-empty string"
            )
        dimensions_raw = entry.get("matchedDimensions") or entry.get("matched_dimensions")
        dimensions = _normalize_string_sequence(
            dimensions_raw, f"{path}[{index}].matchedDimensions"
        )
        if not dimensions:
            raise ReviewEnrichmentPayloadError(
                f"{path}[{index}].matchedDimensions must contain at least one entry"
            )
        reason = _normalize_optional_string(entry.get("reason"), f"{path}[{index}].reason")
        if not reason:
            raise ReviewEnrichmentPayloadError(
                f"{path}[{index}].reason must be a non-empty string"
            )
        used_for = _normalize_optional_string(entry.get("usedFor") or entry.get("used_for"), f"{path}[{index}].usedFor")
        if not used_for:
            raise ReviewEnrichmentPayloadError(
                f"{path}[{index}].usedFor must be a non-empty string"
            )
        refs.append(AlertmanagerEvidenceReference(
            cluster=cluster,
            matched_dimensions=dimensions,
            reason=reason,
            used_for=used_for,
        ))
    return tuple(refs)


def _extract_alertmanager_references(raw: Mapping[str, Any]) -> tuple[AlertmanagerEvidenceReference, ...]:
    """Extract alertmanagerEvidenceReferences from raw mapping."""
    return _normalize_alertmanager_references(
        raw.get("alertmanagerEvidenceReferences") or raw.get("alertmanager_evidence_references"),
        "alertmanagerEvidenceReferences"
    )


@dataclass(frozen=True)
class ReviewEnrichmentPayload:
    summary: str | None
    triage_order: tuple[str, ...]
    top_concerns: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    next_checks: tuple[str, ...]
    focus_notes: tuple[str, ...]
    alertmanager_evidence_references: tuple[AlertmanagerEvidenceReference, ...] = field(
        default_factory=tuple
    )

    @classmethod
    def from_dict(cls, raw: Any) -> ReviewEnrichmentPayload:
        if not isinstance(raw, Mapping):
            raise ReviewEnrichmentPayloadError(
                f"review enrichment response expected an object but got {_type_name(raw)}"
            )
        summary = _normalize_optional_string(raw.get("summary"), "summary")
        triage = _extract_list(raw, "triageOrder", "triage_order")
        concerns = _extract_list(raw, "topConcerns", "top_concerns")
        gaps = _extract_list(raw, "evidenceGaps", "evidence_gaps")
        checks = _extract_list(raw, "nextChecks", "next_checks")
        focus = _extract_list(raw, "focusNotes", "focus_notes")
        am_refs = _extract_alertmanager_references(raw)
        return cls(
            summary=summary,
            triage_order=triage,
            top_concerns=concerns,
            evidence_gaps=gaps,
            next_checks=checks,
            focus_notes=focus,
            alertmanager_evidence_references=am_refs,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON storage."""
        result: dict[str, Any] = {}
        if self.summary is not None:
            result["summary"] = self.summary
        if self.triage_order:
            result["triageOrder"] = list(self.triage_order)
        if self.top_concerns:
            result["topConcerns"] = list(self.top_concerns)
        if self.evidence_gaps:
            result["evidenceGaps"] = list(self.evidence_gaps)
        if self.next_checks:
            result["nextChecks"] = list(self.next_checks)
        if self.focus_notes:
            result["focusNotes"] = list(self.focus_notes)
        if self.alertmanager_evidence_references:
            result["alertmanagerEvidenceReferences"] = [
                {
                    "cluster": ref.cluster,
                    "matchedDimensions": list(ref.matched_dimensions),
                    "reason": ref.reason,
                    "usedFor": ref.used_for,
                }
                for ref in self.alertmanager_evidence_references
            ]
        return result


# Fields that define the bounded review-enrichment shape
_BOUNDED_FIELDS = frozenset({
    "summary",
    "triageOrder",
    "triage_order",
    "topConcerns",
    "top_concerns",
    "evidenceGaps",
    "evidence_gaps",
    "nextChecks",
    "next_checks",
    "focusNotes",
    "focus_notes",
})

# Fields that indicate an assessment-shaped payload (different structure)
_ASSESSMENT_FIELDS = frozenset({
    "observedSignals",
    "observed_signals",
    "findings",
    "hypotheses",
    "nextEvidenceToCollect",
    "next_evidence_to_collect",
    "recommendedAction",
    "recommended_action",
    "safetyLevel",
    "safety_level",
    "overallConfidence",
    "overall_confidence",
})


@dataclass(frozen=True)
class ReviewEnrichmentShapeAnalysis:
    """Result of reviewing enrichment payload shape classification."""

    classification: ReviewEnrichmentShapeClassification
    reason: str
    raw_payload_keys: tuple[str, ...]
    summary_present: bool
    triage_order_count: int
    top_concerns_count: int
    evidence_gaps_count: int
    next_checks_count: int
    focus_notes_count: int


def classify_review_enrichment_shape(
    raw_payload: Any,
) -> ReviewEnrichmentShapeAnalysis:
    """Classify the shape of a review-enrichment payload.

    This function examines the raw payload from the provider and classifies
    it to help diagnose output-shape mismatches that can cause planner failures.

    Args:
        raw_payload: The raw payload dict from the provider response.

    Returns:
        ReviewEnrichmentShapeAnalysis with classification and metadata.
    """
    if raw_payload is None:
        return ReviewEnrichmentShapeAnalysis(
            classification=ReviewEnrichmentShapeClassification.UNRECOGNIZED_PAYLOAD,
            reason="raw payload absent",
            raw_payload_keys=(),
            summary_present=False,
            triage_order_count=0,
            top_concerns_count=0,
            evidence_gaps_count=0,
            next_checks_count=0,
            focus_notes_count=0,
        )

    if not isinstance(raw_payload, dict):
        return ReviewEnrichmentShapeAnalysis(
            classification=ReviewEnrichmentShapeClassification.UNRECOGNIZED_PAYLOAD,
            reason=f"raw payload is not a dict, got {_type_name(raw_payload)}",
            raw_payload_keys=(),
            summary_present=False,
            triage_order_count=0,
            top_concerns_count=0,
            evidence_gaps_count=0,
            next_checks_count=0,
            focus_notes_count=0,
        )

    raw_keys = tuple(raw_payload.keys())
    bounded_found = _BOUNDED_FIELDS.intersection(raw_keys)
    assessment_found = _ASSESSMENT_FIELDS.intersection(raw_keys)

    # Extract bounded field counts
    summary = raw_payload.get("summary") or raw_payload.get("Summary")
    summary_present = summary is not None and isinstance(summary, str) and summary.strip()

    triage = raw_payload.get("triageOrder") or raw_payload.get("triage_order")
    triage_order_count = len(triage) if isinstance(triage, (list, tuple)) else 0

    concerns = raw_payload.get("topConcerns") or raw_payload.get("top_concerns")
    top_concerns_count = len(concerns) if isinstance(concerns, (list, tuple)) else 0

    gaps = raw_payload.get("evidenceGaps") or raw_payload.get("evidence_gaps")
    evidence_gaps_count = len(gaps) if isinstance(gaps, (list, tuple)) else 0

    checks = raw_payload.get("nextChecks") or raw_payload.get("next_checks")
    next_checks_count = len(checks) if isinstance(checks, (list, tuple)) else 0

    focus = raw_payload.get("focusNotes") or raw_payload.get("focus_notes")
    focus_notes_count = len(focus) if isinstance(focus, (list, tuple)) else 0

    # Classification logic
    if bounded_found and assessment_found:
        return ReviewEnrichmentShapeAnalysis(
            classification=ReviewEnrichmentShapeClassification.MIXED_PAYLOAD,
            reason="payload contains both bounded review-enrichment fields and assessment fields",
            raw_payload_keys=raw_keys,
            summary_present=bool(summary_present),
            triage_order_count=triage_order_count,
            top_concerns_count=top_concerns_count,
            evidence_gaps_count=evidence_gaps_count,
            next_checks_count=next_checks_count,
            focus_notes_count=focus_notes_count,
        )

    if assessment_found:
        return ReviewEnrichmentShapeAnalysis(
            classification=ReviewEnrichmentShapeClassification.ASSESSMENT_SHAPED_PAYLOAD,
            reason="payload contains assessment fields but no bounded review-enrichment fields",
            raw_payload_keys=raw_keys,
            summary_present=bool(summary_present),
            triage_order_count=triage_order_count,
            top_concerns_count=top_concerns_count,
            evidence_gaps_count=evidence_gaps_count,
            next_checks_count=next_checks_count,
            focus_notes_count=focus_notes_count,
        )

    if not bounded_found:
        return ReviewEnrichmentShapeAnalysis(
            classification=ReviewEnrichmentShapeClassification.UNRECOGNIZED_PAYLOAD,
            reason="payload contains no recognized review-enrichment or assessment fields",
            raw_payload_keys=raw_keys,
            summary_present=bool(summary_present),
            triage_order_count=triage_order_count,
            top_concerns_count=top_concerns_count,
            evidence_gaps_count=evidence_gaps_count,
            next_checks_count=next_checks_count,
            focus_notes_count=focus_notes_count,
        )

    # Bounded fields present - check if they're all empty
    bounded_fields_empty = (
        not summary_present
        and triage_order_count == 0
        and top_concerns_count == 0
        and evidence_gaps_count == 0
        and next_checks_count == 0
        and focus_notes_count == 0
    )

    if bounded_fields_empty:
        return ReviewEnrichmentShapeAnalysis(
            classification=ReviewEnrichmentShapeClassification.EMPTY_BOUNDED_PAYLOAD,
            reason="bounded fields extracted but all empty",
            raw_payload_keys=raw_keys,
            summary_present=bool(summary_present),
            triage_order_count=triage_order_count,
            top_concerns_count=top_concerns_count,
            evidence_gaps_count=evidence_gaps_count,
            next_checks_count=next_checks_count,
            focus_notes_count=focus_notes_count,
        )

    return ReviewEnrichmentShapeAnalysis(
        classification=ReviewEnrichmentShapeClassification.BOUNDED_REVIEW_ENRICHMENT,
        reason="bounded fields extracted successfully",
        raw_payload_keys=raw_keys,
        summary_present=bool(summary_present),
        triage_order_count=triage_order_count,
        top_concerns_count=top_concerns_count,
        evidence_gaps_count=evidence_gaps_count,
        next_checks_count=next_checks_count,
        focus_notes_count=focus_notes_count,
    )
