"""TypedDict payload definitions for diagnostic-pack and drilldown contracts."""

from __future__ import annotations

from typing import TypedDict

__all__ = [
    "DiagnosticPackPayload",
    "DrilldownCoveragePayload",
    "DrilldownInterpretationPayload",
    "DrilldownSummaryPayload",
]


class DiagnosticPackPayload(TypedDict, total=False):
    """Payload for diagnostic pack metadata."""

    path: str | None
    timestamp: str | None
    label: str | None
    reviewBundlePath: str | None
    reviewInput14bPath: str | None
    # Semantic metadata: indicates whether reviewBundlePath/reviewInput14bPath point to
    # the mutable latest/ mirror (true) or immutable run-scoped artifacts (false).
    # Consumers should NOT treat isMirror=true paths as immutable references.
    isMirror: bool | None
    # Immutable source-of-truth reference: the pack ZIP path that corresponds to
    # the mirror paths when isMirror=true. Exposed so operators can reference
    # the exact immutable pack that generated the current mirror content.
    sourcePackPath: str | None


class DrilldownCoveragePayload(TypedDict):
    """Payload for drilldown coverage of a single cluster."""

    label: str
    context: str
    available: bool
    timestamp: str | None
    artifactPath: str | None


class DrilldownInterpretationPayload(TypedDict, total=False):
    """Payload for an auto-interpretation of drilldown data."""

    adapter: str
    status: str
    summary: str | None
    timestamp: str
    artifactPath: str | None
    provider: str | None
    durationMs: int | None
    payload: dict[str, object] | None
    errorSummary: str | None
    skipReason: str | None


class DrilldownSummaryPayload(TypedDict):
    """Payload for drilldown availability summary."""

    totalClusters: int
    available: int
    missing: int
    missingClusters: list[str]
