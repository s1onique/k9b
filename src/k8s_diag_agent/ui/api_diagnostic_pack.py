"""Diagnostic pack serialization functions for the operator UI.

This module contains serializer functions for diagnostic-pack-related payloads:
- Diagnostic pack metadata
- Diagnostic pack review summary

Extracted from api.py to establish a clean separation of concerns.
These functions are re-exported from api.py for backward compatibility.

Ownership reminder:
    - Payload TypedDict classes live in api_payloads.py.
    - Serializer functions live here.
    - api.py is the public serialization surface.
"""

from __future__ import annotations

from .api_payloads import (
    DiagnosticPackPayload,
    DiagnosticPackReviewPayload,
)
from .model import (
    DiagnosticPackReviewView,
    DiagnosticPackView,
)


def _serialize_diagnostic_pack(
    view: DiagnosticPackView | None,
) -> DiagnosticPackPayload | None:
    """Serialize diagnostic pack metadata to payload dict."""
    if not view:
        return None
    result: DiagnosticPackPayload = {
        "path": view.path,
        "timestamp": view.timestamp,
        "label": view.label,
        "reviewBundlePath": view.review_bundle_path,
        "reviewInput14bPath": view.review_input_14b_path,
    }
    # Additive semantic metadata: indicates whether review paths point to mutable latest/ mirror
    if view.is_mirror is not None:
        result["isMirror"] = view.is_mirror
    # When isMirror=True, expose the immutable source pack reference so operators
    # can use the exact pack ZIP that generated the current mirror content.
    # Use view.source_pack_path if provided, otherwise fall back to view.path.
    if view.is_mirror:
        source_pack = view.source_pack_path if view.source_pack_path is not None else view.path
        if source_pack is not None:
            result["sourcePackPath"] = source_pack
    return result


def _serialize_diagnostic_pack_review(
    view: DiagnosticPackReviewView | None,
) -> DiagnosticPackReviewPayload | None:
    """Serialize diagnostic pack review summary to payload dict."""
    if not view:
        return None
    return {
        "timestamp": view.timestamp,
        "summary": view.summary,
        "majorDisagreements": list(view.major_disagreements),
        "missingChecks": list(view.missing_checks),
        "rankingIssues": list(view.ranking_issues),
        "genericChecks": list(view.generic_checks),
        "recommendedNextActions": list(view.recommended_next_actions),
        "driftMisprioritized": view.drift_misprioritized,
        "confidence": view.confidence,
        "providerStatus": view.provider_status,
        "providerSummary": view.provider_summary,
        "providerErrorSummary": view.provider_error_summary,
        "providerSkipReason": view.provider_skip_reason,
        "providerReview": dict(view.provider_review) if view.provider_review else None,
        "artifactPath": view.artifact_path,
    }
