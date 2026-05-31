"""TypedDict payload definitions for fleet and status contracts."""

from __future__ import annotations

from typing import TypedDict

from .api_payloads_primitives import ProblemSummary
from .api_payloads_proposals import ProposalSummaryPayload, RatingCount

__all__ = [
    "FreshnessPayload",
    "RunStatsPayload",
    "FleetStatusPayload",
    "ClusterSummaryPayload",
    "FleetPayload",
]


class FreshnessPayload(TypedDict, total=False):
    """Payload for run freshness indicator."""

    ageSeconds: int | None
    expectedIntervalSeconds: int | None
    status: str | None


class RunStatsPayload(TypedDict):
    """Payload for run statistics."""

    lastRunDurationSeconds: int | None
    totalRuns: int
    p50RunDurationSeconds: int | None
    p95RunDurationSeconds: int | None
    p99RunDurationSeconds: int | None


class FleetStatusPayload(TypedDict):
    """Payload for fleet-level status summary."""

    ratingCounts: list[RatingCount]
    degradedClusters: list[str]


class ClusterSummaryPayload(TypedDict):
    """Payload for cluster summary in fleet view."""

    label: str
    context: str
    clusterClass: str
    clusterRole: str
    baselineCohort: str
    controlPlaneVersion: str
    healthRating: str
    warnings: int
    nonRunningPods: int
    latestRunTimestamp: str
    topTriggerReason: str | None
    drilldownAvailable: bool
    drilldownTimestamp: str | None
    missingEvidence: list[str]


class FleetPayload(TypedDict):
    """Payload for the fleet overview response."""

    runId: str
    runLabel: str
    lastRunTimestamp: str
    topProblem: ProblemSummary
    fleetStatus: FleetStatusPayload
    clusters: list[ClusterSummaryPayload]
    proposalSummary: ProposalSummaryPayload
