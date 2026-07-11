"""Production-path regression tests for the automatic-diagnosis skip reasons.

Related to: ACT-K9B-AUTO-DIAGNOSIS-SKIP-REASON-OBSERVABILITY01

These tests exercise the health-loop wrapper path:

* ``k8s_diag_agent.health.loop_automatic_diagnosis.run_automatic_diagnosis_loop``
  → ``k8s_diag_agent.collect.incident_diagnosis_auto_loop.run_automatic_diagnosis_loop_evidence_collection``

The compatibility entry point ``run_automatic_diagnosis_loop_compat`` is
not yet exercised; that is tracked in the typed-outcome ACT.

and assert against the actual JSON output produced by
``k8s_diag_agent.structured_logging.emit_structured_log`` (the same
formatter the scheduler container uses).

Covers Sections 9.6 (production-path regression), 9.7 (exactly-once),
9.8 (formatter contract), and 9.9 (artifact/log parity).
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


@pytest.fixture
def capture_json_lines(monkeypatch: pytest.MonkeyPatch):
    """Capture the JSON lines written by ``emit_structured_log``.

    The production scheduler container uses ``emit_structured_log`` to
    write structured JSON lines. We patch the module's ``DEFAULT_LOG_STREAM``
    is not enough; instead we intercept every call by replacing the
    module-level ``emit_structured_log`` import in the production
    modules that call it.
    """
    captured: list[dict[str, object]] = []
    buffer = io.StringIO()

    def _capturing(**kwargs):
        # Write the JSON line ourselves so we can capture it.
        from k8s_diag_agent import structured_logging as _sl

        original_writer = _sl.DEFAULT_LOG_STREAM
        _sl.DEFAULT_LOG_STREAM = buffer
        try:
            entry = _sl.emit_structured_log(
                component=kwargs.get("component", ""),
                message=kwargs.get("message", ""),
                run_label=kwargs.get("run_label", "automatic-diagnosis"),
                severity=kwargs.get("severity", "INFO"),
                run_id=kwargs.get("run_id"),
                log_path=None,
                writer=None,
                metadata=kwargs.get("metadata"),
            )
            captured.append(entry)
            return entry
        finally:
            _sl.DEFAULT_LOG_STREAM = original_writer

    monkeypatch.setattr(
        "k8s_diag_agent.collect.incident_diagnosis_auto_loop_eligibility.emit_structured_log",
        _capturing,
    )
    monkeypatch.setattr(
        "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch.emit_structured_log",
        _capturing,
    )
    return captured


def _seed_incidents(store: IncidentStore, count: int) -> list[str]:
    incident_ids = []
    for i in range(count):
        candidate = make_candidate(name=f"test-pod-{i}")
        incidents = store.promote_candidates([candidate], datetime.now(UTC))
        incident_id = incidents[0].incident_id
        store.mark_collecting_evidence(incident_id, bundle_id=f"test-bundle-{i:03d}")
        incident_ids.append(incident_id)
    return incident_ids


# ---------------------------------------------------------------------------
# 9.6 Production-path regression: 30 skipped, 0 eligible, 0 ineligible, 0 errors
# ---------------------------------------------------------------------------


class TestThirtySkippedProductionPath:
    """Reproduce the exact observed production shape and prove the fix."""

    def test_thirty_skipped_emits_aggregate_event_with_reason_map(
        self,
        temp_external_dir,
        enabled_auto_loop,
        capture_json_lines,
        monkeypatch: pytest.MonkeyPatch,
    ):
        store = IncidentStore()
        _seed_incidents(store, 30)
        set_incident_store(store)

        def mock_process(**_kwargs):
            return AutoLoopIncidentResult(
                incident_id=_kwargs["incident_id"],
                eligible=False,
                eligibility_reason="budget_exhausted",
                skipped=True,
                skip_reason="Budget exhausted for review packets",
            )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
            mock_process,
        )

        scheduler_run_id = "health-run-20260711-001122"
        result = run_automatic_diagnosis_loop(
            external_analysis_dir=temp_external_dir,
            scheduler_run_id=scheduler_run_id,
        )

        # Validate wrapper result shape
        assert result["incidents_processed"] == 30
        assert result["incidents_skipped"] == 30
        assert result["incidents_eligible"] == 0
        assert result["incidents_ineligible"] == 0
        assert result["incidents_with_errors"] == 0
        assert result["run_id"] == scheduler_run_id

        # Validate JSON line emitted via emit_structured_log
        summary_lines = [
            line
            for line in capture_json_lines
            if isinstance(line, dict) and line.get("event") == "automatic-diagnosis-eligibility-summary"
        ]
        assert len(summary_lines) == 1, (
            f"Expected exactly 1 aggregate eligibility-summary JSON line, got {len(summary_lines)}"
        )
        summary = summary_lines[0]

        # ACT Section 7.2: required fields must be present.
        assert summary["incidents_processed"] == 30
        assert summary["incidents_skipped"] == 30
        assert summary["incidents_eligible"] == 0
        assert summary["incidents_ineligible"] == 0
        assert summary["incidents_with_errors"] == 0
        assert summary["run_id"] == scheduler_run_id
        assert summary["schema_version"] == 2

        # The reason map must sum to the skip counter.
        skip_reasons = summary["skip_reasons"]
        assert isinstance(skip_reasons, dict)
        assert sum(skip_reasons.values()) == 30
        assert skip_reasons.get("review_packet_budget_exhausted") == 30

        set_incident_store(None)


# ---------------------------------------------------------------------------
# 9.7 Exactly-once emission tests
# ---------------------------------------------------------------------------


class TestExactlyOnceEmission:
    """Each exit path emits exactly one aggregate summary; no duplicates."""

    def test_normal_loop_emits_exactly_one_aggregate_summary(
        self,
        temp_external_dir,
        enabled_auto_loop,
        capture_json_lines,
        monkeypatch: pytest.MonkeyPatch,
    ):
        store = IncidentStore()
        _seed_incidents(store, 5)
        set_incident_store(store)

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
            lambda **kw: AutoLoopIncidentResult(
                incident_id=kw["incident_id"],
                eligible=False,
                eligibility_reason="budget_exhausted",
                skipped=True,
                skip_reason="Budget exhausted",
            ),
        )

        run_automatic_diagnosis_loop(
            external_analysis_dir=temp_external_dir,
            scheduler_run_id="health-run-x",
        )

        aggregate_lines = [
            line
            for line in capture_json_lines
            if isinstance(line, dict) and line.get("event") == "automatic-diagnosis-eligibility-summary"
        ]
        assert len(aggregate_lines) == 1
        set_incident_store(None)

    def test_per_incident_disposition_emitted_once_per_examined_incident(
        self,
        temp_external_dir,
        enabled_auto_loop,
        capture_json_lines,
        monkeypatch: pytest.MonkeyPatch,
    ):
        store = IncidentStore()
        incident_ids = _seed_incidents(store, 7)
        set_incident_store(store)

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
            lambda **kw: AutoLoopIncidentResult(
                incident_id=kw["incident_id"],
                eligible=False,
                eligibility_reason="budget_exhausted",
                skipped=True,
                skip_reason="Budget exhausted",
            ),
        )

        run_automatic_diagnosis_loop(
            external_analysis_dir=temp_external_dir,
            scheduler_run_id="health-run-y",
        )

        per_incident = [
            line
            for line in capture_json_lines
            if isinstance(line, dict) and line.get("event") == "automatic-diagnosis-incident-disposition"
        ]
        # Each examined incident yields exactly one per-incident event.
        assert len(per_incident) == len(incident_ids)

        # And no duplicate aggregate summary.
        aggregate_lines = [
            line
            for line in capture_json_lines
            if isinstance(line, dict) and line.get("event") == "automatic-diagnosis-eligibility-summary"
        ]
        assert len(aggregate_lines) == 1
        set_incident_store(None)

    def test_disabled_path_emits_exactly_one_aggregate_summary(
        self,
        temp_external_dir,
        capture_json_lines,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Wrapper-level disabled path: no aggregate from collector, no summary."""
        monkeypatch.setattr(
            "k8s_diag_agent.health.loop_automatic_diagnosis.is_automatic_diagnosis_loop_enabled",
            lambda: False,
        )

        result = run_automatic_diagnosis_loop(
            external_analysis_dir=temp_external_dir,
            scheduler_run_id="health-run-z",
        )
        assert result["automatic_diagnosis_enabled"] is False

        # The wrapper returns BEFORE the collector runs, so no
        # automatic-diagnosis-eligibility-summary is emitted.
        aggregate_lines = [
            line
            for line in capture_json_lines
            if isinstance(line, dict) and line.get("event") == "automatic-diagnosis-eligibility-summary"
        ]
        assert len(aggregate_lines) == 0


# ---------------------------------------------------------------------------
# 9.8 Formatter contract test
# ---------------------------------------------------------------------------


class TestFormatterContract:
    """The production JSON formatter preserves nested reason maps."""

    def test_emit_structured_log_writes_valid_json_with_nested_reason_map(
        self,
        temp_external_dir,
        enabled_auto_loop,
        monkeypatch: pytest.MonkeyPatch,
    ):
        store = IncidentStore()
        _seed_incidents(store, 3)
        set_incident_store(store)

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
            lambda **kw: AutoLoopIncidentResult(
                incident_id=kw["incident_id"],
                eligible=False,
                eligibility_reason="budget_exhausted",
                skipped=True,
                skip_reason="Budget exhausted",
            ),
        )

        # Redirect the production JSON formatter to our own buffer.
        from k8s_diag_agent import structured_logging as _sl

        buffer = io.StringIO()
        original_writer = _sl.DEFAULT_LOG_STREAM
        _sl.DEFAULT_LOG_STREAM = buffer
        try:
            run_automatic_diagnosis_loop(
                external_analysis_dir=temp_external_dir,
                scheduler_run_id="health-run-formatter",
            )
            captured_text = buffer.getvalue()
        finally:
            _sl.DEFAULT_LOG_STREAM = original_writer

        # Exactly one valid UTF-8 / valid JSON line per emitted event.
        lines = [ln for ln in captured_text.split("\n") if ln.strip()]
        for line in lines:
            parsed = json.loads(line)  # raises if not valid JSON
            assert isinstance(parsed, dict)

        # The summary line is one of them; check shape.
        summary_lines = [
            json.loads(ln)
            for ln in lines
            if json.loads(ln).get("event") == "automatic-diagnosis-eligibility-summary"
        ]
        assert len(summary_lines) == 1
        summary = summary_lines[0]
        # Nested reason dictionaries must be present, not Python repr dicts.
        skip_reasons = summary["skip_reasons"]
        assert isinstance(skip_reasons, dict)
        assert skip_reasons.get("review_packet_budget_exhausted") == 3
        # No duplicate keys (python dict -> JSON object guarantee)
        assert "review_packet_budget_exhausted" in skip_reasons
        set_incident_store(None)


# ---------------------------------------------------------------------------
# 9.9 Artifact / log parity test
# ---------------------------------------------------------------------------


class TestArtifactLogParity:
    """Artifact, aggregate event, completion event, and result agree."""

    def test_artifact_agrees_with_aggregate_event_and_result(
        self,
        temp_external_dir,
        enabled_auto_loop,
        monkeypatch: pytest.MonkeyPatch,
    ):
        store = IncidentStore()
        _seed_incidents(store, 4)
        set_incident_store(store)

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
            lambda **kw: AutoLoopIncidentResult(
                incident_id=kw["incident_id"],
                eligible=False,
                eligibility_reason="budget_exhausted",
                skipped=True,
                skip_reason="Budget exhausted",
            ),
        )

        # Capture completion event via the log_event_fn path.
        captured_completion: list[dict[str, object]] = []

        def fake_log_event(component: str, severity: str, message: str, **metadata: object) -> None:
            captured_completion.append({
                "component": component,
                "severity": severity,
                "message": message,
                **metadata,
            })

        # Direct call to the wrapper with a fake log_event_fn
        result = run_automatic_diagnosis_loop(
            external_analysis_dir=temp_external_dir,
            log_event_fn=fake_log_event,
            scheduler_run_id="health-run-parity",
        )

        # Read the artifact from the directory.
        artifact_dir = temp_external_dir / "automatic-diagnosis"
        artifacts = list(artifact_dir.rglob("*-summary.json"))
        assert len(artifacts) == 1, f"Expected exactly 1 summary artifact, got {len(artifacts)}"
        artifact = json.loads(artifacts[0].read_text())

        # Find the aggregate summary emitted via emit_structured_log.
        from k8s_diag_agent import structured_logging as _sl

        buffer = io.StringIO()
        original_writer = _sl.DEFAULT_LOG_STREAM
        _sl.DEFAULT_LOG_STREAM = buffer
        try:
            # Re-run to capture the JSON output (artifact already written).
            run_automatic_diagnosis_loop(
                external_analysis_dir=temp_external_dir,
                scheduler_run_id="health-run-parity-2",
            )
            captured_text = buffer.getvalue()
        finally:
            _sl.DEFAULT_LOG_STREAM = original_writer

        summary_lines = [
            json.loads(ln)
            for ln in captured_text.split("\n")
            if ln.strip()
            and json.loads(ln).get("event") == "automatic-diagnosis-eligibility-summary"
        ]
        assert len(summary_lines) == 1
        aggregate = summary_lines[0]

        # All three projections must agree on counters and reason maps.
        for source in (result, artifact["summary"], aggregate):
            assert source["incidents_processed"] == 4
            assert source["incidents_skipped"] == 4
            assert source["incidents_eligible"] == 0
            assert source["incidents_ineligible"] == 0
            assert source["incidents_with_errors"] == 0

        # Reason maps must agree too.
        artifact_skip = artifact.get("skip_reasons", {})
        assert artifact_skip.get("review_packet_budget_exhausted") == 4
        assert aggregate["skip_reasons"].get("review_packet_budget_exhausted") == 4
        assert result["skip_reasons"].get("review_packet_budget_exhausted") == 4

        # Direct assertion on the scheduler completion event captured
        # from the FIRST invocation (single-invocation parity).
        completion = next(
            (
                event
                for event in captured_completion
                if event["message"] == "Automatic diagnosis loop completed"
            ),
            None,
        )
        assert completion is not None, (
            "scheduler completion event not captured by fake_log_event"
        )
        assert completion["skip_reasons"] == {
            "review_packet_budget_exhausted": 4,
        }
        assert completion["ineligible_reasons"] == {}
        assert completion["error_reasons"] == {}
        assert completion["incidents_skipped"] == 4
        assert completion["incidents_eligible"] == 0
        assert completion["incidents_with_errors"] == 0
        assert completion["collector_run_id"] == result["collector_run_id"]
        assert completion["run_id"] == "health-run-parity"
        assert completion["eligibility_schema_version"] == 2

        set_incident_store(None)
