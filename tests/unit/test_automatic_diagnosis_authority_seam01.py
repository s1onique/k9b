"""Unit tests for ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01.

Aggregate-based eligibility, backend not-found / payload-failure
regressions, single-fetch, local-mode compatibility, and the lifecycle
outcome contract. The processor regressions live in
``test_automatic_diagnosis_authority_seam01_processor.py`` and the
lifecycle endpoint / backend dispatch / idempotency tests live in
``test_automatic_diagnosis_authority_seam01_endpoint.py``. Verifier
self-tests live in ``test_automatic_diagnosis_authority_seam01_verifier.py``.

The split-authority defect closed by this ACT was: a backend-fetched
incident was re-resolved through the **local** incident store for
eligibility, producing ``not_eligible: incident_not_found`` even though
the backend returned HTTP 200 with a valid canonical incident.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

import pytest

from k8s_diag_agent.collect import (
    incident_diagnosis_authority_seam as seam_module,
)
from k8s_diag_agent.collect.incident_diagnosis_authority_seam import (
    LIFECYCLE_SCHEMA_VERSION,
    LifecycleTransition,
    LifecycleWriteApplied,
    build_lifecycle_request,
    check_incident_eligibility,
    evaluate_incident_eligibility,
    record_diagnosis_loop_started,
)
from k8s_diag_agent.collect.incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
)
from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
    BackendIncidentFound,
    BackendIncidentLookupFailed,
    BackendIncidentLookupFailureCode,
    BackendIncidentLookupSource,
    BackendIncidentNotFound,
)
from k8s_diag_agent.collect.incident_diagnosis_backend_detail_parser import (
    SUPPORTED_PAYLOAD_TYPE,
    SUPPORTED_SCHEMA_VERSION,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import set_incident_store
from k8s_diag_agent.domain.incident_lifecycle import IncidentId
from k8s_diag_agent.ui.server_incident_diagnosis_lifecycle_handler import (
    SUPPORTED_TRANSITIONS as HANDLER_SUPPORTED_TRANSITIONS,
)
from tests.unit.authority_seam_support import (
    StubEligibility,
    canonical_incident,
    encode,
    reset_env,
)

__all__ = ["reset_env"]  # re-export the autouse fixture for collection


class TestAggregateEvaluator:
    def test_eligible_incident_is_evaluated_without_store_access(
        self, tmp_path: Path
    ) -> None:
        config = AutomaticDiagnosisLoopConfig()
        incident = canonical_incident("incident-eligible")
        for name in (
            "get_incident_store",
            "fetch_backend_incident_for_diagnosis_typed",
            "fetch_incident_for_diagnosis",
        ):
            assert not hasattr(seam_module, name) or callable(
                getattr(seam_module, name)
            )
        result = evaluate_incident_eligibility(incident=incident, config=config)
        assert result.eligible is True
        assert result.incident_id == "incident-eligible"
        assert result.reason == "active_incident_with_suggested_checks"
        assert result.budget_diagnostics[0].exhausted is False

    def test_terminal_status_returns_terminal_reason(self) -> None:
        config = AutomaticDiagnosisLoopConfig()
        incident = canonical_incident("incident-resolved", IncidentStatus.RESOLVED)
        result = evaluate_incident_eligibility(incident=incident, config=config)
        assert result.eligible is False
        assert result.reason == "terminal_status_resolved"
        assert result.status == "resolved"

    def test_inactive_status_returns_inactive_reason(self) -> None:
        config = AutomaticDiagnosisLoopConfig()
        incident = canonical_incident("incident-rfr", IncidentStatus.READY_FOR_REVIEW)
        result = evaluate_incident_eligibility(incident=incident, config=config)
        assert result.eligible is False
        assert result.reason == "terminal_status_ready_for_review"

    def test_suppressed_incident_ineligible(self) -> None:
        config = AutomaticDiagnosisLoopConfig()
        incident = canonical_incident("incident-sup", IncidentStatus.SUPPRESSED)
        result = evaluate_incident_eligibility(incident=incident, config=config)
        assert result.eligible is False
        assert "terminal" in result.reason

    def test_duplicate_incident_ineligible(self) -> None:
        config = AutomaticDiagnosisLoopConfig()
        incident = canonical_incident("incident-dup", IncidentStatus.DUPLICATE)
        result = evaluate_incident_eligibility(incident=incident, config=config)
        assert result.eligible is False
        assert "terminal" in result.reason

    def test_budget_exhaustion_preserves_policy(self, tmp_path: Path) -> None:
        config = AutomaticDiagnosisLoopConfig(max_passes_per_incident=1)
        (tmp_path / "auto-incident-budget-20260101120000-diagnosis-review-packet.json").write_text("{}")
        incident = canonical_incident("incident-budget")
        result = evaluate_incident_eligibility(
            incident=incident, config=config, external_analysis_dir=tmp_path
        )
        assert result.eligible is False
        assert result.reason == "budget_exhausted"
        assert result.budget_diagnostics[0].exhausted is True

    def test_evaluator_does_not_call_get_incident_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The aggregate evaluator lives in
        # ``incident_diagnosis_auto_loop_config``; ensure it does NOT
        # delegate to ``get_incident_store`` by patching the symbol on
        # the config module. ``seam_module`` no longer references the
        # store directly because the local-mode writer was extracted
        # into a sibling module.
        from k8s_diag_agent.collect import (
            incident_diagnosis_auto_loop_config as config_module,
        )

        def boom(*args: object, **kwargs: object) -> NoReturn:
            raise AssertionError("get_incident_store was called")

        monkeypatch.setattr(config_module, "get_incident_store", boom)
        config = AutomaticDiagnosisLoopConfig()
        incident = canonical_incident("incident-no-lookup")
        result = evaluate_incident_eligibility(incident=incident, config=config)
        assert result.eligible is True

    def test_supplied_incident_id_is_identity_in_diagnostics(self) -> None:
        config = AutomaticDiagnosisLoopConfig()
        incident = canonical_incident("incident-identity")
        result = evaluate_incident_eligibility(incident=incident, config=config)
        assert result.incident_id == "incident-identity"

    def test_local_compat_wrapper_delegates_to_evaluator(self) -> None:
        store = IncidentStore()
        set_incident_store(store)
        incident = canonical_incident("incident-local")
        store._incidents[incident.incident_id] = incident
        result = check_incident_eligibility(
            incident_id="incident-local", config=AutomaticDiagnosisLoopConfig()
        )
        assert result.eligible is True

    def test_local_compat_wrapper_returns_not_found(self) -> None:
        set_incident_store(IncidentStore())
        result = check_incident_eligibility(
            incident_id="missing", config=AutomaticDiagnosisLoopConfig()
        )
        assert result.eligible is False
        assert result.reason == "incident_not_found"


class TestBackendNotFound:
    def test_404_emits_skipped_not_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from k8s_diag_agent.collect import (
            incident_diagnosis_auto_loop_evidence_processor as processor_module,
        )

        def fake_typed(incident_id: IncidentId) -> BackendIncidentNotFound:
            return BackendIncidentNotFound(
                requested_incident_id=incident_id,
                source=BackendIncidentLookupSource.BACKEND_API,
                http_status=404,
            )

        monkeypatch.setattr(
            processor_module,
            "fetch_backend_incident_for_diagnosis_typed",
            fake_typed,
        )
        result = processor_module._process_incident(
            incident_id="missing-incident",
            external_analysis_dir=tmp_path,
            config=AutomaticDiagnosisLoopConfig(),
            collector_run_id="collector-test",
            now=datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC),
        )
        assert result.eligible is False
        assert result.skip_reason == "incident_not_found"
        assert result.eligibility_reason == "not_found"
        assert result.skipped is True


class TestBackendPayloadFailures:
    @pytest.mark.parametrize(
        "body,expected_code",
        [
            (b"", BackendIncidentLookupFailureCode.INVALID_JSON),
            (b"{not valid json", BackendIncidentLookupFailureCode.INVALID_JSON),
            (
                encode({"schema_version": "1", "payload_type": "wrong"}),
                BackendIncidentLookupFailureCode.INVALID_PAYLOAD,
            ),
            (
                encode({
                    "schema_version": "999",
                    "payload_type": SUPPORTED_PAYLOAD_TYPE,
                    "incident": {"incident_id": "x"},
                }),
                BackendIncidentLookupFailureCode.UNSUPPORTED_SCHEMA,
            ),
        ],
    )
    def test_malformed_200_never_maps_to_not_found(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        body: bytes,
        expected_code: BackendIncidentLookupFailureCode,
    ) -> None:
        from k8s_diag_agent.collect import (
            incident_diagnosis_auto_loop_evidence_processor as processor_module,
        )

        def fake_typed(incident_id: IncidentId) -> BackendIncidentLookupFailed:
            return BackendIncidentLookupFailed(
                requested_incident_id=incident_id,
                failure_code=expected_code,
                detail="synthetic",
                http_status=200,
            )

        monkeypatch.setattr(
            processor_module,
            "fetch_backend_incident_for_diagnosis_typed",
            fake_typed,
        )
        result = processor_module._process_incident(
            incident_id="incident-abc",
            external_analysis_dir=tmp_path,
            config=AutomaticDiagnosisLoopConfig(),
            collector_run_id="collector-test",
            now=datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC),
        )
        assert result.eligible is False
        assert result.eligibility_reason != "not_found"
        assert "incident_not_found" not in (result.skip_reason or "")
        assert "backend_incident_" in result.eligibility_reason


class TestSingleFetch:
    def test_one_processed_incident_means_one_detail_get(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from k8s_diag_agent.collect import (
            incident_diagnosis_auto_loop_evidence_processor as processor_module,
        )

        call_count = {"detail_gets": 0}
        canonical = canonical_incident("incident-abc")

        def fake_typed(incident_id: IncidentId) -> BackendIncidentFound:
            call_count["detail_gets"] += 1
            return BackendIncidentFound(
                requested_incident_id=incident_id,
                incident=canonical,
                source=BackendIncidentLookupSource.BACKEND_API,
                http_status=200,
                payload_schema_version=SUPPORTED_SCHEMA_VERSION,
                payload_type=SUPPORTED_PAYLOAD_TYPE,
            )

        monkeypatch.setattr(
            processor_module,
            "fetch_backend_incident_for_diagnosis_typed",
            fake_typed,
        )
        monkeypatch.setattr(
            processor_module,
            "evaluate_incident_eligibility",
            lambda **kwargs: StubEligibility(
                eligible=True, reason="active_incident_with_suggested_checks"
            ),
        )
        processor_module._process_incident(
            incident_id="incident-abc",
            external_analysis_dir=tmp_path,
            config=AutomaticDiagnosisLoopConfig(),
            collector_run_id="collector-test",
            now=datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC),
        )
        assert call_count["detail_gets"] == 1


class TestLocalModeCompatibility:
    def test_local_found_delegates_to_aggregate_evaluator(self) -> None:
        store = IncidentStore()
        set_incident_store(store)
        incident = canonical_incident("incident-local")
        store._incidents[incident.incident_id] = incident
        result = check_incident_eligibility(
            incident_id="incident-local", config=AutomaticDiagnosisLoopConfig()
        )
        assert result.eligible is True
        assert result.reason == "active_incident_with_suggested_checks"

    def test_local_absence_yields_incident_not_found(self) -> None:
        set_incident_store(IncidentStore())
        result = check_incident_eligibility(
            incident_id="missing", config=AutomaticDiagnosisLoopConfig()
        )
        assert result.eligible is False
        assert result.reason == "incident_not_found"

    def test_local_mode_lifecycle_via_local_store(self) -> None:
        store = IncidentStore()
        set_incident_store(store)
        incident = canonical_incident("incident-local-lifecycle")
        store._incidents[incident.incident_id] = incident
        outcome = record_diagnosis_loop_started(
            incident_id="incident-local-lifecycle",
            run_id="run-1",
            collector_run_id="collector-1",
        )
        assert isinstance(outcome, LifecycleWriteApplied)
        assert outcome.http_status is None  # local mode

    def test_local_mode_no_backend_http(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def must_not_be_called(*args: Any, **kwargs: Any) -> NoReturn:
            raise AssertionError("backend HTTP must not be called in local mode")

        # The backend-mode HTTP transport lives in the seam_backend
        # sibling module; patch its ``urllib.request.urlopen`` symbol.
        from k8s_diag_agent.collect import (
            incident_diagnosis_authority_seam_backend as seam_backend_module,
        )

        monkeypatch.setattr(
            seam_backend_module.urllib.request, "urlopen", must_not_be_called
        )
        store = IncidentStore()
        set_incident_store(store)
        incident = canonical_incident("incident-local")
        store._incidents[incident.incident_id] = incident
        outcome = record_diagnosis_loop_started(
            incident_id="incident-local", run_id="r", collector_run_id="c"
        )
        assert isinstance(outcome, LifecycleWriteApplied)


class TestLifecycleOutcomeContract:
    def test_lifecycle_request_shape(self) -> None:
        request = build_lifecycle_request(
            incident_id="incident-x",
            transition=LifecycleTransition.STARTED,
            collector_run_id="collector-x",
            diagnosis_run_id="run-x",
            payload={"key": "value"},
        )
        body = request.to_dict()
        assert body["schemaVersion"] == LIFECYCLE_SCHEMA_VERSION
        assert body["incidentId"] == "incident-x"
        assert body["transition"] == "started"
        assert body["collectorRunId"] == "collector-x"
        assert body["diagnosisRunId"] == "run-x"
        assert body["payload"] == {"key": "value"}

    def test_supported_transitions_match_handler(self) -> None:
        for transition in LifecycleTransition:
            assert transition.value in HANDLER_SUPPORTED_TRANSITIONS
