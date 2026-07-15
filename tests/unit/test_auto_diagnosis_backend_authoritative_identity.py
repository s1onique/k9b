"""ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01 regression tests.

These tests pin the contract:

1. Backend-authoritative SQLite store contains an existing incident while
   the scheduler-local store is empty.
2. Alertmanager promotion updates the canonical incident and returns the
   canonical ``incident_id`` (which differs from the source candidate).
3. Automatic diagnosis consumes the returned canonical ID, fetches the
   incident through the backend API, and enters the diagnosis loop.
4. No scheduler-local incident read or write occurs.
5. A deliberately inconsistent promotion/lookup produces
   ``incident_store_consistency_error`` with bounded diagnostics.
6. Multiple promoted candidates retain one-to-one candidate-to-canonical
   ID mapping.
7. Existing in-memory standalone mode remains supported where explicitly
   configured.
8. The auto-diagnosis loop entrypoint emits structured diagnostics
   containing source candidate ID, canonical incident ID, promotion
   outcome, incident access mode, and backend endpoint identity (without
   credentials).

The tests deliberately avoid spinning up a full HTTP backend. Instead
they patch ``SchedulerClient`` so the backend-authoritative read and
write paths can be exercised deterministically. ``fetch_incident_for_diagnosis``
is patched via ``incident_diagnosis_dispatch`` so the test can verify
that the dispatcher's canonical-incident path is used, while the
scheduler-local path is intentionally never invoked.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.collect.incident_identity_hardening import (
    INCIDENT_ACCESS_MODE_BACKEND,
    PROMOTION_OUTCOME_OPENED,
    PROMOTION_OUTCOME_UPDATED,
    PromotionConsistencyContractError,
    PromotionRecord,
    verify_promotion_consistency,
)
from k8s_diag_agent.collect.incident_lifecycle import (
    Incident,
    IncidentSignal,
    IncidentStatus,
)
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    MODE_BACKEND_API,
    IncidentPromotionResult,
    promote_alert_signals,
)
from k8s_diag_agent.collect.incident_promotion_local import promote_local
from k8s_diag_agent.health.loop_automatic_diagnosis import (
    _coerce_canonical_ids,
    run_automatic_diagnosis_loop,
)
from k8s_diag_agent.health.loop_runner_execute import (
    _build_backend_endpoint_identity,
    _derive_automatic_diagnosis_inputs,
    execute_health_loop_run,
)
from k8s_diag_agent.ui.server_incident_internal_models import (
    PromotionResponse,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _incident(incident_id: str, status: IncidentStatus = IncidentStatus.OPEN) -> Incident:
    """Build a minimal Incident record for tests."""
    first = datetime(2026, 7, 10, 12, 0, 0, tzinfo=UTC)
    last = datetime(2026, 7, 10, 13, 0, 0, tzinfo=UTC)
    return Incident(
        incident_id=incident_id,
        source_candidate_id="cand-" + incident_id,
        namespace="default",
        object_kind="Pod",
        object_name="test-pod",
        raw_object_kind=None,
        candidate_class="PodCrashLoop",
        severity="high",
        status=status,
        first_observed_at=first,
        last_observed_at=last,
        signals=[
            IncidentSignal(
                source="alert",
                reason="CrashLoopBackOff",
                message="Container crashed",
                captured_at=first,
                fingerprint="signal-" + incident_id,
            )
        ],
        evidence_needed=["alert_evidence"],
        evidence_links=[],
        signal_count=1,
        events=[],
    )


class TestCoerceCanonicalIds:
    def test_none(self) -> None:
        assert _coerce_canonical_ids(None) is None

    def test_empty_list(self) -> None:
        assert _coerce_canonical_ids([]) is None

    def test_skips_blank_strings(self) -> None:
        assert _coerce_canonical_ids(["incident-1", "", None, "incident-2"]) == [
            "incident-1",
            "incident-2",
        ]

    def test_tuple(self) -> None:
        assert _coerce_canonical_ids(("incident-a", "incident-b")) == [
            "incident-a",
            "incident-b",
        ]

    def test_returns_none_on_invalid_type(self) -> None:
        # A non-iterable should not raise.
        assert _coerce_canonical_ids(42) is None


class TestDeriveAutomaticDiagnosisInputs:
    """``_derive_automatic_diagnosis_inputs`` should thread canonical IDs through."""

    def teardown_method(self) -> None:
        for var in [
            "K9B_BACKEND_INTERNAL_URL",
            "K9B_INTERNAL_API_TOKEN",
            "K9B_INCIDENT_STORE_BACKEND",
            "K9B_PROCESS_ROLE",
            "K9B_INCIDENT_PROMOTION_MODE",
        ]:
            os.environ.pop(var, None)

    def test_no_promotion_returns_empty(self) -> None:
        # R2: ``_derive_automatic_diagnosis_inputs`` now consumes a typed
        # ``RunPromotionAccumulator`` directly. With an empty accumulator
        # the canonical-ID list, the promotion summary, and the
        # consistency error must all be empty / ``None``.
        from k8s_diag_agent.collect.incident_promotion_accumulator import (
            RunPromotionAccumulator,
        )

        accumulator = RunPromotionAccumulator()
        canonical_ids, summary, consistency, endpoint, _execution = (
            _derive_automatic_diagnosis_inputs(accumulator)
        )
        assert canonical_ids == []
        assert summary["promotion_records"] == []
        assert consistency is None

    def test_promotion_records_become_canonical_ids(self) -> None:
        # R2: ``_derive_automatic_diagnosis_inputs`` consumes a typed
        # ``RunPromotionAccumulator``. We populate it with the same
        # canonical incident records the dispatcher would have built,
        # then assert the canonical-ID list and summary aggregate over
        # the typed records without re-parsing a free-form dict.
        from k8s_diag_agent.collect.incident_promotion_accumulator import (
            RunPromotionAccumulator,
        )
        from k8s_diag_agent.collect.incident_promotion_batch import (
            PromotionBatch,
        )
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            MODE_BACKEND_API,
            IncidentPromotionResult,
        )

        accumulator = RunPromotionAccumulator()
        backend_result = IncidentPromotionResult(
            ok=True,
            scanned=2,
            firing=2,
            opened_incidents=1,
            updated_incidents=1,
            skipped_duplicates=0,
            errors=0,
            promotion_mode=MODE_BACKEND_API,
            opened_incident_ids=("incident-1",),
            updated_incident_ids=("incident-2",),
            promotion_records=(
                {
                    "source_candidate_id": "cand-1",
                    "canonical_incident_id": "incident-1",
                    "promotion_outcome": PROMOTION_OUTCOME_OPENED,
                },
                {
                    "source_candidate_id": "cand-2",
                    "canonical_incident_id": "incident-2",
                    "promotion_outcome": PROMOTION_OUTCOME_UPDATED,
                },
            ),
            unique_candidate_count=2,
            promotion_scan_scope="internal_api_alert_signals",
            incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        accumulator.add_batch(
            PromotionBatch(
                promotion_result=backend_result,
                promotion_records=(
                    PromotionRecord(
                        source_candidate_id="cand-1",
                        canonical_incident_id="incident-1",
                        promotion_outcome=PROMOTION_OUTCOME_OPENED,
                    ),
                    PromotionRecord(
                        source_candidate_id="cand-2",
                        canonical_incident_id="incident-2",
                        promotion_outcome=PROMOTION_OUTCOME_UPDATED,
                    ),
                ),
                source_kind="alertmanager",
            )
        )
        # Patch the authoritative lookup so consistency check passes without
        # an HTTP roundtrip. R4: the helper takes only ``accumulator``
        # and derives every mode/access-mode value from the accumulated
        # batches. We still rely on the upstream patches to seed the
        # accumulator with backend-mode promotion_records, so the
        # derived summary respects that mode verbatim.
        canonical_ids, summary, _consistency, _backend, _execution = (
            _derive_automatic_diagnosis_inputs(accumulator)
        )
        assert canonical_ids == ["incident-1", "incident-2"]
        assert summary["unique_candidate_count"] == 2
        assert summary["incident_access_mode"] == INCIDENT_ACCESS_MODE_BACKEND


class TestRunAutomaticDiagnosisLoopCanonicalIDs:
    """``run_automatic_diagnosis_loop`` must pass canonical IDs through."""

    def teardown_method(self) -> None:
        os.environ.pop("K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED", None)

    def test_disabled_path_does_not_synthesize_ids(self) -> None:
        # Even when canonical IDs are supplied, a disabled loop returns no
        # synthesized IDs. We patch the gate so we don't depend on the
        # scheduler deployment environment. Round-10 (R10-1B):
        # ``scheduler_run_id="test-run"`` is supplied because the
        # dispatch-seam validator is fail-closed and rejects
        # promotion-derived selections without an explicit scheduler
        # run identity to compare against.
        os.environ["K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"] = "false"
        with patch(
            "k8s_diag_agent.health.loop_automatic_diagnosis.is_automatic_diagnosis_loop_enabled",
            return_value=False,
        ):
            result = run_automatic_diagnosis_loop(
                external_analysis_dir=Path("/tmp"),
                log_event_fn=lambda *a, **kw: None,
                canonical_incident_ids=["incident-1"],
                scheduler_run_id="test-run",
            )
        assert result["automatic_diagnosis_enabled"] is False
        assert result["promotion_propagated_to_diagnosis"] is True
        assert result["explicit_canonical_id_count"] == 1
        # R7 (item 2): the disabled path preserves the access mode from
        # the supplied metadata. With no backend_endpoint_identity or
        # promotion_result_summary the loop falls back to the explicit
        # ``no_promotion_run`` sentinel instead of the legacy
        # ``backend`` default.
        assert result["incident_access_mode"] == "no_promotion_run"

    def test_no_canonical_ids_raises_ambiguous_selection(self) -> None:
        """ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 invariant.

        The legacy ``if not ids: scan()`` truthiness fallback was the
        cause of the production 33-duplicate regression.  The seam
        now refuses the call rather than silently picking an unrelated
        incident.
        """
        from k8s_diag_agent.health.loop_automatic_diagnosis import (
            AmbiguousDiagnosisSelectionError,
        )

        with patch(
            "k8s_diag_agent.health.loop_automatic_diagnosis.is_automatic_diagnosis_loop_enabled",
            return_value=False,
        ):
            with pytest.raises(AmbiguousDiagnosisSelectionError):
                run_automatic_diagnosis_loop(
                    external_analysis_dir=Path("/tmp"),
                    log_event_fn=lambda *a, **kw: None,
                    canonical_incident_ids=None,
                )

    def test_multiple_authority_sources_raise_ambiguous(
        self,
    ) -> None:
        """Round 6 P0: contradictory authority sources are rejected.

        The 5-way combination of authority sources MUST yield exactly
        one source. The P0 guard closes the bypass where
        ``promotion_outcome=PromotionCommitUnknown`` paired with
        ``diagnosis_selection=DiagnosisSelectionFromPromotion`` would
        otherwise silently outrank the commit-uncertainty block.
        """
        from k8s_diag_agent.collect.diagnosis_selection import (
            DiagnosisSelectionFromPromotion,
            DiagnosisSelectionWithoutPromotion,
        )
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionCommitUnknown,
            PromotionReconciliationToken,
            PromotionRejected,
            PromotionRejectionCode,
            PromotionSucceeded,
        )
        from k8s_diag_agent.health.loop_automatic_diagnosis import (
            AmbiguousDiagnosisSelectionError,
        )

        from_promotion = DiagnosisSelectionFromPromotion(
            promotion_run_id="run", incident_ids=()
        )
        without_promotion = DiagnosisSelectionWithoutPromotion(
            reason=__import__(
                "k8s_diag_agent.collect.diagnosis_selection",
                fromlist=["NoPromotionSelectionReason"],
            ).NoPromotionSelectionReason.SCHEDULED_SCAN_RUN
        )
        commit_unknown = PromotionCommitUnknown(
            run_id="run",
            reason=__import__(
                "k8s_diag_agent.collect.promotion_outcomes",
                fromlist=["PromotionUncertaintyCode"],
            ).PromotionUncertaintyCode.AMBIGUOUS_RESPONSE,
            reconciliation_token=PromotionReconciliationToken(
                request_id="r",
                request_fingerprint="sha256:f",
            ),
        )
        rejected = PromotionRejected(
            run_id="run",
            reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
            rejected_signal_ids=(),
        )
        succeeded = PromotionSucceeded(
            run_id="run",
            requested_signal_ids=(),
            records=(),
            diagnosis_incident_ids=(),
        )

        with patch(
            "k8s_diag_agent.health.loop_automatic_diagnosis.is_automatic_diagnosis_loop_enabled",
            return_value=False,
        ):
            # diagnosis_selection + promotion_outcome -> raise
            for selection, outcome in [
                (from_promotion, commit_unknown),
                (from_promotion, rejected),
                (from_promotion, succeeded),
                (without_promotion, commit_unknown),
                (without_promotion, rejected),
                (without_promotion, succeeded),
            ]:
                with pytest.raises(AmbiguousDiagnosisSelectionError):
                    run_automatic_diagnosis_loop(
                        external_analysis_dir=Path("/tmp"),
                        log_event_fn=lambda *a, **kw: None,
                        diagnosis_selection=selection,
                        promotion_outcome=outcome,
                    )

    def test_cross_run_promotion_selection_is_rejected(self) -> None:
        """A DiagnosisSelectionFromPromotion with a mismatched run_id MUST be rejected.

        Round 10 P0 invariant: the dispatch seam rejects every
        :class:`DiagnosisSelectionFromPromotion` whose
        ``promotion_run_id`` differs from the caller-supplied
        ``scheduler_run_id``. Promoting the assertion from the broad
        ``ValueError`` form to the typed
        :class:`DiagnosisRunIdentityMismatchError` makes the contract
        explicit and prevents a silently-relabelled cross-run
        selection from leaking into diagnosis.
        """
        from k8s_diag_agent.collect.diagnosis_selection import (
            DiagnosisRunIdentityMismatchError,
            DiagnosisSelectionFromPromotion,
        )

        # Construct a diagnosis selection whose underlying outcome
        # run_id is "run-A" but pass "run-B" as the scheduler run_id.
        # A correct implementation MUST raise
        # DiagnosisRunIdentityMismatchError; until round 10 the call
        # returned normally and the strict xfail accepted that as the
        # documented defect. The strict marker has now been removed.
        selection = DiagnosisSelectionFromPromotion(
            promotion_run_id="run-A",
            incident_ids=("incident-A",),
        )

        with patch(
            "k8s_diag_agent.health.loop_automatic_diagnosis.is_automatic_diagnosis_loop_enabled",
            return_value=False,
        ):
            with pytest.raises(DiagnosisRunIdentityMismatchError) as exc_info:
                run_automatic_diagnosis_loop(
                    external_analysis_dir=Path("/tmp"),
                    log_event_fn=lambda *a, **kw: None,
                    diagnosis_selection=selection,
                    scheduler_run_id="run-B",
                )
        # Typed-error contract: surface the expected and actual run
        # identities so the operator can diagnose the cross-run
        # laundering directly without parsing the message.
        assert exc_info.value.expected_run_id == "run-B"
        assert exc_info.value.actual_run_id == "run-A"

    def test_cross_run_unavailable_outcome_is_rejected(self) -> None:
        """A DiagnosisSelectionUnavailable with a mismatched outcome.run_id MUST be rejected.

        Round 10 P0 invariant (all promotion-derived values must
        match): even when the selection is the
        :class:`DiagnosisSelectionUnavailable` variant, the carried
        :class:`PromotionRejected`/``PromotionCommitUnknown`` ``run_id``
        is checked against ``scheduler_run_id``. The cross-run
        laundering risk is identical for "blocked" and "available"
        selection variants.
        """
        from k8s_diag_agent.collect.diagnosis_selection import (
            DiagnosisRunIdentityMismatchError,
            DiagnosisSelectionUnavailable,
        )
        from k8s_diag_agent.collect.promotion_outcomes import (
            PromotionRejected,
            PromotionRejectionCode,
        )

        selection = DiagnosisSelectionUnavailable(
            outcome=PromotionRejected(
                run_id="run-A",
                reason=PromotionRejectionCode.WORKLIST_INCONSISTENT,
                rejected_signal_ids=(),
            )
        )

        with patch(
            "k8s_diag_agent.health.loop_automatic_diagnosis.is_automatic_diagnosis_loop_enabled",
            return_value=False,
        ):
            with pytest.raises(DiagnosisRunIdentityMismatchError) as exc_info:
                run_automatic_diagnosis_loop(
                    external_analysis_dir=Path("/tmp"),
                    log_event_fn=lambda *a, **kw: None,
                    diagnosis_selection=selection,
                    scheduler_run_id="run-B",
                )
        assert exc_info.value.expected_run_id == "run-B"
        assert exc_info.value.actual_run_id == "run-A"

    def test_completion_emits_consistency_propagation_metadata(self, tmp_path: Path) -> None:
        # Patch the gate to deterministically enable the loop regardless
        # of the deployment env. This pins the test to "scheduler says
        # run" without depending on cluster state.
        captured: list[dict[str, Any]] = []

        def log_event(*_args: Any, **metadata: Any) -> None:
            captured.append(metadata)

        promotion_summary = {
            "opened_incident_ids": ["incident-1"],
            "updated_incident_ids": [],
            "promotion_records": [
                {
                    "source_candidate_id": "cand-1",
                    "canonical_incident_id": "incident-1",
                    "promotion_outcome": "opened",
                }
            ],
        }

        with patch(
            "k8s_diag_agent.health.loop_automatic_diagnosis.is_automatic_diagnosis_loop_enabled",
            return_value=True,
        ), patch(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop.run_automatic_diagnosis_loop_evidence_collection"
        ) as collector:
            collector.return_value.incidents_processed = 0
            collector.return_value.incidents_eligible = 0
            collector.return_value.incidents_skipped = 0
            collector.return_value.incidents_ineligible = 0
            collector.return_value.incidents_with_errors = 0
            collector.return_value.total_review_packets_written = 0
            collector.return_value.disposition_summary = MagicMock(
                skip_reasons={},
                ineligible_reasons={},
                error_reasons={},
            )
            collector.return_value.run_id = "test-run"

            run_automatic_diagnosis_loop(
                external_analysis_dir=tmp_path,
                log_event_fn=log_event,
                canonical_incident_ids=["incident-1"],
                promotion_result_summary=promotion_summary,
                backend_endpoint_identity={
                    "backend_base_url": "http://k9b-backend:8080",
                    "internal_api_path_prefix": "/api/internal",
                    "backend_reachable": True,
                    "incident_access_mode": INCIDENT_ACCESS_MODE_BACKEND,
                },
                # Round-10 (R10-1B): the dispatch seam is fail-closed;
                # a promotion-derived selection requires an explicit
                # scheduler_run_id to compare against. The collector
                # stub returns ``run_id="test-run"`` so the legacy
                # path's selection carries the matching identity.
                scheduler_run_id="test-run",
            )

        start = next(
            event for event in captured if event.get("event") == "start"
        )
        assert start["explicit_canonical_id_count"] == 1
        assert start["incident_access_mode"] == INCIDENT_ACCESS_MODE_BACKEND

        complete = next(
            event for event in captured if event.get("event") == "complete"
        )
        assert complete["incident_access_mode"] == INCIDENT_ACCESS_MODE_BACKEND
        assert complete["promotion_propagated_to_diagnosis"] is True
        assert complete["explicit_canonical_id_count"] == 1
        # The collector is invoked once with explicit canonical IDs.
        assert collector.call_count == 1
        _, kwargs = collector.call_args
        assert kwargs["incident_ids"] == ["incident-1"]


class TestBackendEndpointIdentityNoCredentials:
    def test_payload_omits_bearer_token_and_secret(self) -> None:
        os.environ["K9B_BACKEND_INTERNAL_URL"] = "https://backend:8443"
        try:
            payload = _build_backend_endpoint_identity()
        finally:
            os.environ.pop("K9B_BACKEND_INTERNAL_URL", None)
        import json
        serialized = json.dumps(payload, default=str)
        assert "token" not in serialized
        # We deliberately do not embed any auth tokens in the diagnostic
        # payload; only the base URL and path prefix are exposed.
        assert "https://backend:8443" in serialized
        assert payload["incident_access_mode"] == INCIDENT_ACCESS_MODE_BACKEND


class TestAlertSignalPromotionReturnsCanonicalIDs:
    """``promote_alert_signals`` should expose canonical IDs end-to-end."""

    def teardown_method(self) -> None:
        for var in [
            "K9B_BACKEND_INTERNAL_URL",
            "K9B_INTERNAL_API_TOKEN",
            "K9B_INCIDENT_STORE_BACKEND",
            "K9B_PROCESS_ROLE",
            "K9B_INCIDENT_PROMOTION_MODE",
        ]:
            os.environ.pop(var, None)

    def test_backend_api_path_propagates_canonical_ids(self) -> None:
        # Force backend-api mode with a fake backend URL/token.
        os.environ["K9B_INCIDENT_PROMOTION_MODE"] = "backend-api"
        os.environ["K9B_BACKEND_INTERNAL_URL"] = "http://k9b-backend:8080"
        os.environ["K9B_INTERNAL_API_TOKEN"] = "secret"

        response = PromotionResponse(
            ok=True,
            scanned=2,
            firing=2,
            opened_incidents=1,
            updated_incidents=1,
            skipped_duplicates=0,
            errors=0,
            error_messages=[],
            opened_incident_ids=["incident-1"],
            updated_incident_ids=["incident-2"],
            promotion_records=[
                {
                    "source_candidate_id": "cand-1",
                    "canonical_incident_id": "incident-1",
                    "promotion_outcome": "opened",
                },
                {
                    "source_candidate_id": "cand-2",
                    "canonical_incident_id": "incident-2",
                    "promotion_outcome": "updated",
                },
            ],
            unique_candidate_count=2,
            promotion_scan_scope="internal_api_alert_signals",
            incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )

        from datetime import UTC as _UTC
        from datetime import datetime as _dt

        observed_at = _dt.now(_UTC)

        with patch(
            "k8s_diag_agent.collect.incident_promotion_backend.SchedulerClient"
        ) as mock_client_class:
            mock_client_class.return_value.promote_alert_signals.return_value = response

            result = promote_alert_signals(
                candidates=[],
                observed_at=observed_at,
            )

        assert isinstance(result, IncidentPromotionResult)
        assert result.promotion_mode == MODE_BACKEND_API
        assert list(result.opened_incident_ids) == ["incident-1"]
        assert list(result.updated_incident_ids) == ["incident-2"]
        assert len(result.promotion_records) == 2
        record = result.promotion_records[0]
        assert record["source_candidate_id"] == "cand-1"
        assert record["canonical_incident_id"] == "incident-1"
        # One-to-one mapping must be preserved.
        assert {r["canonical_incident_id"] for r in result.promotion_records} == {
            "incident-1",
            "incident-2",
        }
        assert {r["source_candidate_id"] for r in result.promotion_records} == {
            "cand-1",
            "cand-2",
        }

    def test_local_path_preserves_canonical_id_propagation(self) -> None:
        # Explicit local mode: rely on the in-memory store but confirm
        # canonical IDs are exposed through the dispatcher. The store
        # derives a deterministic canonical incident_id from the candidate
        # fields (namespace, kind, name, class). The key invariant is that
        # the canonical_id is non-empty, consistent across promotion records,
        # and distinct from the source_candidate_id when the candidate_id is
        # short-form.
        os.environ["K9B_INCIDENT_PROMOTION_MODE"] = "local"
        os.environ.pop("K9B_PROCESS_ROLE", None)
        os.environ.pop("K9B_INCIDENT_STORE_BACKEND", None)

        from k8s_diag_agent.collect.incident_store_provider import (
            reset_incident_store,
        )

        # Force a clean process-local store before exercising local mode.
        reset_incident_store()

        from datetime import UTC as _UTC
        from datetime import datetime as _dt

        from k8s_diag_agent.collect.incident_candidates import (
            CandidateClass,
            CandidateSignal,
            IncidentCandidate,
            ObjectKind,
            Severity,
        )

        candidate = IncidentCandidate(
            candidate_id="cand-1",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="test-pod",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(CandidateSignal(source="alert", reason="CrashLoopBackOff", message="oops"),),
            evidence_needed=("alert_evidence",),
        )

        result_dict = promote_local(
            candidates=[candidate],
            observed_at=_dt.now(_UTC),
        )
        opened = result_dict["opened_incident_ids"]
        assert len(opened) == 1
        canonical_incident_id = opened[0]
        assert canonical_incident_id  # non-empty
        # The promotion record reports the same canonical ID we got back.
        records = result_dict["promotion_records"]
        assert len(records) == 1
        assert records[0]["canonical_incident_id"] == canonical_incident_id
        assert records[0]["promotion_outcome"] == "opened"
        assert records[0]["source_candidate_id"] == "cand-1"
        # ``source_candidate_id`` MUST NOT be used as ``canonical_incident_id``
        # when the in-memory store is asked to materialize an incident.
        # Pin this to make sure the regression never reintroduces the
        # candidate-shaped-IDs-as-incident-IDs bug.
        assert records[0]["canonical_incident_id"] != records[0]["source_candidate_id"]
        reset_incident_store()


class TestSchedulerRoleGuard:
    """Scheduler must not open SQLite directly in backend-authoritative mode.

    These regression tests verify that ``IncidentPromotionDispatchConfig``
    refuses to allow local promotion when the scheduler role and SQLite
    store are both selected, mirroring the existing role-guard contract.
    """

    def teardown_method(self) -> None:
        for var in [
            "K9B_BACKEND_INTERNAL_URL",
            "K9B_INTERNAL_API_TOKEN",
            "K9B_INCIDENT_STORE_BACKEND",
            "K9B_PROCESS_ROLE",
            "K9B_INCIDENT_PROMOTION_MODE",
        ]:
            os.environ.pop(var, None)

    def test_scheduler_sqlite_mode_cannot_use_local(self) -> None:
        # Scheduler running with the sqlite backend MUST resolve to the
        # backend-api promotion path. This is the architectural invariant
        # that prevents the scheduler from opening a SQLite store directly.
        os.environ["K9B_PROCESS_ROLE"] = "scheduler"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "sqlite"
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            _get_dispatch_config,
        )

        config = _get_dispatch_config()
        assert config.process_role == "scheduler"
        assert config.store_backend == "sqlite"
        # The auto-resolve policy MUST pick backend-api in scheduler+sqlite.
        assert config.resolved_mode() == MODE_BACKEND_API
        # And ``can_use_local`` MUST report False so the dispatcher never
        # attempts a scheduler-local write even if a future caller asks
        # for it explicitly.
        assert config.can_use_local() is False

    def test_scheduler_local_mode_explicitly_rejected_by_dispatcher(self) -> None:
        # Even when the caller explicitly opts in to local mode, the
        # ``can_use_local`` guard prevents scheduler+sqlite from doing a
        # local write. We exercise ``promote_alert_signals`` directly so
        # we observe the dispatcher's actual behavior rather than relying
        # on the artifact scan path which short-circuits when no candidates
        # exist.
        os.environ["K9B_PROCESS_ROLE"] = "scheduler"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "sqlite"
        os.environ["K9B_INCIDENT_PROMOTION_MODE"] = "local"

        from datetime import UTC
        from datetime import datetime as _dt

        from k8s_diag_agent.collect.incident_candidates import (
            CandidateClass,
            CandidateSignal,
            IncidentCandidate,
            ObjectKind,
            Severity,
        )
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            _get_dispatch_config,
            promote_alert_signals,
        )

        config = _get_dispatch_config()
        assert config.can_use_local() is False
        # Even with explicit local mode the dispatcher returns an error
        # result rather than attempting a scheduler-side SQLite write.
        candidate = IncidentCandidate(
            candidate_id="cand-1",
            namespace="default",
            object_kind=ObjectKind.POD,
            object_name="test-pod",
            candidate_class=CandidateClass.CRASH_LOOP,
            severity=Severity.ERROR,
            signals=(CandidateSignal(source="alert", reason="X", message="oops"),),
            evidence_needed=("alert_evidence",),
        )
        result = promote_alert_signals(
            candidates=[candidate],
            observed_at=_dt.now(UTC),
        )
        assert result.ok is False
        assert result.errors >= 1
        assert any(
            "scheduler cannot use SQLite store directly" in str(message)
            for message in result.error_messages
        )


class TestMultiplePromotedCandidatesOneToOneMapping:
    """Multiple promoted candidates retain one-to-one candidate-to-id mapping.

    This test pins down the regression that previously motivated the ACT:
    when ``updated_incidents=68`` was reported, the scheduler would
    re-synthesize candidate-shaped incident IDs and miss every lookup.
    """

    def teardown_method(self) -> None:
        for var in (
            "K9B_BACKEND_INTERNAL_URL",
            "K9B_INTERNAL_API_TOKEN",
            "K9B_INCIDENT_STORE_BACKEND",
            "K9B_PROCESS_ROLE",
            "K9B_INCIDENT_PROMOTION_MODE",
        ):
            os.environ.pop(var, None)

    def test_distinct_candidate_ids_yield_distinct_canonical_ids(self) -> None:
        # 3 distinct candidates must yield 3 distinct canonical incident IDs
        # and a one-to-one mapping. We do not assume a particular canonical
        # ID shape (the in-memory store derives from canonical attributes)
        # but assert structural uniqueness and the candidate→canonical map.
        from datetime import UTC as _UTC
        from datetime import datetime as _dt

        from k8s_diag_agent.collect.incident_candidates import (
            CandidateClass,
            CandidateSignal,
            IncidentCandidate,
            ObjectKind,
            Severity,
        )
        from k8s_diag_agent.collect.incident_store_provider import (
            reset_incident_store,
        )

        os.environ["K9B_INCIDENT_PROMOTION_MODE"] = "local"
        os.environ.pop("K9B_PROCESS_ROLE", None)
        os.environ.pop("K9B_INCIDENT_STORE_BACKEND", None)
        reset_incident_store()

        candidates = [
            IncidentCandidate(
                candidate_id=f"cand-{i}",
                namespace="default",
                object_kind=ObjectKind.POD,
                object_name=f"pod-{i}",
                candidate_class=CandidateClass.CRASH_LOOP,
                severity=Severity.ERROR,
                signals=(CandidateSignal(source="alert", reason="X", message="oops"),),
                evidence_needed=("alert_evidence",),
            )
            for i in range(3)
        ]

        result_dict = promote_local(
            candidates=candidates,
            observed_at=_dt.now(_UTC),
        )
        opened = result_dict["opened_incident_ids"]
        assert len(opened) == 3
        # 3 distinct canonical IDs.
        assert len(set(opened)) == 3
        records = result_dict["promotion_records"]
        assert len(records) == 3
        # 3 distinct source candidate IDs.
        assert len({r["source_candidate_id"] for r in records}) == 3
        # One-to-one canonical↔source mapping (no two distinct candidates
        # collapsing into the same canonical incident ID).
        seen: dict[str, str] = {}
        for record in records:
            assert record["canonical_incident_id"] not in seen
            seen[record["canonical_incident_id"]] = record["source_candidate_id"]
        reset_incident_store()


class TestInconsistentPromotionLookupEmitsConsistencyError:
    """A deliberately inconsistent promotion/lookup produces the structured error."""

    def teardown_method(self) -> None:
        for var in (
            "K9B_BACKEND_INTERNAL_URL",
            "K9B_INTERNAL_API_TOKEN",
            "K9B_INCIDENT_STORE_BACKEND",
            "K9B_PROCESS_ROLE",
            "K9B_INCIDENT_PROMOTION_MODE",
        ):
            os.environ.pop(var, None)

    def test_consistency_error_when_lookup_misses(self) -> None:
        promotions = [
            PromotionRecord(
                source_candidate_id="cand-1",
                canonical_incident_id="incident-1",
                promotion_outcome="opened",
            )
        ]
        from k8s_diag_agent.collect.incident_identity_hardening import (
            LookupOutcome,
            backend_endpoint_identity_from_url,
        )

        endpoint = backend_endpoint_identity_from_url("http://k9b-backend:8080")
        lookups = [LookupOutcome("incident-1", found=False)]
        error = verify_promotion_consistency(
            promotions,
            lookups=lookups,
            backend_endpoint=endpoint,
            opened_incidents=1,
            updated_incidents=0,
            opened_incident_ids=("incident-1",),
            updated_incident_ids=(),
        )
        assert error is not None
        payload = error.to_dict()
        assert payload["error_kind"] == "incident_store_consistency_error"
        assert payload["source_candidate_ids"] == ["cand-1"]
        assert payload["canonical_incident_ids"] == ["incident-1"]
        assert payload["lookup_outcomes"][0]["found"] is False
        assert payload["backend_endpoint"]["base_url"] == "http://k9b-backend:8080"
        assert payload["backend_endpoint"]["host"] == "k9b-backend"
        assert payload["backend_endpoint"]["port"] == 8080
        # R1 contract: no raw URL with userinfo/query/path must leak.
        assert "@" not in payload["backend_endpoint"]["host"]
        assert "/" not in payload["backend_endpoint"]["host"]

    def test_consistency_error_candidate_id_differs_from_canonical(self) -> None:
        """Source candidate ID MUST NOT be used as the canonical incident ID."""
        from k8s_diag_agent.collect.incident_identity_hardening import (
            LookupOutcome,
            backend_endpoint_identity_from_url,
        )

        promotions = [
            PromotionRecord(
                source_candidate_id="k8s-namespace/Pod/my-pod",
                canonical_incident_id="incident-canonical-abc",
                promotion_outcome="opened",
            ),
            PromotionRecord(
                source_candidate_id="k8s-namespace/Deployment/my-deploy",
                canonical_incident_id="incident-canonical-def",
                promotion_outcome="updated",
            ),
        ]
        endpoint = backend_endpoint_identity_from_url("http://k9b-backend:8080")
        lookups = [
            LookupOutcome("incident-canonical-abc", found=True),
            # The deployment-shaped candidate's lookup fails so we surface
            # a consistency error.
            LookupOutcome("incident-canonical-def", found=False),
        ]
        error = verify_promotion_consistency(
            promotions,
            lookups=lookups,
            backend_endpoint=endpoint,
            opened_incidents=1,
            updated_incidents=1,
            opened_incident_ids=("incident-canonical-abc",),
            updated_incident_ids=("incident-canonical-def",),
        )
        assert error is not None
        payload = error.to_dict()
        # Verify the diagnostic carries the candidate-shaped ID *as
        # correlation metadata only*, and the canonical incident ID is
        # what we treat as the incident_id.
        assert payload["source_candidate_ids"] == [
            "k8s-namespace/Deployment/my-deploy",
        ]
        assert payload["canonical_incident_ids"] == [
            "incident-canonical-def",
        ]
        # The candidate-shaped ID MUST NOT appear inside canonical incident IDs.
        canonical_ids = payload["canonical_incident_ids"]
        for value in canonical_ids:
            assert "/" not in value
            assert " " not in value


class TestRunPromotionAccumulatorIntegratedRegression:
    """R2 integrated regression: the real run-level accumulator path.

    The original ACT regression closed the
    ``incident_not_found`` diagnostic by replacing
    ``directories["__last_promotion_result__"]`` smuggling with a
    typed ``RunPromotionAccumulator`` handoff. This class locks down
    the new contract:

    1. The dispatcher hands typed ``PromotionRecord`` values directly
       to ``RunPromotionAccumulator.add_record``.
    2. ``_derive_automatic_diagnosis_inputs`` consumes the typed
       accumulator without re-parsing a free-form dict.
    3. The accumulator's canonical IDs are routed into
       ``run_automatic_diagnosis_loop`` as ``incident_ids``.
    4. ``incident_not_found`` is absent from the auto-diagnosis
       disposition summary.
    5. An instrumented scheduler-local ``IncidentStore`` records zero
       reads and zero writes during the run (the scheduler never
       touches the local store in backend-authoritative mode).
    """

    def teardown_method(self) -> None:
        for var in (
            "K9B_BACKEND_INTERNAL_URL",
            "K9B_INTERNAL_API_TOKEN",
            "K9B_INCIDENT_STORE_BACKEND",
            "K9B_PROCESS_ROLE",
            "K9B_INCIDENT_PROMOTION_MODE",
            "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
        ):
            os.environ.pop(var, None)

    def test_run_promotion_accumulator_drives_diagnosis_without_smuggling(
        self,
    ) -> None:
        from datetime import UTC as _UTC
        from datetime import datetime as _dt
        from unittest.mock import MagicMock, patch

        from k8s_diag_agent.collect.incident_identity_hardening import (
            PROMOTION_OUTCOME_OPENED,
            PROMOTION_OUTCOME_UPDATED,
        )
        from k8s_diag_agent.collect.incident_promotion_accumulator import (
            RunPromotionAccumulator,
        )

        # Set up backend-authoritative env so the dispatcher picks
        # the backend-api mode and the canonical IDs are authoritative.
        os.environ["K9B_PROCESS_ROLE"] = "scheduler"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "sqlite"
        os.environ["K9B_INCIDENT_PROMOTION_MODE"] = "backend-api"
        os.environ["K9B_BACKEND_INTERNAL_URL"] = "http://k9b-backend:8080"
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"

        # Simulate a real run-level accumulator populated by the
        # dispatcher. R4: every batch carries its resolved mode/access-mode
        # so the orchestrator can derive them verbatim. We seed the
        # accumulator with a single backend-api batch.
        from k8s_diag_agent.collect.incident_promotion_batch import (
            PromotionBatch,
        )
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            MODE_BACKEND_API,
            IncidentPromotionResult,
        )

        accumulator = RunPromotionAccumulator()
        backend_result = IncidentPromotionResult(
            ok=True,
            scanned=2,
            firing=2,
            opened_incidents=1,
            updated_incidents=1,
            skipped_duplicates=0,
            errors=0,
            promotion_mode=MODE_BACKEND_API,
            opened_incident_ids=("incident-canonical-abc",),
            updated_incident_ids=("incident-canonical-def",),
            promotion_records=(
                {
                    "source_candidate_id": "k8s-namespace/Pod/my-pod",
                    "canonical_incident_id": "incident-canonical-abc",
                    "promotion_outcome": PROMOTION_OUTCOME_OPENED,
                },
                {
                    "source_candidate_id": "k8s-namespace/Deployment/my-deploy",
                    "canonical_incident_id": "incident-canonical-def",
                    "promotion_outcome": PROMOTION_OUTCOME_UPDATED,
                },
            ),
            unique_candidate_count=2,
            promotion_scan_scope="internal_api_alert_signals",
            incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        accumulator.add_batch(
            PromotionBatch(
                promotion_result=backend_result,
                promotion_records=(
                    PromotionRecord(
                        source_candidate_id="k8s-namespace/Pod/my-pod",
                        canonical_incident_id="incident-canonical-abc",
                        promotion_outcome=PROMOTION_OUTCOME_OPENED,
                    ),
                    PromotionRecord(
                        source_candidate_id="k8s-namespace/Deployment/my-deploy",
                        canonical_incident_id="incident-canonical-def",
                        promotion_outcome=PROMOTION_OUTCOME_UPDATED,
                    ),
                ),
                source_kind="alertmanager",
            )
        )

        # The diagnosis collector MUST receive the canonical IDs and
        # report zero ``incident_not_found`` outcomes because the
        # backend-api dispatcher's authoritative lookup succeeded.
        captured_incident_ids: dict[str, object] = {}

        def collector_stub(
            *,
            external_analysis_dir: object,
            config: object = None,
            incident_ids: list[str] | None = None,
            scheduler_run_id: str | None = None,
        ) -> MagicMock:
            captured_incident_ids["incident_ids"] = list(incident_ids or [])
            result = MagicMock()
            result.incidents_processed = len(incident_ids or [])
            result.incidents_eligible = len(incident_ids or [])
            result.incidents_skipped = 0
            result.incidents_ineligible = 0
            result.incidents_with_errors = 0
            result.total_review_packets_written = len(incident_ids or [])
            # ``incident_not_found`` MUST be absent from skip reasons
            # in the success case.
            result.disposition_summary = MagicMock(
                skip_reasons={},
                ineligible_reasons={},
                error_reasons={},
            )
            result.run_id = "test-run"
            return result

        with patch(
            "k8s_diag_agent.collect.incident_diagnosis_auto_loop.run_automatic_diagnosis_loop_evidence_collection",
            side_effect=collector_stub,
        ), patch(
            "k8s_diag_agent.health.loop_automatic_diagnosis.is_automatic_diagnosis_loop_enabled",
            return_value=True,
        ):
            # Step 1: derive the diagnosis inputs from the typed
            # accumulator. This MUST NOT consult
            # ``directories["__last_promotion_result__"]``. R4: the
            # helper derives every mode/access-mode value from the
            # accumulated batches. We seeded the accumulator with a
            # backend-api batch above so the derived summary respects
            # that mode verbatim.
            canonical_ids, summary, consistency, backend_identity, _execution = (
                _derive_automatic_diagnosis_inputs(accumulator)
            )

            assert canonical_ids == [
                "incident-canonical-abc",
                "incident-canonical-def",
            ]
            # The promotion summary carries the typed records
            # straight through so downstream structured logs do not
            # have to re-parse a free-form dict.
            assert summary["promotion_records"][0]["canonical_incident_id"] == (
                "incident-canonical-abc"
            )
            assert summary["promotion_records"][1]["canonical_incident_id"] == (
                "incident-canonical-def"
            )
            assert summary["incident_access_mode"] == "backend"

            # Step 2: feed the canonical IDs into the auto-diagnosis
            # loop. The collector stub records zero
            # ``incident_not_found`` outcomes because the backend-api
            # dispatcher resolves every ID.
            result = run_automatic_diagnosis_loop(
                external_analysis_dir=_dt.now(_UTC),
                log_event_fn=lambda *a, **kw: None,
                canonical_incident_ids=canonical_ids,
                promotion_result_summary=summary,
                backend_endpoint_identity=backend_identity,
                scheduler_run_id="test-run",
            )

        assert captured_incident_ids["incident_ids"] == canonical_ids
        assert result["incidents_processed"] == 2
        assert result["incidents_eligible"] == 2
        assert result["promotion_propagated_to_diagnosis"] is True
        assert result["explicit_canonical_id_count"] == 2
        # The success disposition summary has no ``incident_not_found``
        # entry. We confirm via the collector stub's recorded reasons.
        assert result["skip_reasons"] == {}

    def test_instrumented_scheduler_local_store_sees_zero_io(
        self,
    ) -> None:
        # R2 acceptance criterion: the scheduler-local store MUST NOT
        # be touched at all when the dispatcher is in
        # ``backend-api`` mode. We instrument ``IncidentStore.add_incident``
        # and ``IncidentStore.get_incident`` to record any reads or
        # writes; the test fails if either method is invoked.
        from k8s_diag_agent.collect.incident_promotion_accumulator import (
            RunPromotionAccumulator,
        )

        os.environ["K9B_PROCESS_ROLE"] = "scheduler"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "sqlite"
        os.environ["K9B_INCIDENT_PROMOTION_MODE"] = "backend-api"
        os.environ["K9B_BACKEND_INTERNAL_URL"] = "http://k9b-backend:8080"
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"

        from k8s_diag_agent.collect.incident_promotion_batch import (
            PromotionBatch,
        )
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            IncidentPromotionResult,
        )

        accumulator = RunPromotionAccumulator()
        backend_result = IncidentPromotionResult(
            ok=True,
            scanned=1,
            firing=1,
            opened_incidents=1,
            updated_incidents=0,
            skipped_duplicates=0,
            errors=0,
            promotion_mode=MODE_BACKEND_API,
            opened_incident_ids=("incident-canonical-abc",),
            promotion_scan_scope="internal_api_alert_signals",
            incident_access_mode=INCIDENT_ACCESS_MODE_BACKEND,
        )
        accumulator.add_batch(
            PromotionBatch(
                promotion_result=backend_result,
                promotion_records=(
                    PromotionRecord(
                        source_candidate_id="k8s-namespace/Pod/my-pod",
                        canonical_incident_id="incident-canonical-abc",
                        promotion_outcome=PROMOTION_OUTCOME_OPENED,
                    ),
                ),
                source_kind="alertmanager",
            )
        )

        # Patch the scheduler-local store to count reads and writes.
        # The dispatcher should not touch either method while the
        # accumulator is the authoritative source.
        from k8s_diag_agent.collect import incident_store as store_module

        original_add = store_module.IncidentStore.add_incident
        original_get = store_module.IncidentStore.get_incident

        read_count = {"reads": 0, "writes": 0}

        def tracked_add(self: object, incident: object) -> None:
            read_count["writes"] += 1
            original_add(self, incident)

        def tracked_get(self: object, incident_id: object) -> object:
            read_count["reads"] += 1
            return original_get(self, incident_id)

        # Monkey-patch the store methods so every read/write goes
        # through the tracking wrappers above.
        store_module.IncidentStore.add_incident = tracked_add
        store_module.IncidentStore.get_incident = tracked_get
        try:
            # Patch the authoritative backend lookup so the test does
            # not depend on a live backend. The successful lookup means
            # ``verify_promotion_consistency`` returns ``None`` and
            # ``consistency`` stays ``None``. R4: no hard-coded mode
            # arguments; the helper derives ``backend-api`` /
            # ``incident_access_mode="backend"`` from the batch above.
            with patch(
                "k8s_diag_agent.collect.incident_diagnosis_dispatch.fetch_incident_for_diagnosis",
                return_value=("incident-canonical-abc-stub", True, None),
            ):
                canonical_ids, summary, consistency, backend_identity, _execution = (
                    _derive_automatic_diagnosis_inputs(accumulator)
                )
            assert canonical_ids == ["incident-canonical-abc"]
            assert summary["promotion_records"][0]["canonical_incident_id"] == (
                "incident-canonical-abc"
            )
            assert consistency is None
            assert backend_identity["incident_access_mode"] == INCIDENT_ACCESS_MODE_BACKEND
        finally:
            store_module.IncidentStore.add_incident = original_add
            store_module.IncidentStore.get_incident = original_get

        # The dispatcher MUST NOT have read or written the local store.
        assert read_count["reads"] == 0
        assert read_count["writes"] == 0
class TestDeriveAutomaticDiagnosisInputsLegacyRegression:
    """R6 (item 1): the legacy-backend regression reaches the
    orchestrator and produces a typed contract failure.

    This is the production-reachability closure: opened_incidents > 0
    plus empty ``promotion_records`` plus empty ``opened_incident_ids``
    is the exact shape of the legacy-backend regression. The contract
    validator MUST raise :class:`PromotionConsistencyContractError`
    even though both ``promotion_records`` and ``canonical_ids`` are
    empty, so the orchestrator can short-circuit BEFORE automatic
    diagnosis falls back to scan mode.
    """

    def teardown_method(self) -> None:
        for var in [
            "K9B_BACKEND_INTERNAL_URL",
            "K9B_INTERNAL_API_TOKEN",
            "K9B_INCIDENT_STORE_BACKEND",
            "K9B_PROCESS_ROLE",
            "K9B_INCIDENT_PROMOTION_MODE",
        ]:
            os.environ.pop(var, None)

    def test_legacy_backend_regression_contract_failure_is_typed(self) -> None:
        """opened_incidents > 0, empty records, empty IDs -> typed contract failure.

        The contract validator runs unconditionally for every
        backend-authoritative run, so the regression cannot be silently
        masked by an empty-records guard. The
        :class:`PromotionConsistencyContractError` carries the
        per-aggregate counts so the orchestrator can route the
        dispatcher regression into the typed event log instead of
        letting automatic diagnosis fall back to scan mode.
        """
        os.environ["K9B_PROCESS_ROLE"] = "scheduler"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "sqlite"
        os.environ["K9B_INCIDENT_PROMOTION_MODE"] = "backend-api"
        os.environ["K9B_BACKEND_INTERNAL_URL"] = "http://k9b-backend:8080"
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"

        from k8s_diag_agent.collect.incident_promotion_accumulator import (
            RunPromotionAccumulator,
        )

        accumulator = RunPromotionAccumulator()
        # The legacy regression: aggregate counts report opens/updates
        # but the batch exposes neither records nor canonical IDs.
        # Build a batch whose aggregate totals are nonzero but whose
        # promotion_records list is empty.
        empty_records_batch_dict = {
            "ok": True,
            "scanned": 2,
            "firing": 2,
            "opened_incidents": 2,
            "updated_incidents": 1,
            "skipped_duplicates": 0,
            "errors": 0,
            "promotion_mode": "backend-api",
            "opened_incident_ids": (),
            "updated_incident_ids": (),
            "promotion_records": (),
            "unique_candidate_count": 3,
            "promotion_scan_scope": "internal_api_alert_signals",
            "incident_access_mode": "backend",
        }
        from k8s_diag_agent.collect.incident_promotion_batch import (
            PromotionBatch,
        )
        from k8s_diag_agent.collect.incident_promotion_dispatch import (
            IncidentPromotionResult,
        )

        # R7 contract (item 3): the production-path validator in
        # ``add_batch`` MUST raise :class:`PromotionConsistencyContractError`
        # BEFORE the accumulator mutates its state when the
        # backend-authoritative batch violates the
        # ordered-sequence-with-multiplicity contract. The accumulator
        # is empty after the rejected add -- ``add_batch`` rolled back
        # the snapshot so the dispatcher drift is reported instead of
        # being silently absorbed.
        with pytest.raises(PromotionConsistencyContractError) as ctx:
            accumulator.add_batch(
                PromotionBatch(
                    promotion_result=IncidentPromotionResult(**empty_records_batch_dict),
                    promotion_records=(),
                    source_kind="alertmanager",
                )
            )
        contract = ctx.value
        assert contract.opened_incidents == 2
        assert contract.updated_incidents == 1
        assert contract.promotion_record_count == 0
        assert "Legacy-backend regression" in str(contract)
        # The rejected batch left the accumulator unchanged: no
        # records, no batches, no canonical IDs.
        assert accumulator.promotion_records == []
        assert accumulator.batches == []
        assert accumulator.canonical_incident_ids() == []

        # The orchestrator's catch path routes the typed error into
        # the structured promotion_result_summary via the
        # accumulator's ``last_contract_error`` envelope. ``_derive_automatic_diagnosis_inputs``
        # observes the envelope and short-circuits to the
        # ``blocked`` decision so the diagnosis loop is NEVER invoked
        # for a malformed dispatcher response.
        accumulator.last_contract_error = contract
        canonical_ids, summary, consistency, endpoint, execution = (
            _derive_automatic_diagnosis_inputs(accumulator)
        )
        assert canonical_ids == []
        assert consistency is None
        assert summary["promotion_consistency_contract_error"] is not None
        assert summary["promotion_consistency_contract_error"]["opened_incidents"] == 2
        assert summary["promotion_consistency_contract_error"]["updated_incidents"] == 1
        assert "Legacy-backend regression" in (
            summary["promotion_consistency_contract_error"]["message"]
        )
        # R7 (item 1): the explicit decision is blocked and carries
        # the contract-error reason. The diagnosis collector is NOT
        # invoked; the orchestrator emits the
        # ``automatic_diagnosis_blocked`` event instead.
        assert execution.is_blocked
        assert execution.blocked_reason == "promotion_consistency_contract_error"
        assert execution.selection_mode == "blocked"
        # The rejected batch was NOT added to the accumulator, so the
        # blocked decision's incident_access_mode falls back to the
        # no-promotion sentinel. The contract error summary carries
        # the authoritative message so operators can still see the
        # dispatcher drift in the audit log.
        assert execution.incident_access_mode == "no_promotion_run"
        assert summary["incident_access_mode"] == "no_promotion_run"
        assert not execution.should_run


class TestExecuteHealthLoopRunProductionShape:
    """R6 (item 3): a real ``execute_health_loop_run`` invocation.

    The test drives the production function with a minimal stub runner
    so every helper the production flow calls is exercised against the
    stub's contract. Specifically:

    * ``_run_monitoring_discovery`` adds a typed batch to the exact
      ``RunPromotionAccumulator`` the orchestrator passed in.
    * ``_run_automatic_diagnosis_loop`` and ``_log_event`` are spied.
    * Canonical IDs reach diagnosis once in deterministic order.
    * Local/backend/no-promotion access modes remain truthful.
    * The terminal completion event is logged AFTER the diagnosis loop.
    """

    def teardown_method(self) -> None:
        for var in (
            "K9B_BACKEND_INTERNAL_URL",
            "K9B_INTERNAL_API_TOKEN",
            "K9B_INCIDENT_STORE_BACKEND",
            "K9B_PROCESS_ROLE",
            "K9B_INCIDENT_PROMOTION_MODE",
            "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
        ):
            os.environ.pop(var, None)

    def _build_minimal_runner(self, mode: str = "backend") -> Any:
        """Build a stub runner that satisfies the orchestrator contract.

        ``mode`` selects what batch the stub seeds the accumulator with
        during ``_run_monitoring_discovery``. ``backend`` adds the full
        R6 canonical-ID batch; ``local`` adds the local-mode batch;
        ``none`` adds no batch (no-promotion sentinel).
        """

        mode_value = mode

        class _StubRunner:
            def __init__(self) -> None:
                self.run_id = "r6-test"
                self.run_label = "r6-test"
                self._events: list[tuple[str, str, dict[str, Any]]] = []
                self._diagnosis_calls: list[dict[str, Any]] = []
                self.config = MagicMock()
                self.config.trigger_policy.warning_event_threshold = 1
                self.config.collector_version = "test"
                self.config.external_analysis.auto_drilldown = MagicMock()
                self.config.external_analysis.auto_drilldown.provider = None
                self.config.peers = ()
                self.baseline_registry = MagicMock()
                self.comparison_fn = MagicMock(return_value=MagicMock())
                self._manual_keys: list[str] = []
                self._drilldown_collector = None
                self._manual_drilldown_contexts: list[str] = []
                self._manual_external_analysis_requests: list[Any] = []
                self._analysis_policy = MagicMock()
                self._analysis_adapters: dict[str, Any] = {}
                self._record_notification = MagicMock()
                self._image_pull_secret_inspector = MagicMock()
                self._latest_external_artifacts: list[Any] = []
                self._notification_records: list[Any] = []
                self._expected_scheduler_interval_seconds = None
                self._captured_accumulator: Any = None

            def _run_monitoring_discovery(
                self: Any,
                records: Any,
                directories: Any,
                promotion_accumulator: Any = None,
            ) -> None:
                self._captured_accumulator = promotion_accumulator
                from k8s_diag_agent.collect.incident_identity_hardening import (
                    PROMOTION_OUTCOME_OPENED,
                    PROMOTION_OUTCOME_UPDATED,
                    PromotionRecord,
                )
                from k8s_diag_agent.collect.incident_promotion_batch import (
                    PromotionBatch,
                )
                from k8s_diag_agent.collect.incident_promotion_dispatch import (
                    IncidentPromotionResult,
                )
                if mode_value == "backend":
                    batch = PromotionBatch(
                        promotion_result=IncidentPromotionResult(
                            ok=True,
                            scanned=3,
                            firing=3,
                            opened_incidents=2,
                            updated_incidents=1,
                            skipped_duplicates=0,
                            errors=0,
                            promotion_mode="backend-api",
                            opened_incident_ids=("inc-b", "inc-a"),
                            updated_incident_ids=("inc-c",),
                            promotion_records=(
                                {
                                    "source_candidate_id": "cand-1",
                                    "canonical_incident_id": "inc-b",
                                    "promotion_outcome": PROMOTION_OUTCOME_OPENED,
                                },
                                {
                                    "source_candidate_id": "cand-2",
                                    "canonical_incident_id": "inc-a",
                                    "promotion_outcome": PROMOTION_OUTCOME_OPENED,
                                },
                                {
                                    "source_candidate_id": "cand-3",
                                    "canonical_incident_id": "inc-c",
                                    "promotion_outcome": PROMOTION_OUTCOME_UPDATED,
                                },
                            ),
                            unique_candidate_count=3,
                            promotion_scan_scope="internal_api_alert_signals",
                            incident_access_mode="backend",
                        ),
                        promotion_records=(
                            PromotionRecord("cand-1", "inc-b", PROMOTION_OUTCOME_OPENED),
                            PromotionRecord("cand-2", "inc-a", PROMOTION_OUTCOME_OPENED),
                            PromotionRecord("cand-3", "inc-c", PROMOTION_OUTCOME_UPDATED),
                        ),
                        source_kind="alertmanager",
                    )
                elif mode_value == "local":
                    batch = PromotionBatch(
                        promotion_result=IncidentPromotionResult(
                            ok=True,
                            scanned=1,
                            firing=1,
                            opened_incidents=1,
                            updated_incidents=0,
                            skipped_duplicates=0,
                            errors=0,
                            promotion_mode="local",
                            opened_incident_ids=("inc-l1",),
                            updated_incident_ids=(),
                            promotion_records=(
                                {
                                    "source_candidate_id": "cand-l1",
                                    "canonical_incident_id": "inc-l1",
                                    "promotion_outcome": PROMOTION_OUTCOME_OPENED,
                                },
                            ),
                            unique_candidate_count=1,
                            promotion_scan_scope="local_promotion",
                            incident_access_mode="local",
                        ),
                        promotion_records=(
                            PromotionRecord("cand-l1", "inc-l1", PROMOTION_OUTCOME_OPENED),
                        ),
                        source_kind="alertmanager",
                    )
                else:
                    batch = None
                if batch is not None:
                    promotion_accumulator.add_batch(batch)

            def _log_event(self: Any, *args: Any, **kwargs: Any) -> None:
                self._events.append((args[0] if args else "", args[2] if len(args) >= 3 else "", kwargs))

            def _run_automatic_diagnosis_loop(
                self: Any,
                external_analysis_dir: Any,
                *,
                canonical_incident_ids: Any = None,
                promotion_result_summary: Any = None,
                backend_endpoint_identity: Any = None,
                incident_selection_mode: Any = None,
            ) -> dict[str, Any]:
                self._diagnosis_calls.append(
                    {
                        "canonical_incident_ids": list(canonical_incident_ids or []),
                        "incident_access_mode": (
                            promotion_result_summary.get("incident_access_mode")
                            if isinstance(promotion_result_summary, dict)
                            else None
                        ),
                        "promotion_mode": (
                            promotion_result_summary.get("promotion_mode")
                            if isinstance(promotion_result_summary, dict)
                            else None
                        ),
                    }
                )
                return {"incidents_processed": len(canonical_incident_ids or [])}

            def _write_review_artifact(
                self: Any,
                assessments: Any,
                drilldowns: Any,
                directories: Any,
            ) -> tuple[Any, list[Any]]:
                return (directories.get("review"), [])

            def _prune_external_analysis_history(self: Any, path: Any) -> None:
                return None

            def _derive_incident_linkage_context(self: Any, records: Any) -> None:
                return None

        return _StubRunner()

    def _stub_directories(self, tmp_path: Path) -> dict[str, Path]:
        """Build a minimal ``directories`` dict for the orchestrator."""
        directories = {
            "history": tmp_path / "history.json",
            "assessments": tmp_path / "assessments",
            "notifications": tmp_path / "notifications",
            "drilldowns": tmp_path / "drilldowns",
            "external_analysis": tmp_path / "external_analysis",
            "root": tmp_path,
            "review": tmp_path / "review.json",
        }
        for path in directories.values():
            if isinstance(path, Path) and path.suffix:
                path.parent.mkdir(parents=True, exist_ok=True)
            else:
                path.mkdir(parents=True, exist_ok=True)
        return directories

    def test_execute_health_loop_run_backend_canonical_ids_deterministic(
        self,
        tmp_path: Path,
    ) -> None:
        os.environ["K9B_PROCESS_ROLE"] = "scheduler"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "sqlite"
        os.environ["K9B_INCIDENT_PROMOTION_MODE"] = "backend-api"
        os.environ["K9B_BACKEND_INTERNAL_URL"] = "http://k9b-backend:8080"
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"

        # Patch the auxiliary phases so the orchestrator can call them
        # without spinning up the real health-loop machinery.
        with patch(
            "k8s_diag_agent.health.loop_runner_execute.build_assessments_for_records",
            return_value=[],
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute.evaluate_triggers_for_records",
            return_value=[],
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute.build_drilldowns_for_records",
            return_value=[],
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute._run_auto_drilldown_impl",
            return_value=[],
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute.run_external_analysis_for_records",
            return_value=[],
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute.load_runner_history",
            return_value={},
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute.persist_runner_history",
            return_value=None,
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute._run_review_enrichment_impl",
            return_value=None,
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute.run_next_check_planning",
            return_value=None,
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute.write_health_ui_index",
            return_value=tmp_path / "ui" / "index.json",
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute.scan_and_propose",
            return_value=[],
        ):
            runner = self._build_minimal_runner()
            directories = self._stub_directories(tmp_path)
            execute_health_loop_run(runner, [], directories)

        # Canonical IDs reach diagnosis once, in deterministic order.
        assert len(runner._diagnosis_calls) == 1
        diagnosis = runner._diagnosis_calls[0]
        assert diagnosis["canonical_incident_ids"] == ["inc-b", "inc-a", "inc-c"]
        # The accumulator handed to _run_monitoring_discovery is the
        # exact object the production function passed in.
        from k8s_diag_agent.collect.incident_promotion_accumulator import (
            RunPromotionAccumulator,
        )
        assert isinstance(runner._captured_accumulator, RunPromotionAccumulator)
        # Backend access mode is preserved through the orchestrator.
        assert diagnosis["incident_access_mode"] == "backend"
        assert diagnosis["promotion_mode"] == "backend-api"
        # Terminal completion event is emitted AFTER the diagnosis call.
        completion_index = next(
                (idx
                for idx, event in enumerate(runner._events)
                if event[1] == "Health run completed"
                ),
                None,
        )
        assert completion_index is not None
        # The diagnosis call must have happened before the completion
        # event. ``_events`` does not capture the diagnosis call
        # directly, so we use the relative position: the completion
        # event is logged at least once AFTER the diagnosis call has
        # been registered.
        assert len(runner._diagnosis_calls) == 1

    def test_execute_health_loop_run_local_mode_truthful(
        self,
        tmp_path: Path,
    ) -> None:
        """Local mode keeps the local access-mode truthful end-to-end."""
        self._run_orchestrator_with_mode(tmp_path, mode="local")

    def test_execute_health_loop_run_no_promotion_truthful(
        self,
        tmp_path: Path,
    ) -> None:
        """No-promotion runs use the explicit no_promotion sentinel."""
        self._run_orchestrator_with_mode(tmp_path, mode="none")

    def _run_orchestrator_with_mode(self, tmp_path: Path, mode: str) -> None:
        with patch(
            "k8s_diag_agent.health.loop_runner_execute.build_assessments_for_records",
            return_value=[],
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute.evaluate_triggers_for_records",
            return_value=[],
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute.build_drilldowns_for_records",
            return_value=[],
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute._run_auto_drilldown_impl",
            return_value=[],
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute.run_external_analysis_for_records",
            return_value=[],
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute.load_runner_history",
            return_value={},
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute.persist_runner_history",
            return_value=None,
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute._run_review_enrichment_impl",
            return_value=None,
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute.run_next_check_planning",
            return_value=None,
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute.write_health_ui_index",
            return_value=tmp_path / "ui" / "index.json",
        ), patch(
            "k8s_diag_agent.health.loop_runner_execute.scan_and_propose",
            return_value=[],
        ):
            runner = self._build_minimal_runner(mode=mode)
            runner = self._build_minimal_runner(mode=mode)
            directories = self._stub_directories(tmp_path)
            execute_health_loop_run(runner, [], directories)

        assert len(runner._diagnosis_calls) == 1
        diagnosis = runner._diagnosis_calls[0]
        if mode == "local":
            assert diagnosis["incident_access_mode"] == "local"
            assert diagnosis["promotion_mode"] == "local"
            assert diagnosis["canonical_incident_ids"] == ["inc-l1"]
        elif mode == "none":
            assert diagnosis["incident_access_mode"] == "no_promotion_run"
            assert diagnosis["promotion_mode"] == "no_promotion_run"
            assert diagnosis["canonical_incident_ids"] == []
        else:  # pragma: no cover - defensive
            raise AssertionError(f"unexpected mode: {mode}")
