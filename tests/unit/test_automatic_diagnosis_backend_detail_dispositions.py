"""Integration tests for automatic-diagnosis disposition mapping.

These tests pin the contract from
ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01:

* ``BackendIncidentFound`` continues into domain eligibility.
* ``BackendIncidentNotFound`` emits ``skipped / incident_not_found``.
* ``BackendIncidentLookupFailed`` emits ``error / <mapped reason code>``.
* Lookup failures increment ``incidents_with_errors`` /
  ``error_reasons.<code>`` and never ``incidents_skipped`` /
  ``skip_reasons.incident_not_found``.
* A failure on one incident does not abort processing of later
  selected incidents.
* Diagnostics remain bounded.

The tests inject a fake ``_process_incident`` so the batch processor
sees the exact ``AutoLoopIncidentResult`` projection the new lookup
path would emit. The compat layer is then exercised end-to-end through
``run_automatic_diagnosis_loop_evidence_collection``.
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
from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
    BackendIncidentLookupFailureCode,
)
from k8s_diag_agent.collect.incident_diagnosis_disposition import (
    AutomaticDiagnosisEvaluationFailed,
    SkippedFromAutomaticDiagnosis,
    reduce_disposition,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_FAILURE_REASON_BY_CODE: dict[BackendIncidentLookupFailureCode, str] = {
    BackendIncidentLookupFailureCode.INVALID_JSON: "backend_incident_invalid_json",
    BackendIncidentLookupFailureCode.INVALID_PAYLOAD: "backend_incident_invalid_payload",
    BackendIncidentLookupFailureCode.UNSUPPORTED_SCHEMA: "backend_incident_unsupported_schema",
    BackendIncidentLookupFailureCode.DESERIALIZATION_FAILED: "backend_incident_deserialization_failed",
    BackendIncidentLookupFailureCode.IDENTITY_MISMATCH: "backend_incident_identity_mismatch",
    BackendIncidentLookupFailureCode.UNAUTHORIZED: "backend_incident_unauthorized",
    BackendIncidentLookupFailureCode.FORBIDDEN: "backend_incident_forbidden",
    BackendIncidentLookupFailureCode.HTTP_CLIENT_ERROR: "backend_incident_http_client_error",
    BackendIncidentLookupFailureCode.BACKEND_ERROR: "backend_incident_backend_error",
    BackendIncidentLookupFailureCode.TRANSPORT_ERROR: "backend_incident_transport_error",
}


@pytest.fixture
def temp_external_dir() -> Iterable[Path]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def enabled_auto_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the enabled production path without consulting the environment."""
    monkeypatch.setattr(
        "k8s_diag_agent.collect."
        "incident_diagnosis_auto_loop_evidence_collection."
        "is_automatic_diagnosis_loop_enabled",
        lambda: True,
    )


def _summary_from_logs(captured: list[dict[str, Any]]) -> dict[str, Any]:
    summary_logs = [
        log for log in captured if log.get("event") == "automatic-diagnosis-eligibility-summary"
    ]
    assert len(summary_logs) == 1, (
        f"Expected exactly one eligibility summary event, got {len(summary_logs)}"
    )
    return summary_logs[0]


def _capture_logging() -> tuple[list[dict[str, Any]], Any]:
    captured: list[dict[str, Any]] = []

    class LogCapture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            d = record.__dict__
            captured.append({
                "message": record.getMessage(),
                "event": d.get("event"),
                "incidents_processed": d.get("incidents_processed"),
                "incidents_eligible": d.get("incidents_eligible"),
                "incidents_skipped": d.get("incidents_skipped"),
                "incidents_ineligible": d.get("incidents_ineligible"),
                "incidents_with_errors": d.get("incidents_with_errors"),
                "skip_reasons": d.get("skip_reasons"),
                "ineligible_reasons": d.get("ineligible_reasons"),
                "error_reasons": d.get("error_reasons"),
                "stop_reason": d.get("stop_reason"),
            })

    handler = LogCapture()
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return captured, handler


# ---------------------------------------------------------------------------
# 1. Found outcome → continues into eligibility
# ---------------------------------------------------------------------------


class TestFoundOutcomeMapping:
    def test_found_outcome_continues_into_eligibility(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``BackendIncidentFound`` → continue with domain eligibility."""

        captured, handler = _capture_logging()
        try:
            def fake_process(**kwargs: Any) -> AutoLoopIncidentResult:
                # Pretend the incident was found and is eligible.
                return AutoLoopIncidentResult(
                    incident_id=kwargs["incident_id"],
                    eligible=True,
                    eligibility_reason="active_incident_with_suggested_checks",
                    decision="STOP_ROOT_CAUSE_FOUND",
                    checks_requested=2,
                    checks_run=2,
                    review_packet_written=True,
                )

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
                fake_process,
            )

            incident_ids = [f"incident-{i}" for i in range(3)]
            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=incident_ids,
            )
            summary = _summary_from_logs(captured)
            assert summary["incidents_processed"] == 3
            assert summary["incidents_eligible"] == 3
            assert summary["incidents_skipped"] == 0
            assert summary["incidents_with_errors"] == 0
            assert summary["error_reasons"] == {}
            assert "incident_not_found" not in summary["skip_reasons"]
            assert result.incidents_eligible == 3
        finally:
            logging.getLogger().removeHandler(handler)

    def test_found_but_domain_ineligible_is_counted_as_ineligible(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Found → domain ineligibility → ``ineligible / terminal_status``.

        The legacy compat layer routes ``terminal_status_*`` to
        :class:`IneligibleForAutomaticDiagnosis`, not ``Skipped``. The
        important contract is that domain ineligibility is NOT
        ``incident_not_found`` and never increments the error counter.
        """

        captured, handler = _capture_logging()
        try:
            def fake_process(**kwargs: Any) -> AutoLoopIncidentResult:
                return AutoLoopIncidentResult(
                    incident_id=kwargs["incident_id"],
                    eligible=False,
                    eligibility_reason="terminal_status_resolved",
                    skipped=True,
                    skip_reason="not_eligible: terminal_status_resolved",
                )

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
                fake_process,
            )

            run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=["incident-1", "incident-2"],
            )
            summary = _summary_from_logs(captured)
            assert summary["incidents_processed"] == 2
            assert summary["incidents_with_errors"] == 0
            assert summary["ineligible_reasons"]["terminal_status"] == 2
            # ``incident_not_found`` must not be confused with domain ineligibility.
            assert "incident_not_found" not in summary["skip_reasons"]
        finally:
            logging.getLogger().removeHandler(handler)

    def test_found_eligible_result_counts_as_eligible(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured, handler = _capture_logging()
        try:
            def fake_process(**kwargs: Any) -> AutoLoopIncidentResult:
                return AutoLoopIncidentResult(
                    incident_id=kwargs["incident_id"],
                    eligible=True,
                    eligibility_reason="active_incident_with_suggested_checks",
                )

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
                fake_process,
            )
            run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=["incident-1"],
            )
            summary = _summary_from_logs(captured)
            assert summary["incidents_eligible"] == 1
            assert summary["incidents_skipped"] == 0
        finally:
            logging.getLogger().removeHandler(handler)


# ---------------------------------------------------------------------------
# 2. NotFound outcome → skipped / incident_not_found
# ---------------------------------------------------------------------------


class TestNotFoundOutcomeMapping:
    def test_not_found_outcome_emits_skipped_incident_not_found(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured, handler = _capture_logging()
        try:
            def fake_process(**kwargs: Any) -> AutoLoopIncidentResult:
                # Pretend the lookup returned ``BackendIncidentNotFound``.
                return AutoLoopIncidentResult(
                    incident_id=kwargs["incident_id"],
                    eligible=False,
                    eligibility_reason="not_found",
                    skipped=True,
                    skip_reason="incident_not_found",
                )

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
                fake_process,
            )

            result = run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=["incident-1", "incident-2"],
            )
            summary = _summary_from_logs(captured)
            assert summary["incidents_processed"] == 2
            assert summary["incidents_skipped"] == 2
            assert summary["incidents_with_errors"] == 0
            assert summary["skip_reasons"]["incident_not_found"] == 2
            # The error map must remain empty.
            assert summary["error_reasons"] == {}
            assert result.incidents_skipped == 2
        finally:
            logging.getLogger().removeHandler(handler)

    def test_not_found_does_not_increment_errors(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured, handler = _capture_logging()
        try:
            def fake_process(**kwargs: Any) -> AutoLoopIncidentResult:
                return AutoLoopIncidentResult(
                    incident_id=kwargs["incident_id"],
                    eligible=False,
                    eligibility_reason="not_found",
                    skipped=True,
                    skip_reason="incident_not_found",
                )

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
                fake_process,
            )
            run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=["incident-1"],
            )
            summary = _summary_from_logs(captured)
            assert summary["incidents_with_errors"] == 0
        finally:
            logging.getLogger().removeHandler(handler)


# ---------------------------------------------------------------------------
# 3. Failed outcome → error with mapped stable reason code
# ---------------------------------------------------------------------------


class TestFailedOutcomeMapping:
    @pytest.mark.parametrize(
        "failure_code",
        list(BackendIncidentLookupFailureCode),
    )
    def test_each_failure_code_maps_to_error_disposition(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        monkeypatch: pytest.MonkeyPatch,
        failure_code: BackendIncidentLookupFailureCode,
    ) -> None:
        """Every backend incident failure code emits an error disposition."""

        captured, handler = _capture_logging()
        try:
            reason = _FAILURE_REASON_BY_CODE[failure_code]

            def fake_process(**kwargs: Any) -> AutoLoopIncidentResult:
                return AutoLoopIncidentResult(
                    incident_id=kwargs["incident_id"],
                    eligible=False,
                    eligibility_reason=reason,
                    error=(
                        f"backend lookup failed (http_status=200 failure_code="
                        f"{failure_code.value} payload_type='incident-internal-detail'"
                        f" payload_schema_version=1 exception_type='None')"
                    ),
                )

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
                fake_process,
            )
            run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=["incident-1"],
            )
            summary = _summary_from_logs(captured)
            assert summary["incidents_processed"] == 1, (
                f"[{failure_code}] processed count"
            )
            assert summary["incidents_with_errors"] == 1, (
                f"[{failure_code}] incidents_with_errors"
            )
            assert summary["incidents_skipped"] == 0, (
                f"[{failure_code}] incidents_skipped"
            )
            assert summary["skip_reasons"] == {}, (
                f"[{failure_code}] skip_reasons must be empty for failed lookups"
            )
            assert summary["error_reasons"][reason] == 1, (
                f"[{failure_code}] error_reasons map"
            )
        finally:
            logging.getLogger().removeHandler(handler)

    def test_lookup_failure_increments_errors_and_populates_error_reasons(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured, handler = _capture_logging()
        try:
            def fake_process(**kwargs: Any) -> AutoLoopIncidentResult:
                return AutoLoopIncidentResult(
                    incident_id=kwargs["incident_id"],
                    eligible=False,
                    eligibility_reason="backend_incident_unsupported_schema",
                    error="schema 99 not supported",
                )

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
                fake_process,
            )
            run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=["incident-1", "incident-2"],
            )
            summary = _summary_from_logs(captured)
            assert summary["incidents_with_errors"] == 2
            assert summary["error_reasons"]["backend_incident_unsupported_schema"] == 2
        finally:
            logging.getLogger().removeHandler(handler)

    def test_lookup_failure_does_not_populate_skip_reasons_incident_not_found(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured, handler = _capture_logging()
        try:
            def fake_process(**kwargs: Any) -> AutoLoopIncidentResult:
                return AutoLoopIncidentResult(
                    incident_id=kwargs["incident_id"],
                    eligible=False,
                    eligibility_reason="backend_incident_invalid_json",
                    error="invalid JSON",
                )

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
                fake_process,
            )
            run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=["incident-1"],
            )
            summary = _summary_from_logs(captured)
            assert "incident_not_found" not in summary["skip_reasons"]
            assert summary["incidents_skipped"] == 0
            assert summary["incidents_with_errors"] == 1
        finally:
            logging.getLogger().removeHandler(handler)


# ---------------------------------------------------------------------------
# 4. Mixed inputs
# ---------------------------------------------------------------------------


class TestMixedOutcomes:
    def test_mixed_found_notfound_failed_produce_correct_totals(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Found + NotFound + Failed in one run → correct per-kind totals."""

        outcomes: list[str] = ["found", "notfound", "failed", "found", "notfound"]

        def fake_process(**kwargs: Any) -> AutoLoopIncidentResult:
            incident_id = kwargs["incident_id"]
            index = int(incident_id.rsplit("-", 1)[-1])
            outcome = outcomes[index]
            if outcome == "found":
                return AutoLoopIncidentResult(
                    incident_id=incident_id,
                    eligible=True,
                    eligibility_reason="active_incident_with_suggested_checks",
                )
            if outcome == "notfound":
                return AutoLoopIncidentResult(
                    incident_id=incident_id,
                    eligible=False,
                    eligibility_reason="not_found",
                    skipped=True,
                    skip_reason="incident_not_found",
                )
            return AutoLoopIncidentResult(
                incident_id=incident_id,
                eligible=False,
                eligibility_reason="backend_incident_identity_mismatch",
                error="identity mismatch",
            )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
            fake_process,
        )

        captured, handler = _capture_logging()
        try:
            run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=[f"incident-{i}" for i in range(len(outcomes))],
            )
            summary = _summary_from_logs(captured)
            assert summary["incidents_processed"] == 5
            assert summary["incidents_eligible"] == 2
            assert summary["incidents_skipped"] == 2
            assert summary["incidents_with_errors"] == 1
            assert summary["skip_reasons"]["incident_not_found"] == 2
            assert summary["error_reasons"]["backend_incident_identity_mismatch"] == 1
        finally:
            logging.getLogger().removeHandler(handler)

    def test_failure_on_one_incident_does_not_abort_later_incidents(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured, handler = _capture_logging()
        try:
            call_count = {"n": 0}

            def fake_process(**kwargs: Any) -> AutoLoopIncidentResult:
                call_count["n"] += 1
                if call_count["n"] == 1:
                    return AutoLoopIncidentResult(
                        incident_id=kwargs["incident_id"],
                        eligible=False,
                        eligibility_reason="backend_incident_transport_error",
                        error="timeout",
                    )
                return AutoLoopIncidentResult(
                    incident_id=kwargs["incident_id"],
                    eligible=True,
                    eligibility_reason="active_incident_with_suggested_checks",
                )

            monkeypatch.setattr(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_batch._process_incident",
                fake_process,
            )
            run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=[f"incident-{i}" for i in range(5)],
            )
            summary = _summary_from_logs(captured)
            assert call_count["n"] == 5
            assert summary["incidents_processed"] == 5
            assert summary["incidents_with_errors"] == 1
            assert summary["incidents_eligible"] == 4
        finally:
            logging.getLogger().removeHandler(handler)


# ---------------------------------------------------------------------------
# 5. Disposition compat matrix
# ---------------------------------------------------------------------------


class TestCompatMatrix:
    """The compat layer maps every backend incident code to the right variant."""

    def test_not_found_compat_maps_to_skip_incident_not_found(self) -> None:
        result = AutoLoopIncidentResult(
            incident_id="incident-abc",
            eligible=False,
            eligibility_reason="not_found",
            skipped=True,
            skip_reason="incident_not_found",
        )
        from k8s_diag_agent.collect.incident_diagnosis_disposition_compat import (
            disposition_from_legacy_result,
        )

        disposition = disposition_from_legacy_result(result)
        assert isinstance(disposition, SkippedFromAutomaticDiagnosis)
        from k8s_diag_agent.collect.incident_diagnosis_disposition import (
            DiagnosisSkipReason,
        )

        assert disposition.reason == DiagnosisSkipReason.INCIDENT_NOT_FOUND

    def test_each_backend_failure_code_compat_maps_to_evaluation_failed(self) -> None:
        from k8s_diag_agent.collect.incident_diagnosis_disposition import (
            DiagnosisEvaluationFailureReason,
        )
        from k8s_diag_agent.collect.incident_diagnosis_disposition_compat import (
            disposition_from_legacy_result,
        )

        for code in BackendIncidentLookupFailureCode:
            reason = _FAILURE_REASON_BY_CODE[code]
            result = AutoLoopIncidentResult(
                incident_id="incident-abc",
                eligible=False,
                eligibility_reason=reason,
                error=f"backend returned failure_code={code.value}",
            )
            disposition = disposition_from_legacy_result(result)
            assert isinstance(disposition, AutomaticDiagnosisEvaluationFailed), (
                f"[{code.value}] must map to AutomaticDiagnosisEvaluationFailed"
            )
            # The reason must be the canonical enum value, NOT a generic fallback.
            expected_member = DiagnosisEvaluationFailureReason(reason)
            assert disposition.reason == expected_member

    def test_compat_preserves_conservation_invariants(self) -> None:
        """Per-incident reductions must keep the summary consistent."""
        from k8s_diag_agent.collect.incident_diagnosis_disposition import (
            empty_disposition_summary,
        )
        from k8s_diag_agent.collect.incident_diagnosis_disposition_compat import (
            disposition_from_legacy_result,
        )

        results: list[AutoLoopIncidentResult] = [
            AutoLoopIncidentResult(
                incident_id="i-1",
                eligible=True,
                eligibility_reason="active_incident_with_suggested_checks",
            ),
            AutoLoopIncidentResult(
                incident_id="i-2",
                eligible=False,
                eligibility_reason="not_found",
                skipped=True,
                skip_reason="incident_not_found",
            ),
            AutoLoopIncidentResult(
                incident_id="i-3",
                eligible=False,
                eligibility_reason="backend_incident_invalid_payload",
                error="bad envelope",
            ),
        ]
        summary = empty_disposition_summary()
        for result in results:
            disposition = disposition_from_legacy_result(result)
            summary = reduce_disposition(summary, disposition)
        assert summary.is_consistent()
        assert summary.processed == 3
        assert summary.eligible == 1
        assert summary.skipped == 1
        assert summary.errors == 1


# ---------------------------------------------------------------------------
# 6. Diagnostic bounds
# ---------------------------------------------------------------------------


class TestDiagnosticBounds:
    def test_failure_diagnostic_carries_safe_metadata_only(self) -> None:
        """Diagnostic projection must not contain Authorization / Bearer / token."""

        from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
            BackendIncidentLookupDiagnostic,
            BackendIncidentLookupFailed,
        )
        from k8s_diag_agent.domain.incident_lifecycle import IncidentId

        outcome = BackendIncidentLookupFailed(
            requested_incident_id=IncidentId("incident-abc"),
            failure_code=BackendIncidentLookupFailureCode.TRANSPORT_ERROR,
            detail="connection refused",
            http_status=None,
            exception_type="ConnectionRefusedError",
        )
        diagnostic = outcome.to_diagnostic()
        assert isinstance(diagnostic, BackendIncidentLookupDiagnostic)
        assert diagnostic.failure_code == BackendIncidentLookupFailureCode.TRANSPORT_ERROR
        assert diagnostic.http_status is None
        assert diagnostic.exception_type == "ConnectionRefusedError"
        assert diagnostic.requested_incident_id == IncidentId("incident-abc")

    def test_failure_detail_is_truncated(self) -> None:
        from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
            BackendIncidentLookupFailed,
        )
        from k8s_diag_agent.domain.incident_lifecycle import IncidentId

        huge = "x" * 5000
        outcome = BackendIncidentLookupFailed(
            requested_incident_id=IncidentId("incident-abc"),
            failure_code=BackendIncidentLookupFailureCode.INVALID_PAYLOAD,
            detail=huge,
            http_status=200,
        )
        diagnostic = outcome.to_diagnostic()
        assert diagnostic.detail is not None
        assert len(diagnostic.detail) <= 512


# ---------------------------------------------------------------------------
# 7. Production-path regression test (R1)
# ---------------------------------------------------------------------------


class TestProductionPathRegression:
    """Integration-style test that does NOT replace ``_process_incident``.

    The real evidence processor is exercised end-to-end. Only
    downstream work is patched:

    * the hypothesis burst multipass loop (LLM-free) returns an empty
      payload,
    * the policy-enforced loop pass is short-circuited,
    * the review-packet writer is stubbed so we do not write to disk
      beyond the ``external_analysis_dir`` summary artifact.

    The test uses the canonical
    :func:`build_incident_internal_detail_response_payload` backend
    serializer to build a valid 200 payload for the canonical
    "found" case, the canonical parser for the "invalid payload"
    case, and a hand-rolled ``BackendIncidentHttpResponse`` for the
    "404 not found" case.
    """

    @pytest.fixture
    def seeded_incident_store(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Seed the local incident store with an eligible incident so
        the ``_process_incident`` eligibility check returns ``True``
        after the lookup succeeds.
        """
        from datetime import UTC, datetime

        from k8s_diag_agent.collect.incident_lifecycle import (
            Incident,
            IncidentStatus,
        )
        from k8s_diag_agent.collect.incident_store import IncidentStore
        from k8s_diag_agent.collect.incident_store_provider import (
            set_incident_store,
        )

        incident = Incident(
            incident_id="incident-r1-found",
            source_candidate_id="candidate-r1",
            namespace="default",
            object_kind="Pod",
            object_name="nginx-pod",
            raw_object_kind=None,
            candidate_class="PodCrashLoop",
            severity="high",
            status=IncidentStatus.OPEN,
            first_observed_at=datetime(2026, 7, 12, 10, 0, 0, tzinfo=UTC),
            last_observed_at=datetime(2026, 7, 12, 10, 30, 0, tzinfo=UTC),
            signal_count=1,
            evidence_count=0,
        )
        store = IncidentStore()
        store.add_incident(incident)
        set_incident_store(store)
        yield incident
        set_incident_store(None)

    def _run_production_path(
        self,
        *,
        body: bytes,
        http_status: int,
        monkeypatch: pytest.MonkeyPatch,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        incident_ids: list[str],
    ) -> dict[str, Any]:
        """Run the production loop with a single fake HTTP client.

        Patches the ``BackendIncidentClient`` implementation that
        ``HttpIncidentBackendClient`` builds so we never touch the
        network.
        """
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop import (
            run_automatic_diagnosis_loop_evidence_collection,
        )
        from k8s_diag_agent.collect.incident_diagnosis_dispatch_contracts import (
            IncidentDiagnosisDispatchConfig,
        )

        # Force the dispatch mode to backend-api so the canonical
        # HTTP lookup path is exercised instead of the local store.
        def _backend_api_config() -> IncidentDiagnosisDispatchConfig:
            return IncidentDiagnosisDispatchConfig(
                mode="backend-api",
                backend_url="http://fake-backend.test",
                internal_api_token=None,
                store_backend="memory",
                process_role="scheduler",
            )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_dispatch._get_dispatch_config",
            _backend_api_config,
        )

        # Patch downstream work so the processor returns quickly
        # without invoking the LLM / disk artifacts.
        class _FakeHypothesis:
            def to_dict(self) -> dict[str, Any]:
                return {}

        def _fake_hypothesis_loop(**kwargs: Any) -> _FakeHypothesis:
            return _FakeHypothesis()

        def _fake_policy_pass(**kwargs: Any) -> dict[str, Any]:
            return {
                "decision": "STOP_NO_SAFE_CHECKS",
                "runner_result": {
                    "checks_requested": 0,
                    "checks_run": 0,
                    "checks_skipped": 0,
                    "checks_rejected": 0,
                },
                "artifact": {"written": False},
                "loop_pass_artifact": {"written": False},
            }

        def _fake_review_packet(**kwargs: Any) -> dict[str, Any]:
            return {"written": False}

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
            "run_automatic_diagnosis_hypothesis_loop",
            _fake_hypothesis_loop,
        )
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
            "run_policy_enforced_loop_pass",
            _fake_policy_pass,
        )
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
            "write_diagnosis_review_packet",
            _fake_review_packet,
        )

        # Force the canonical lookup to use our fake HTTP client.
        from k8s_diag_agent.collect.incident_diagnosis_backend_detail_lookup import (
            BackendIncidentHttpResponse,
        )

        class _FakeHttpClient:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def fetch_incident(
                self, incident_id: object, *, timeout: float = 30.0
            ) -> BackendIncidentHttpResponse:
                self.calls.append(str(incident_id))
                return BackendIncidentHttpResponse(
                    http_status=http_status,
                    body=body,
                )

        fake = _FakeHttpClient()

        class _FakeClientFactory:
            def __init__(self, fake: _FakeHttpClient) -> None:
                self._fake = fake

            def __call__(self, *, base_url: str, token: object) -> _FakeHttpClient:
                return self._fake

        # The dispatch module imports the client class lazily inside
        # the function body. Patch the symbol in the lookup module
        # namespace (which is where the canonical lookup references
        # it) before the function runs.
        import k8s_diag_agent.collect.incident_diagnosis_backend_detail_lookup as lookup_mod

        class _FakeHttpIncidentBackendClient:
            def __init__(self, *, base_url: str, token: object) -> None:
                self._fake = fake

            def fetch_incident(
                self, incident_id: object, *, timeout: float = 30.0
            ) -> BackendIncidentHttpResponse:
                return self._fake.fetch_incident(incident_id, timeout=timeout)

        monkeypatch.setattr(
            lookup_mod,
            "HttpIncidentBackendClient",
            _FakeHttpIncidentBackendClient,
        )

        captured, handler = _capture_logging()
        try:
            run_automatic_diagnosis_loop_evidence_collection(
                external_analysis_dir=temp_external_dir,
                incident_ids=incident_ids,
            )
        finally:
            logging.getLogger().removeHandler(handler)
        return _summary_from_logs(captured)

    def test_200_canonical_payload_produces_found_outcome(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        seeded_incident_store: object,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """HTTP 200 + canonical payload -> ``Found`` -> eligibility ->
        processed=1, skipped=0, errors=0, real eligibility reached.
        """
        from k8s_diag_agent.ui.api_incident_internal_reads import (
            build_incident_internal_detail_response_payload,
        )

        canonical_payload = build_incident_internal_detail_response_payload(
            seeded_incident_store
        )
        body = json.dumps(canonical_payload).encode("utf-8")

        summary = self._run_production_path(
            body=body,
            http_status=200,
            monkeypatch=monkeypatch,
            temp_external_dir=temp_external_dir,
            enabled_auto_loop=enabled_auto_loop,
            incident_ids=["incident-r1-found"],
        )

        assert summary["incidents_processed"] == 1
        assert summary["incidents_skipped"] == 0
        assert summary["incidents_with_errors"] == 0
        assert "incident_not_found" not in summary["skip_reasons"]

    def test_200_invalid_payload_produces_failed_outcome(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        seeded_incident_store: object,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """HTTP 200 + valid JSON but invalid envelope contract
        (missing ``incident`` aggregate) -> ``Failed`` -> processed=1,
        errors=1, error_reasons=backend_incident_invalid_payload exactly.

        This proves the seam classifies a successfully-decoded-but-invalid
        payload as ``INVALID_PAYLOAD`` (not ``INVALID_JSON`` and never
        ``incident_not_found``). The malformed-JSON case is exercised by
        :meth:`test_200_malformed_json_produces_failed_outcome`.
        """
        import json as _json

        invalid_envelope = {
            "schema_version": "1",
            "payload_type": "incident-internal-detail",
            # Intentionally missing the required ``incident`` aggregate.
        }
        invalid_body = _json.dumps(invalid_envelope).encode("utf-8")
        summary = self._run_production_path(
            body=invalid_body,
            http_status=200,
            monkeypatch=monkeypatch,
            temp_external_dir=temp_external_dir,
            enabled_auto_loop=enabled_auto_loop,
            incident_ids=["incident-r1-found"],
        )
        assert summary["incidents_processed"] == 1
        assert summary["incidents_with_errors"] == 1
        assert summary["incidents_skipped"] == 0
        # Exactly: INVALID_PAYLOAD = 1 and INVALID_JSON is absent.
        assert summary["error_reasons"].get("backend_incident_invalid_payload") == 1
        assert "backend_incident_invalid_json" not in summary["error_reasons"]
        assert "incident_not_found" not in summary["skip_reasons"]

    def test_200_malformed_json_produces_failed_outcome(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        seeded_incident_store: object,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """HTTP 200 + malformed JSON -> ``Failed`` ->
        processed=1, errors=1, error_reasons=backend_incident_invalid_json.

        This is the canonical JSON decoding failure path: the body is
        not valid JSON, so the lookup function cannot reach the envelope
        validator and classifies the result as ``INVALID_JSON``.
        Kept separate from the valid-JSON-but-invalid-envelope case.
        """
        invalid_body = b"{not valid json"
        summary = self._run_production_path(
            body=invalid_body,
            http_status=200,
            monkeypatch=monkeypatch,
            temp_external_dir=temp_external_dir,
            enabled_auto_loop=enabled_auto_loop,
            incident_ids=["incident-r1-found"],
        )
        assert summary["incidents_processed"] == 1
        assert summary["incidents_with_errors"] == 1
        assert summary["incidents_skipped"] == 0
        # Exactly: INVALID_JSON = 1 and INVALID_PAYLOAD is absent.
        assert summary["error_reasons"].get("backend_incident_invalid_json") == 1
        assert "backend_incident_invalid_payload" not in summary["error_reasons"]
        assert "incident_not_found" not in summary["skip_reasons"]

    def test_404_response_produces_skipped_incident_not_found(
        self,
        temp_external_dir: Path,
        enabled_auto_loop: None,
        seeded_incident_store: object,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """HTTP 404 -> ``NotFound`` -> skipped / ``incident_not_found`` ->
        processed=1, skipped=1, error_reasons empty.
        """
        summary = self._run_production_path(
            body=b"",
            http_status=404,
            monkeypatch=monkeypatch,
            temp_external_dir=temp_external_dir,
            enabled_auto_loop=enabled_auto_loop,
            incident_ids=["incident-r1-not-found"],
        )
        assert summary["incidents_processed"] == 1
        assert summary["incidents_skipped"] == 1
        assert summary["incidents_with_errors"] == 0
        assert summary["skip_reasons"].get("incident_not_found") == 1
        assert "backend_incident_invalid_payload" not in summary["error_reasons"]
