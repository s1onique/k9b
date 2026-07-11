"""Regression tests for ``incidents_with_errors`` propagation.

Related to: ACT-K9B-AUTO-DIAGNOSIS-SKIP-REASON-OBSERVABILITY01

These tests pin the observability contract that an eligible incident
with a downstream execution error still increments
``incidents_with_errors`` in every projection:

* the collector result returned by the wrapper;
* the scheduler completion event;
* the aggregate eligibility-summary structured event;
* the summary artifact on disk.

The compatibility counter (``execution_errors``) is added to
``summary.errors`` by the batch processor and then propagated
through the wrapper result, the aggregate event, the artifact,
and the completion event. R2 will replace this with typed
execution counters; R1 (observability) preserves the pre-ADT truth.
"""

from __future__ import annotations

import io
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import (
    AutoLoopIncidentResult,
)
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import set_incident_store
from k8s_diag_agent.health.loop_automatic_diagnosis import run_automatic_diagnosis_loop
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
    monkeypatch.setattr(
        "k8s_diag_agent.health.loop_automatic_diagnosis."
        "is_automatic_diagnosis_loop_enabled",
        lambda: True,
    )


def _seed_incidents(store: IncidentStore, count: int) -> list[str]:
    incident_ids: list[str] = []
    for i in range(count):
        candidate = make_candidate(name=f"exec-pod-{i}")
        incidents = store.promote_candidates([candidate], datetime.now(UTC))
        incident_id = incidents[0].incident_id
        store.mark_collecting_evidence(incident_id, bundle_id=f"exec-bundle-{i:03d}")
        incident_ids.append(incident_id)
    return incident_ids


class TestEligibleWithDownstreamError:
    """An eligible incident with a downstream error increments all four
    ``incidents_with_errors`` projections."""

    def test_eligible_with_downstream_error_propagates_through_all_projections(
        self,
        temp_external_dir,
        enabled_auto_loop,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store = IncidentStore()
        _seed_incidents(store, 1)
        set_incident_store(store)

        # One eligible incident that encountered a downstream execution
        # error. The legacy error string lives alongside the eligible
        # flag; pre-ADT, this would have incremented
        # ``incidents_with_errors``.
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
            lambda **kw: AutoLoopIncidentResult(
                incident_id=kw["incident_id"],
                eligible=True,
                eligibility_reason="active",
                error="downstream execution failed",
                run_id=f"run-{kw['incident_id']}",
                checks_run=1,
            ),
        )

        captured_completion: list[dict[str, object]] = []

        def fake_log_event(component: str, severity: str, message: str, **metadata: object) -> None:
            captured_completion.append({
                "component": component,
                "severity": severity,
                "message": message,
                **metadata,
            })

        result = run_automatic_diagnosis_loop(
            external_analysis_dir=temp_external_dir,
            log_event_fn=fake_log_event,
            scheduler_run_id="health-run-exec-error",
        )

        # 1. Wrapper result.
        assert result["incidents_eligible"] == 1
        assert result["incidents_with_errors"] == 1, (
            "wrapper result must carry the compatibility execution-error counter"
        )

        # 2. Summary artifact.
        artifact_path = next(temp_external_dir.glob("automatic-diagnosis/**/*-summary.json"), None)
        assert artifact_path is not None
        artifact = json.loads(artifact_path.read_text())
        assert artifact["summary"]["incidents_with_errors"] == 1

        # 3. Aggregate structured event.
        captured_aggregate = self._capture_aggregate_event(temp_external_dir)
        assert captured_aggregate["incidents_eligible"] == 1
        assert captured_aggregate["incidents_with_errors"] == 1

        # 4. Scheduler completion event.
        completion = next(
            (
                event
                for event in captured_completion
                if event["message"] == "Automatic diagnosis loop completed"
            ),
            None,
        )
        assert completion is not None, "scheduler completion event not captured"
        assert completion["incidents_eligible"] == 1
        assert completion["incidents_with_errors"] == 1

        set_incident_store(None)

    def _capture_aggregate_event(self, temp_external_dir: Path) -> dict[str, object]:
        """Re-run the wrapper once to capture the JSON line written by
        ``emit_structured_log`` to ``DEFAULT_LOG_STREAM``."""
        # Reset the in-memory store before the second run so the second
        # run sees the same single-incident fixture.
        set_incident_store(None)
        store = IncidentStore()
        _seed_incidents(store, 1)
        set_incident_store(store)
        from k8s_diag_agent import structured_logging as _sl

        buffer = io.StringIO()
        original = _sl.DEFAULT_LOG_STREAM
        _sl.DEFAULT_LOG_STREAM = buffer
        try:
            run_automatic_diagnosis_loop(
                external_analysis_dir=temp_external_dir,
                scheduler_run_id="health-run-exec-error-2",
            )
            text = buffer.getvalue()
        finally:
            _sl.DEFAULT_LOG_STREAM = original
        set_incident_store(None)
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if payload.get("event") == "automatic-diagnosis-eligibility-summary":
                return payload  # type: ignore[no-any-return]
        raise AssertionError("aggregate event not found in captured output")
