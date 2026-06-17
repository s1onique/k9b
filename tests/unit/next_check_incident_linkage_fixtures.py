"""Shared test fixtures for next_check_incident_linkage tests.

This module contains reusable helper factories for tests:
- make_incident_candidate()
- make_linkage_context()

No test assertions, no test cases.
"""

from __future__ import annotations

from k8s_diag_agent.collect.incident_candidates import (
    CandidateClass,
    IncidentCandidate,
    ObjectKind,
    Severity,
)
from k8s_diag_agent.external_analysis.next_check_incident_linkage_contracts import (
    IncidentLinkageContext,
)


def make_incident_candidate(
    candidate_id: str = "test-candidate",
    namespace: str = "default",
    object_kind: ObjectKind = ObjectKind.POD,
    object_name: str = "test-pod",
    candidate_class: CandidateClass = CandidateClass.CRASH_LOOP,
) -> IncidentCandidate:
    """Create a test incident candidate."""
    return IncidentCandidate(
        candidate_id=candidate_id,
        namespace=namespace,
        object_kind=object_kind,
        object_name=object_name,
        candidate_class=candidate_class,
        severity=Severity.ERROR,
        signals=(),
        evidence_needed=("kubectl logs",),
    )


def make_linkage_context(
    incident_id: str | None = "default-pod-test-pod-crash-loop",
    source_candidate_id: str | None = "test-candidate",
    namespace: str | None = "default",
    object_kind: str | None = "Pod",
    object_name: str | None = "test-pod",
    candidate_class: str | None = "crash_loop",
    run_id: str | None = "run-123",
) -> IncidentLinkageContext:
    """Create a test linkage context."""
    return IncidentLinkageContext(
        incident_id=incident_id,
        source_candidate_id=source_candidate_id,
        namespace=namespace,
        object_kind=object_kind,
        object_name=object_name,
        candidate_class=candidate_class,
        run_id=run_id,
    )
