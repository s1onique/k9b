"""Processor regressions for ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01.

Covers ``_process_incident`` behaviour for the ``BackendIncidentFound``
path: aggregate-based eligibility (no second store read), identity
mismatch handling, lifecycle-failure surfacing, and the exact
production-shape regression. Shared helpers live in
``authority_seam_support``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from k8s_diag_agent.collect.incident_diagnosis_authority_seam import (
    LifecycleTransition,
    LifecycleWriteApplied,
    LifecycleWriteFailed,
)
from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
)
from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
    BackendIncidentFound,
    BackendIncidentLookupSource,
)
from k8s_diag_agent.collect.incident_diagnosis_backend_detail_parser import (
    SUPPORTED_PAYLOAD_TYPE,
    SUPPORTED_SCHEMA_VERSION,
)
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import set_incident_store
from k8s_diag_agent.domain.incident_lifecycle import IncidentId
from tests.unit.authority_seam_support import (
    StubEligibility,
    canonical_incident,
    never_called,
    reset_env,
)

__all__ = ["reset_env"]  # re-export the autouse fixture for collection

_NOW = datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC)


def _found(incident_id: IncidentId, incident: Any) -> BackendIncidentFound:
    return BackendIncidentFound(
        requested_incident_id=incident_id,
        incident=incident,
        source=BackendIncidentLookupSource.BACKEND_API,
        http_status=200,
        payload_schema_version=SUPPORTED_SCHEMA_VERSION,
        payload_type=SUPPORTED_PAYLOAD_TYPE,
    )


def _stub_hypothesis_result() -> Any:
    from k8s_diag_agent.collect.incident_automatic_diagnosis_loop_state import (
        HypothesisLoopResult,
    )

    return HypothesisLoopResult(
        total_passes_completed=0,
        total_checks_executed=0,
        hypothesis_burst_written=False,
    )


def _stub_pass(**kwargs: Any) -> dict[str, Any]:
    return {
        "decision": "stop_no_checks_proposed",
        "runner_result": {"checks_requested": 0, "checks_run": 0},
        "artifact": None,
        "loop_pass_artifact": None,
    }


class TestBackendFoundProcessor:
    def test_processor_passes_aggregate_to_evaluator(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from k8s_diag_agent.collect import (
            incident_diagnosis_auto_loop_evidence_processor as processor_module,
        )

        captured: dict[str, Any] = {}

        def fake_evaluate(**kwargs: Any) -> Any:
            captured["incident"] = kwargs.get("incident")
            return StubEligibility(
                eligible=True, reason="active_incident_with_suggested_checks"
            )

        canonical = canonical_incident("incident-abc")
        monkeypatch.setattr(processor_module, "evaluate_incident_eligibility", fake_evaluate)
        monkeypatch.setattr(
            processor_module,
            "record_diagnosis_loop_started",
            lambda **kwargs: LifecycleWriteApplied(
                transition=LifecycleTransition.STARTED,
                incident_id=kwargs["incident_id"],
            ),
        )
        monkeypatch.setattr(
            processor_module,
            "record_diagnosis_loop_completed",
            lambda **kwargs: LifecycleWriteApplied(
                transition=LifecycleTransition.COMPLETED,
                incident_id=kwargs["incident_id"],
            ),
        )
        monkeypatch.setattr(processor_module, "record_diagnosis_loop_failed", never_called)
        monkeypatch.setattr(
            processor_module,
            "build_incident_case_file",
            lambda **kwargs: {"generated_at": "2026-07-12T10:00:00Z", "suggested_checks": []},
        )
        monkeypatch.setattr(
            processor_module,
            "run_automatic_diagnosis_hypothesis_loop",
            lambda *args, **kwargs: _stub_hypothesis_result(),
        )
        monkeypatch.setattr(
            processor_module, "run_policy_enforced_loop_pass", lambda **kwargs: _stub_pass()
        )
        monkeypatch.setattr(
            processor_module,
            "fetch_backend_incident_for_diagnosis_typed",
            lambda incident_id: _found(incident_id, canonical),
        )

        result = processor_module._process_incident(
            incident_id="incident-abc",
            external_analysis_dir=tmp_path,
            config=AutomaticDiagnosisLoopConfig(),
            collector_run_id="collector-test",
            now=_NOW,
        )
        assert captured.get("incident") is canonical
        assert result.error is None or "incident_not_found" not in str(result.error)
        assert result.eligible is True

    def test_no_local_store_read_before_eligibility(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from k8s_diag_agent.collect import (
            incident_diagnosis_auto_loop_evidence_processor as processor_module,
        )
        from k8s_diag_agent.collect import (
            incident_store_provider as provider_module,
        )

        seen_get_store: list[bool] = []
        original_get_store = provider_module.get_incident_store

        def tracking_get_store() -> IncidentStore:
            seen_get_store.append(True)
            return original_get_store()

        monkeypatch.setattr(provider_module, "get_incident_store", tracking_get_store)
        # The processor must not re-import get_incident_store.
        assert not hasattr(processor_module, "get_incident_store")

        canonical = canonical_incident("incident-abc")
        monkeypatch.setattr(
            processor_module,
            "fetch_backend_incident_for_diagnosis_typed",
            lambda incident_id: _found(incident_id, canonical),
        )
        monkeypatch.setattr(
            processor_module,
            "evaluate_incident_eligibility",
            lambda **kwargs: StubEligibility(
                eligible=True, reason="active_incident_with_suggested_checks"
            ),
        )
        monkeypatch.setattr(
            processor_module,
            "record_diagnosis_loop_started",
            lambda **kwargs: LifecycleWriteApplied(
                transition=LifecycleTransition.STARTED,
                incident_id=kwargs["incident_id"],
            ),
        )
        monkeypatch.setattr(
            processor_module,
            "record_diagnosis_loop_completed",
            lambda **kwargs: LifecycleWriteApplied(
                transition=LifecycleTransition.COMPLETED,
                incident_id=kwargs["incident_id"],
            ),
        )
        monkeypatch.setattr(processor_module, "record_diagnosis_loop_failed", never_called)
        monkeypatch.setattr(
            processor_module,
            "build_incident_case_file",
            lambda **kwargs: {"generated_at": "x", "suggested_checks": []},
        )
        monkeypatch.setattr(
            processor_module,
            "run_automatic_diagnosis_hypothesis_loop",
            lambda *args, **kwargs: _stub_hypothesis_result(),
        )
        monkeypatch.setattr(
            processor_module, "run_policy_enforced_loop_pass", lambda **kwargs: _stub_pass()
        )

        result = processor_module._process_incident(
            incident_id="incident-abc",
            external_analysis_dir=tmp_path,
            config=AutomaticDiagnosisLoopConfig(),
            collector_run_id="collector-test",
            now=_NOW,
        )
        assert result.eligible is True
        assert result.error is None or "incident_not_found" not in str(result.error)
        assert seen_get_store == []

    def test_identity_mismatch_surfaces_as_typed_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from k8s_diag_agent.collect import (
            incident_diagnosis_auto_loop_evidence_processor as processor_module,
        )

        mismatched = canonical_incident("incident-OTHER")
        monkeypatch.setattr(
            processor_module,
            "fetch_backend_incident_for_diagnosis_typed",
            lambda incident_id: _found(incident_id, mismatched),
        )
        result = processor_module._process_incident(
            incident_id="incident-abc",
            external_analysis_dir=tmp_path,
            config=AutomaticDiagnosisLoopConfig(),
            collector_run_id="collector-test",
            now=_NOW,
        )
        assert result.eligible is False
        assert result.eligibility_reason == "backend_incident_identity_mismatch"
        assert result.error is not None
        assert "incident-OTHER" in result.error
        assert "incident-abc" in result.error


class TestProcessorLifecycleFailures:
    def test_start_failure_prevents_diagnosis(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from k8s_diag_agent.collect import (
            incident_diagnosis_auto_loop_evidence_processor as processor_module,
        )

        canonical = canonical_incident("incident-start-fail")
        monkeypatch.setattr(
            processor_module,
            "fetch_backend_incident_for_diagnosis_typed",
            lambda incident_id: _found(incident_id, canonical),
        )
        monkeypatch.setattr(
            processor_module,
            "evaluate_incident_eligibility",
            lambda **kwargs: StubEligibility(
                eligible=True, reason="active_incident_with_suggested_checks"
            ),
        )
        monkeypatch.setattr(
            processor_module,
            "record_diagnosis_loop_started",
            lambda **kwargs: LifecycleWriteFailed(
                transition=LifecycleTransition.STARTED,
                incident_id=kwargs["incident_id"],
                reason_code="backend_url_not_configured",
            ),
        )
        monkeypatch.setattr(processor_module, "record_diagnosis_loop_completed", never_called)
        monkeypatch.setattr(processor_module, "record_diagnosis_loop_failed", never_called)

        result = processor_module._process_incident(
            incident_id="incident-start-fail",
            external_analysis_dir=tmp_path,
            config=AutomaticDiagnosisLoopConfig(),
            collector_run_id="collector-test",
            now=_NOW,
        )
        assert result.eligible is True
        assert result.error is not None
        assert "diagnosis_lifecycle_start_failed" in result.error
        assert "backend_url_not_configured" in result.error

    def test_completion_failure_does_not_claim_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from k8s_diag_agent.collect import (
            incident_diagnosis_auto_loop_evidence_processor as processor_module,
        )

        canonical = canonical_incident("incident-completion-fail")
        monkeypatch.setattr(
            processor_module,
            "fetch_backend_incident_for_diagnosis_typed",
            lambda incident_id: _found(incident_id, canonical),
        )
        monkeypatch.setattr(
            processor_module,
            "evaluate_incident_eligibility",
            lambda **kwargs: StubEligibility(
                eligible=True, reason="active_incident_with_suggested_checks"
            ),
        )
        monkeypatch.setattr(
            processor_module,
            "record_diagnosis_loop_started",
            lambda **kwargs: LifecycleWriteApplied(
                transition=LifecycleTransition.STARTED,
                incident_id=kwargs["incident_id"],
            ),
        )
        monkeypatch.setattr(processor_module, "record_diagnosis_loop_failed", never_called)
        monkeypatch.setattr(
            processor_module,
            "record_diagnosis_loop_completed",
            lambda **kwargs: LifecycleWriteFailed(
                transition=LifecycleTransition.COMPLETED,
                incident_id=kwargs["incident_id"],
                reason_code="backend_error",
            ),
        )
        monkeypatch.setattr(
            processor_module,
            "build_incident_case_file",
            lambda **kwargs: {"generated_at": "x", "suggested_checks": []},
        )
        monkeypatch.setattr(
            processor_module,
            "run_automatic_diagnosis_hypothesis_loop",
            lambda *args, **kwargs: _stub_hypothesis_result(),
        )
        monkeypatch.setattr(
            processor_module, "run_policy_enforced_loop_pass", lambda **kwargs: _stub_pass()
        )

        result = processor_module._process_incident(
            incident_id="incident-completion-fail",
            external_analysis_dir=tmp_path,
            config=AutomaticDiagnosisLoopConfig(),
            collector_run_id="collector-test",
            now=_NOW,
        )
        assert result.error is not None
        assert "diagnosis_lifecycle_completion_failed" in result.error
        assert "backend_error" in result.error


class TestProductionShapeRegression:
    def test_production_sequence_does_not_emit_incident_not_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from k8s_diag_agent.collect import (
            incident_diagnosis_auto_loop_evidence_processor as processor_module,
        )

        canonical = canonical_incident("incident-prod-shape")
        monkeypatch.setattr(
            processor_module,
            "fetch_backend_incident_for_diagnosis_typed",
            lambda incident_id: _found(incident_id, canonical),
        )
        monkeypatch.setattr(
            processor_module,
            "evaluate_incident_eligibility",
            lambda **kwargs: StubEligibility(
                eligible=True, reason="active_incident_with_suggested_checks"
            ),
        )
        # Local store is empty (production shape).
        set_incident_store(IncidentStore())

        result = processor_module._process_incident(
            incident_id="incident-prod-shape",
            external_analysis_dir=tmp_path,
            config=AutomaticDiagnosisLoopConfig(),
            collector_run_id="collector-test",
            now=_NOW,
        )
        assert result.eligibility_reason != "not_found"
        assert (result.skip_reason or "") != "not_eligible: incident_not_found"
        assert result.eligible is True
