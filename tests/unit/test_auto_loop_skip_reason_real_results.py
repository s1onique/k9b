"""Real-result tests that exercise actual eligibility evaluation.

Related to: ACT-K9B-AUTO-DIAGNOSIS-SKIP-REASON-OBSERVABILITY01

Covers Section 9.10 (real-result tests): at least one test must use real
eligibility evaluation rather than mocking every incident result.

These tests construct real incidents in a real ``IncidentStore``, run
real eligibility evaluation, and verify the resulting closed-vocabulary
reason codes naturally fall out of the disposition ADT.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop import (
    run_automatic_diagnosis_loop_evidence_collection,
)
from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
)
from k8s_diag_agent.collect.incident_diagnosis_disposition import (
    DiagnosisIneligibleReason,
    DiagnosisSkipReason,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import set_incident_store
from tests.unit.incident_store_fixtures import make_candidate


@pytest.fixture
def temp_external_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def enabled_auto_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "k8s_diag_agent.collect."
        "incident_diagnosis_auto_loop_evidence_collection."
        "is_automatic_diagnosis_loop_enabled",
        lambda: True,
    )


def _create_incident_with_status(
    store: IncidentStore, *, name: str, status: IncidentStatus
) -> str:
    candidate = make_candidate(name=name)
    incidents = store.promote_candidates([candidate], datetime.now(UTC))
    incident_id: str = str(incidents[0].incident_id)
    if status == IncidentStatus.COLLECTING_EVIDENCE:
        store.mark_collecting_evidence(incident_id, bundle_id=f"bundle-{name}")
    elif status == IncidentStatus.RESOLVED:
        # ``IncidentStore`` exposes ``mark_ready_for_review`` as a
        # terminal-state transition that the eligibility layer
        # classifies identically to RESOLVED. We use it because the
        # in-memory store doesn't have a literal ``mark_resolved``
        # helper; the disposition logic only cares about being in a
        # terminal status, not how we got there.
        store.mark_collecting_evidence(incident_id, bundle_id=f"bundle-{name}")
        store.mark_ready_for_review(incident_id)
    elif status == IncidentStatus.OPEN:
        # No-op; promote leaves it in OPEN.
        pass
    else:  # pragma: no cover - exhaustiveness
        raise ValueError(f"Unsupported status {status}")
    return incident_id


class TestRealEligibilityResults:
    """Real eligibility evaluation naturally produces closed-vocabulary reasons."""

    def test_active_incident_with_review_packets_is_skipped_via_budget(
        self, temp_external_dir, enabled_auto_loop, monkeypatch: pytest.MonkeyPatch
    ):
        """R1 contract: pre-existing review packets do NOT cause a fresh
        collector to skip a new incident. The collector-local
        :class:`ReviewPacketCreationBudget` is the authoritative
        accounting source; the historical filesystem count is bypassed.

        Exhaustion is reached only when the budget's
        ``can_attempt()`` returns ``False`` after successful packet
        writes inside the same collector run.
        """
        store = IncidentStore()
        incident_id = _create_incident_with_status(
            store, name="pod-budget", status=IncidentStatus.COLLECTING_EVIDENCE
        )

        # Drop a fake "auto-" review packet into the external-analysis
        # dir; under the legacy contract this would push the count over
        # ``max_passes_per_incident``. Under the R1 contract the
        # collector-local budget starts at zero usage regardless.
        external_dir = temp_external_dir
        external_dir.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            (external_dir / f"auto-{incident_id}-run{i}-diagnosis-review-packet.json").write_text("{}")

        set_incident_store(store)

        config = AutomaticDiagnosisLoopConfig(
            max_incidents_per_run=10,
            max_passes_per_incident=2,
        )

        try:
            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=external_dir,
                config=config,
                incident_ids=[incident_id],
            )

            # R1: the incident is NOT skipped because of historical packets.
            # It may be eligible or ineligible for other reasons; this test
            # only asserts the legacy ``review_packet_budget_exhausted``
            # skip is no longer triggered by pre-existing artifacts.
            summary_skip_reasons = (
                result.disposition_summary.skip_reasons
                if result.disposition_summary is not None
                else {}
            )
            assert (
                DiagnosisSkipReason.REVIEW_PACKET_BUDGET_EXHAUSTED
                not in summary_skip_reasons
            )
        finally:
            set_incident_store(None)

    def test_terminal_status_incident_is_ineligible(
        self, temp_external_dir, enabled_auto_loop, monkeypatch: pytest.MonkeyPatch
    ):
        """A RESOLVED incident is terminal and is classified as ineligible."""
        store = IncidentStore()
        incident_id = _create_incident_with_status(
            store, name="pod-terminal", status=IncidentStatus.RESOLVED
        )
        set_incident_store(store)

        try:
            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=[incident_id],
            )

            assert result.incidents_ineligible == 1
            assert result.incidents_skipped == 0
            assert result.dispositions
            assert result.disposition_summary is not None
            summary = result.disposition_summary
            assert summary.ineligible == 1
            assert summary.ineligible_reasons.get(DiagnosisIneligibleReason.TERMINAL_STATUS) == 1
            _assert_conservation(summary)
        finally:
            set_incident_store(None)


def _assert_conservation(summary) -> None:
    """Conservation invariant from the disposition summary."""
    assert summary.is_consistent()
    assert summary.processed == (
        summary.eligible + summary.skipped + summary.ineligible + summary.errors
    )
