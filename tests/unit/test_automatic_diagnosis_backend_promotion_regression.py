"""Promotion-to-diagnosis regression test for
ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01.

Reproduces the production sequence from
``health-run-20260712T123805Z``:

* promotion returns a canonical incident ID,
* automatic diagnosis receives the explicit canonical ID,
* the backend GET returns HTTP 200 with a canonical incident detail,
* the typed lookup returns ``BackendIncidentFound``,
* the eligibility path evaluates the incident,
* no ``incident_not_found`` disposition is emitted.

The test does NOT require an LLM provider. The regression lives
before provider invocation: it proves that the typed backend lookup
boundary is no longer misclassifying HTTP 200 + valid JSON as
``incident_not_found``.
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from k8s_diag_agent.collect.incident_diagnosis_auto_loop import (
    run_automatic_diagnosis_loop_evidence_collection,
)
from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import (
    AutoLoopIncidentResult,
)
from k8s_diag_agent.collect.incident_diagnosis_backend_detail_lookup import (
    BackendIncidentHttpResponse,
)
from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
    BackendIncidentFound,
    BackendIncidentNotFound,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_external_dir() -> Iterable[Path]:
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


def _canonical_payload(
    incident_id: str = "incident-canonical-abc",
) -> dict[str, Any]:
    """Build the exact wrapped canonical payload the backend emits."""
    return {
        "schema_version": "1",
        "payload_type": "incident-internal-detail",
        "incident": {
            "incident_id": incident_id,
            "source_candidate_id": "candidate-source-xyz",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "nginx-pod",
            "class": "PodCrashLoop",
            "severity": "high",
            "status": IncidentStatus.OPEN.value,
            "first_observed_at": "2026-07-12T10:00:00+00:00",
            "last_observed_at": "2026-07-12T10:30:00+00:00",
            "signal_count": 1,
            "evidence_count": 0,
        },
    }


def _capture_logging() -> tuple[list[dict[str, Any]], logging.Handler]:
    captured: list[dict[str, Any]] = []

    class LogCapture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            d = record.__dict__
            captured.append({
                "event": d.get("event"),
                "disposition": d.get("disposition"),
                "reason_code": d.get("reason_code"),
                "detail": d.get("detail"),
                "incident_id": d.get("incident_id"),
                "incidents_processed": d.get("incidents_processed"),
                "incidents_eligible": d.get("incidents_eligible"),
                "incidents_skipped": d.get("incidents_skipped"),
                "incidents_with_errors": d.get("incidents_with_errors"),
                "skip_reasons": d.get("skip_reasons"),
                "error_reasons": d.get("error_reasons"),
                "explicit_canonical_id_count": d.get("explicit_canonical_id_count"),
                "promotion_propagated_to_diagnosis": d.get("promotion_propagated_to_diagnosis"),
                "selection_mode": d.get("selection_mode"),
                "incident_access_mode": d.get("incident_access_mode"),
            })

    handler = LogCapture()
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return captured, handler


# ---------------------------------------------------------------------------
# 1. End-to-end regression: production sequence reproduces no false absence
# ---------------------------------------------------------------------------


class TestPromotionToDiagnosisRegression:
    """Reproduce ``health-run-20260712T123805Z`` after the fix."""

    def test_production_sequence_does_not_emit_incident_not_found(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The full production flow must NOT classify 200 as not-found."""

        canonical_id = "incident-canonical-abc"
        # Backend serves a valid 200 with the canonical wrapped payload.
        payload_bytes = json.dumps(_canonical_payload(canonical_id)).encode("utf-8")
        response = BackendIncidentHttpResponse(http_status=200, body=payload_bytes)

        # Replace the canonical lookup helper so every backend GET
        # returns the canned 200 response. The lookup function itself
        # is the seam under test.
        def fake_fetch_incident(
            incident_id: Any, *, timeout: float = 30.0
        ) -> BackendIncidentHttpResponse:
            return response

        # Force backend mode so the typed dispatch goes through the
        # canonical lookup path.
        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "backend-api")
        monkeypatch.setenv("K9B_BACKEND_INTERNAL_URL", "http://backend.test:8080")
        monkeypatch.setenv("K9B_INTERNAL_API_TOKEN", "test-token-not-secret")
        monkeypatch.setenv("K9B_INCIDENT_STORE_BACKEND", "sqlite")
        monkeypatch.setenv("K9B_PROCESS_ROLE", "scheduler")

        # Stub the eligibility check so we don't run real downstream
        # work; we only need to observe the backend-lookup seam.

        eligibility_stub_calls: list[str] = []

        def fake_evaluate_incident_eligibility(**kwargs: Any) -> Any:
            eligibility_stub_calls.append(kwargs["incident_id"])
            return _StubEligibility(eligible=True, reason="active_incident_with_suggested_checks")

        # R1 follow-up: the processor now calls
        # ``evaluate_incident_eligibility`` (the canonical
        # eligibility evaluator). The monkeypatch target must
        # match the symbol the processor actually invokes.
        monkeypatch.setattr(
            "k8s_diag_agent.collect."
            "incident_diagnosis_auto_loop_evidence_processor."
            "evaluate_incident_eligibility",
            fake_evaluate_incident_eligibility,
        )

        # Inject a fake ``BackendIncidentClient`` via the typed lookup
        # module's symbol so ``HttpIncidentBackendClient`` is bypassed
        # entirely.
        from k8s_diag_agent.collect import (
            incident_diagnosis_backend_detail_lookup as detail_lookup,
        )

        class _FakeClient:
            def __init__(self) -> None:
                self.calls: list[Any] = []

            def fetch_incident(
                self,
                incident_id: Any,
                *,
                timeout: float = 30.0,
            ) -> BackendIncidentHttpResponse:
                self.calls.append(incident_id)
                return response

        fake_client = _FakeClient()
        monkeypatch.setattr(
            detail_lookup,
            "HttpIncidentBackendClient",
            lambda base_url, token=None: fake_client,
        )

        # Skip the actual diagnosis execution paths (they would
        # attempt real LLM providers); the regression lives at the
        # typed-lookup boundary, so we can stop after eligibility.
        # NOTE: we patch ``incident_diagnosis_auto_loop_batch._process_incident``
        # (not the evidence-processor module) because the batch
        # processor calls its own module-level reference.
        from k8s_diag_agent.collect import (
            incident_diagnosis_auto_loop_batch as batch_module,
        )

        original_process = batch_module._process_incident
        call_count = {"n": 0}

        def stub_process_incident(**kwargs: Any) -> AutoLoopIncidentResult:
            call_count["n"] += 1
            # Reach through the typed lookup to prove the seam works
            # end-to-end.
            from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
                fetch_backend_incident_for_diagnosis_typed,
            )
            from k8s_diag_agent.domain.incident_lifecycle import IncidentId

            incident_id = IncidentId(kwargs["incident_id"])
            outcome = fetch_backend_incident_for_diagnosis_typed(incident_id)
            assert isinstance(outcome, BackendIncidentFound), (
                f"Expected BackendIncidentFound, got {type(outcome).__name__}"
            )
            # Skip real downstream work; mark eligible.
            return AutoLoopIncidentResult(
                incident_id=kwargs["incident_id"],
                eligible=True,
                eligibility_reason="active_incident_with_suggested_checks",
            )

        monkeypatch.setattr(batch_module, "_process_incident", stub_process_incident)

        captured, handler = _capture_logging()
        try:
            # Promotion result returns canonical ID.
            promotion_summary = {
                "promotion_record_count": 1,
                "incident_access_mode": "backend",
                "firing": 1,
                "scanned": 1,
                "opened_incidents": 0,
                "updated_incidents": 1,
                "errors": 0,
                "unique_candidate_count": 1,
                "promotion_mode": "backend-api",
            }

            # Automatic diagnosis is invoked with the explicit canonical ID.
            from k8s_diag_agent.health.loop_automatic_diagnosis import (
                run_automatic_diagnosis_loop,
            )

            result = run_automatic_diagnosis_loop(
                external_analysis_dir=temp_external_dir,
                scheduler_run_id="health-run-20260712T123805Z",
                canonical_incident_ids=[canonical_id],
                promotion_result_summary=promotion_summary,
                backend_endpoint_identity={"incident_access_mode": "backend"},
            )

            # --- Assertions on the automatic-diagnosis completion event ---
            assert result["automatic_diagnosis_enabled"] is True
            assert result["explicit_canonical_id_count"] == 1
            assert result["promotion_propagated_to_diagnosis"] is True
            assert result["selection_mode"] == "explicit_incident_ids"
            assert result["incident_access_mode"] == "backend"

            assert result["incidents_processed"] == 1
            # Crucially: no incident_not_found disposition was emitted.
            assert result["incidents_skipped"] == 0
            assert "incident_not_found" not in result.get("skip_reasons", {})
            # Either eligible or a legitimate domain-ineligible reason is
            # acceptable; what is NOT acceptable is any backend-incident
            # error or skip with reason_code incident_not_found.
            assert result.get("error_reasons", {}) == {}
            assert call_count["n"] == 1
            assert len(fake_client.calls) == 1

            # No per-incident disposition event with reason_code == incident_not_found
            for log in captured:
                if log.get("event") == "automatic-diagnosis-incident-disposition":
                    assert log.get("reason_code") != "incident_not_found", (
                        f"False absence detected: {log}"
                    )
        finally:
            logging.getLogger().removeHandler(handler)
            # Restore the original to avoid leaking monkeypatch state.
            batch_module._process_incident = original_process

    def test_production_sequence_with_real_dispatch_path(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Drive the full evidence collection through the typed dispatch.

        This time we drive ``run_automatic_diagnosis_loop_evidence_collection``
        directly so we exercise the typed dispatch + batch processor
        seam end-to-end without mocking ``_process_incident``.
        """

        canonical_id = "incident-canonical-abc"
        payload_bytes = json.dumps(_canonical_payload(canonical_id)).encode("utf-8")

        # Stub the eligibility check + downstream execution so the
        # loop completes without trying to invoke LLM providers.
        # Patch the batch module reference (not the evidence processor)
        # so the batch loop sees the stub.
        from k8s_diag_agent.collect import (
            incident_diagnosis_auto_loop_batch as batch_module,
        )

        def stub_process_incident(**kwargs: Any) -> AutoLoopIncidentResult:
            incident_id_str = kwargs["incident_id"]
            # Use the real typed dispatch path.
            from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
                fetch_backend_incident_for_diagnosis_typed,
            )
            from k8s_diag_agent.domain.incident_lifecycle import IncidentId

            outcome = fetch_backend_incident_for_diagnosis_typed(
                IncidentId(incident_id_str)
            )
            assert isinstance(outcome, BackendIncidentFound), (
                f"Backend HTTP 200 with canonical payload must yield "
                f"BackendIncidentFound, got {type(outcome).__name__}"
            )
            # Mark eligible so we get an "eligible" disposition.
            return AutoLoopIncidentResult(
                incident_id=incident_id_str,
                eligible=True,
                eligibility_reason="active_incident_with_suggested_checks",
            )

        # Inject a fake ``BackendIncidentClient`` via the typed lookup.
        from k8s_diag_agent.collect import (
            incident_diagnosis_backend_detail_lookup as detail_lookup,
        )

        class _FakeClient:
            def __init__(self) -> None:
                self.calls: list[Any] = []

            def fetch_incident(
                self,
                incident_id: Any,
                *,
                timeout: float = 30.0,
            ) -> BackendIncidentHttpResponse:
                self.calls.append(incident_id)
                return BackendIncidentHttpResponse(
                    http_status=200, body=payload_bytes
                )

        fake_client = _FakeClient()

        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "backend-api")
        monkeypatch.setenv("K9B_BACKEND_INTERNAL_URL", "http://backend.test:8080")
        monkeypatch.setenv("K9B_INTERNAL_API_TOKEN", "test-token-not-secret")
        monkeypatch.setenv("K9B_INCIDENT_STORE_BACKEND", "sqlite")
        monkeypatch.setenv("K9B_PROCESS_ROLE", "scheduler")

        monkeypatch.setattr(
            detail_lookup,
            "HttpIncidentBackendClient",
            lambda base_url, token=None: fake_client,
        )
        monkeypatch.setattr(batch_module, "_process_incident", stub_process_incident)

        captured, handler = _capture_logging()
        try:
            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=[canonical_id],
            )
            assert result.incidents_processed == 1
            assert result.incidents_skipped == 0
            assert "incident_not_found" not in result.disposition_summary.skip_reasons
            assert result.disposition_summary.error_reasons == {}
            # The fake client was invoked exactly once.
            assert len(fake_client.calls) == 1

            # No per-incident disposition event must be incident_not_found.
            for log in captured:
                if log.get("event") == "automatic-diagnosis-incident-disposition":
                    assert log.get("reason_code") != "incident_not_found", (
                        f"Production regression: incident_not_found emitted for HTTP 200: {log}"
                    )
        finally:
            logging.getLogger().removeHandler(handler)


# ---------------------------------------------------------------------------
# 2. End-to-end regression: 404 still emits not-found (NOT a regression)
# ---------------------------------------------------------------------------


class TestGenuineNotFoundStillMapsCorrectly:
    """A real 404 must still emit ``skipped / incident_not_found``."""

    def test_genuine_404_emits_skipped_incident_not_found(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from k8s_diag_agent.collect import (
            incident_diagnosis_auto_loop_batch as batch_module,
        )
        from k8s_diag_agent.collect import (
            incident_diagnosis_backend_detail_lookup as detail_lookup,
        )

        class _FakeClient:
            def fetch_incident(
                self,
                incident_id: Any,
                *,
                timeout: float = 30.0,
            ) -> BackendIncidentHttpResponse:
                return BackendIncidentHttpResponse(http_status=404, body=b"")

        monkeypatch.setenv("K9B_INCIDENT_PROMOTION_MODE", "backend-api")
        monkeypatch.setenv("K9B_BACKEND_INTERNAL_URL", "http://backend.test:8080")
        monkeypatch.setenv("K9B_INTERNAL_API_TOKEN", "test-token")
        monkeypatch.setenv("K9B_INCIDENT_STORE_BACKEND", "sqlite")
        monkeypatch.setenv("K9B_PROCESS_ROLE", "scheduler")

        monkeypatch.setattr(
            detail_lookup,
            "HttpIncidentBackendClient",
            lambda base_url, token=None: _FakeClient(),
        )

        def stub_process_incident(**kwargs: Any) -> AutoLoopIncidentResult:
            # Real typed dispatch.
            from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
                fetch_backend_incident_for_diagnosis_typed,
            )
            from k8s_diag_agent.domain.incident_lifecycle import IncidentId

            outcome = fetch_backend_incident_for_diagnosis_typed(
                IncidentId(kwargs["incident_id"])
            )
            assert isinstance(outcome, BackendIncidentNotFound)
            return AutoLoopIncidentResult(
                incident_id=kwargs["incident_id"],
                eligible=False,
                eligibility_reason="not_found",
                skipped=True,
                skip_reason="incident_not_found",
            )

        monkeypatch.setattr(batch_module, "_process_incident", stub_process_incident)

        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=temp_external_dir,
            incident_ids=["incident-missing"],
        )
        assert result.incidents_processed == 1
        assert result.incidents_skipped == 1
        assert result.disposition_summary.skip_reasons.get(
            "incident_not_found"
        ) == 1


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------


class _StubEligibility:
    eligible: bool
    reason: str
    budget_diagnostics: tuple[Any, ...]

    def __init__(
        self,
        *,
        eligible: bool,
        reason: str,
        budget_diagnostics: tuple[Any, ...] = (),
    ) -> None:
        self.eligible = eligible
        self.reason = reason
        self.budget_diagnostics = budget_diagnostics
