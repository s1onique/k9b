"""Shared fixtures and helpers for incident store tests.

This module contains:
- Standard test timestamps
- Candidate factory function
- IncidentStore factory

Not prefixed with `test_` to avoid pytest treating it as a test module.
"""

from __future__ import annotations

from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    CandidateSignal,
    IncidentCandidate,
    ObjectKind,
    Severity,
)
from k8s_diag_agent.collect.incident_store import IncidentStore

# Standard test timestamps
TEST_TIME_1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
TEST_TIME_2 = datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC)
TEST_TIME_3 = datetime(2024, 1, 1, 14, 0, 0, tzinfo=UTC)


def make_candidate(
    name: str,
    namespace: str = "default",
    candidate_class: CandidateClass = CandidateClass.CRASH_LOOP,
    object_kind: ObjectKind = ObjectKind.POD,
    raw_object_kind: str | None = None,
) -> IncidentCandidate:
    """Helper to create test candidates."""
    return IncidentCandidate(
        candidate_id=f"{namespace}-{object_kind.value.lower()}-{name}-{candidate_class.value}",
        namespace=namespace,
        object_kind=object_kind,
        object_name=name,
        candidate_class=candidate_class,
        severity=Severity.ERROR,
        signals=(
            CandidateSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="Back-off restarting",
            ),
        ),
        evidence_needed=("pod_logs", "pod_describe"),
        raw_object_kind=raw_object_kind,
    )


def make_store() -> IncidentStore:
    """Factory for creating a fresh IncidentStore instance."""
    return IncidentStore()
