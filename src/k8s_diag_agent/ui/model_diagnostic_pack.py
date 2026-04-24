"""View models for diagnostic pack UI layer.

This module contains diagnostic-pack-related view model dataclasses and builders
extracted from model.py. It exists to enable incremental modularization without
changing behavior.

Dependency direction:
- model_diagnostic_pack.py -> model_primitives.py

model.py imports from model_diagnostic_pack.py for re-export compatibility.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .model_primitives import (
    _coerce_optional_str,
    _coerce_sequence,
)


@dataclass(frozen=True)
class DiagnosticPackReviewView:
    """View model for diagnostic pack review."""
    timestamp: str | None
    summary: str | None
    major_disagreements: tuple[str, ...]
    missing_checks: tuple[str, ...]
    ranking_issues: tuple[str, ...]
    generic_checks: tuple[str, ...]
    recommended_next_actions: tuple[str, ...]
    drift_misprioritized: bool
    confidence: str | None
    provider_status: str | None
    provider_summary: str | None
    provider_error_summary: str | None
    provider_skip_reason: str | None
    provider_review: Mapping[str, object] | None
    artifact_path: str | None


@dataclass(frozen=True)
class DiagnosticPackView:
    """View model for diagnostic pack."""
    path: str | None
    timestamp: str | None
    label: str | None
    review_bundle_path: str | None
    review_input_14b_path: str | None
    # Semantic metadata: True when review paths point to mutable latest/ mirror,
    # False/None when paths point to immutable run-scoped artifacts.
    is_mirror: bool | None = None
    # Immutable source-of-truth reference: the pack ZIP path that corresponds to
    # the mirror paths when isMirror=True. Exposed so operators can reference
    # the exact immutable pack that generated the current mirror content.
    source_pack_path: str | None = None


def _build_diagnostic_pack_review_view(raw: object | None) -> DiagnosticPackReviewView | None:
    """Build DiagnosticPackReviewView from raw JSON data."""
    if not isinstance(raw, Mapping):
        return None
    major_disagreements = _coerce_sequence(raw.get("majorDisagreements") or raw.get("major_disagreements"))
    missing_checks = _coerce_sequence(raw.get("missingChecks") or raw.get("missing_checks"))
    ranking_issues = _coerce_sequence(raw.get("rankingIssues") or raw.get("ranking_issues"))
    generic_checks = _coerce_sequence(raw.get("genericChecks") or raw.get("generic_checks"))
    recommended_next_actions = _coerce_sequence(
        raw.get("recommendedNextActions") or raw.get("recommended_next_actions")
    )
    provider_review = raw.get("providerReview") or raw.get("provider_review")
    return DiagnosticPackReviewView(
        timestamp=_coerce_optional_str(raw.get("timestamp")),
        summary=_coerce_optional_str(raw.get("summary")),
        major_disagreements=major_disagreements,
        missing_checks=missing_checks,
        ranking_issues=ranking_issues,
        generic_checks=generic_checks,
        recommended_next_actions=recommended_next_actions,
        drift_misprioritized=bool(raw.get("driftMisprioritized") or raw.get("drift_misprioritized")),
        confidence=_coerce_optional_str(raw.get("confidence")),
        provider_status=_coerce_optional_str(raw.get("providerStatus") or raw.get("provider_status")),
        provider_summary=_coerce_optional_str(raw.get("providerSummary") or raw.get("provider_summary")),
        provider_error_summary=_coerce_optional_str(
            raw.get("providerErrorSummary") or raw.get("provider_error_summary")
        ),
        provider_skip_reason=_coerce_optional_str(
            raw.get("providerSkipReason") or raw.get("provider_skip_reason")
        ),
        provider_review=provider_review if isinstance(provider_review, Mapping) else None,
        artifact_path=_coerce_optional_str(raw.get("artifactPath") or raw.get("artifact_path")),
    )


def _build_diagnostic_pack_view(raw: object | None) -> DiagnosticPackView | None:
    """Build DiagnosticPackView from raw JSON data."""
    if not isinstance(raw, Mapping):
        return None
    # Parse isMirror field - handle both camelCase (API) and snake_case (internal)
    is_mirror_value = raw.get("isMirror")
    if is_mirror_value is None:
        is_mirror_value = raw.get("is_mirror")
    is_mirror: bool | None = None
    if is_mirror_value is not None:
        is_mirror = bool(is_mirror_value)
    # Parse sourcePackPath field - immutable pack reference when isMirror=true
    source_pack_path: str | None = None
    source_pack_value = raw.get("sourcePackPath")
    if source_pack_value is None:
        source_pack_value = raw.get("source_pack_path")
    if source_pack_value is not None:
        source_pack_path = _coerce_optional_str(source_pack_value)
    return DiagnosticPackView(
        path=_coerce_optional_str(raw.get("path")),
        timestamp=_coerce_optional_str(raw.get("timestamp")),
        label=_coerce_optional_str(raw.get("label")),
        review_bundle_path=_coerce_optional_str(raw.get("review_bundle_path")),
        review_input_14b_path=_coerce_optional_str(raw.get("review_input_14b_path")),
        is_mirror=is_mirror,
        source_pack_path=source_pack_path,
    )
