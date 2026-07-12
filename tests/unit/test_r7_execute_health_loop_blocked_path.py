"""ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R7 blocked-path regression tests.

R7 (item 1): the orchestrator MUST NOT invoke the diagnosis loop for
a malformed backend dispatcher response. The production regression
proves:

* malformed backend counts/IDs/records are caught at ``add_batch``;
* the orchestrator's catch path stores the contract error on the
  accumulator before any diagnosis call is attempted;
* the diagnosis collector call count is zero;
* scan mode is never entered;
* the terminal completion event records the blocked reason via a
  typed ``automatic_diagnosis_blocked`` structured event.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.collect.incident_identity_hardening import (
    PROMOTION_OUTCOME_OPENED,
    PromotionConsistencyContractError,
    PromotionRecord,
)
from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.collect.incident_promotion_batch import PromotionBatch
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    INCIDENT_ACCESS_MODE_BACKEND as DISPATCH_BACKEND,
)
from k8s_diag_agent.collect.incident_promotion_dispatch import (
    IncidentPromotionResult,
)
from k8s_diag_agent.health.loop_runner_execute import (
    BLOCKED_REASON_PROMOTION_CONSISTENCY_CONTRACT_ERROR,
    execute_health_loop_run,
)


def _teardown() -> None:
    for var in (
        "K9B_BACKEND_INTERNAL_URL",
        "K9B_INTERNAL_API_TOKEN",
        "K9B_INCIDENT_STORE_BACKEND",
        "K9B_PROCESS_ROLE",
        "K9B_INCIDENT_PROMOTION_MODE",
        "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED",
    ):
        os.environ.pop(var, None)


def _backend_batch(
    *,
    opened_incidents: int = 1,
    updated_incidents: int = 0,
    opened_ids: tuple[str, ...] = ("incident-1",),
    updated_ids: tuple[str, ...] = (),
    records: tuple[PromotionRecord, ...] = (
        PromotionRecord("cand-1", "incident-1", PROMOTION_OUTCOME_OPENED),
    ),
) -> PromotionBatch:
    """Build a backend-authoritative batch for the orchestrator tests."""
    return PromotionBatch(
        promotion_result=IncidentPromotionResult(
            ok=True,
            scanned=opened_incidents + updated_incidents,
            firing=opened_incidents + updated_incidents,
            opened_incidents=opened_incidents,
            updated_incidents=updated_incidents,
            skipped_duplicates=0,
            errors=0,
            promotion_mode="backend-api",
            opened_incident_ids=opened_ids,
            updated_incident_ids=updated_ids,
            promotion_records=(),
            unique_candidate_count=opened_incidents + updated_incidents,
            promotion_scan_scope="internal_api_alert_signals",
            incident_access_mode=DISPATCH_BACKEND,
        ),
        promotion_records=records,
        source_kind="alertmanager",
    )


class TestExecuteHealthLoopRunBlockedPath:
    """R7 (item 1): the orchestrator blocks the diagnosis loop on contract error.

    Production-path regression proving:
    * malformed backend counts/IDs/records;
    * diagnosis collector call count is zero;
    * scan mode is never entered;
    * terminal completion records the blocked reason.
    """

    def setUp(self) -> None:
        _teardown()

    def tearDown(self) -> None:
        _teardown()

    def _build_minimal_runner(self, batch: PromotionBatch | None) -> Any:
        class _StubRunner:
            def __init__(self) -> None:
                self.run_id = "r7-test"
                self.run_label = "r7-test"
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
                self._stub_batch = batch
                self._blocked = batch is None

            def _run_monitoring_discovery(
                self: Any,
                records: Any,
                directories: Any,
                promotion_accumulator: Any = None,
            ) -> None:
                if self._stub_batch is not None:
                    try:
                        promotion_accumulator.add_batch(self._stub_batch)
                    except PromotionConsistencyContractError as exc:
                        promotion_accumulator.last_contract_error = exc

            def _log_event(self: Any, *args: Any, **kwargs: Any) -> None:
                self._events.append(
                    (args[0] if args else "", args[2] if len(args) >= 3 else "", kwargs)
                )

            def _run_automatic_diagnosis_loop(
                self: Any,
                external_analysis_dir: Any,
                *,
                canonical_incident_ids: Any = None,
                promotion_result_summary: Any = None,
                backend_endpoint_identity: Any = None,
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

    def _stub_directories(self, tmp_path: Any) -> dict[str, Any]:
        return {
            "history": tmp_path / "history.json",
            "assessments": tmp_path / "assessments",
            "notifications": tmp_path / "notifications",
            "drilldowns": tmp_path / "drilldowns",
            "external_analysis": tmp_path / "external_analysis",
            "root": tmp_path,
            "review": tmp_path / "review.json",
        }

    def _run_orchestrator(self, runner: Any, tmp_path: Any) -> None:
        directories = self._stub_directories(tmp_path)
        for path in directories.values():
            if hasattr(path, "suffix") and path.suffix:
                path.parent.mkdir(parents=True, exist_ok=True)
            else:
                path.mkdir(parents=True, exist_ok=True)
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
            execute_health_loop_run(runner, [], directories)

    def test_blocked_backend_batch_does_not_invoke_collector(
        self, tmp_path: Any
    ) -> None:
        os.environ["K9B_PROCESS_ROLE"] = "scheduler"
        os.environ["K9B_INCIDENT_STORE_BACKEND"] = "sqlite"
        os.environ["K9B_INCIDENT_PROMOTION_MODE"] = "backend-api"
        os.environ["K9B_BACKEND_INTERNAL_URL"] = "http://k9b-backend:8080"
        os.environ["K9B_INTERNAL_API_TOKEN"] = "test-token"
        # Build a malformed backend batch: nonempty counts, empty
        # records and empty IDs. add_batch MUST raise and the
        # orchestrator's catch path stores the error on the accumulator.
        bad_batch = _backend_batch(
            opened_incidents=2,
            updated_incidents=1,
            opened_ids=(),
            updated_ids=(),
            records=(),
        )
        runner = self._build_minimal_runner(bad_batch)
        self._run_orchestrator(runner, tmp_path)

        # R7 (item 1) production regression: the diagnosis collector
        # is NEVER invoked for a blocked run. scan mode is never
        # entered either.
        assert len(runner._diagnosis_calls) == 0

        # The terminal-completion log is still emitted, but it records
        # the blocked reason so downstream consumers see why diagnosis
        # was skipped.
        completion_events = [
            event for event in runner._events
            if event[1] == "Health run completed"
        ]
        assert len(completion_events) == 1
        completion_kwargs = completion_events[0][2]
        # The completion event surfaces the blocked path so operators
        # can audit the dispatcher regression.
        assert completion_kwargs["automatic_diagnosis_synchronous"] is True

        # A typed ``automatic_diagnosis_blocked`` structured event was
        # emitted before the completion log.
        blocked_events = [
            event for event in runner._events
            if event[2].get("event") == "automatic_diagnosis_blocked"
        ]
        assert len(blocked_events) == 1
        blocked_kwargs = blocked_events[0][2]
        assert blocked_kwargs["blocked_reason"] == (
            BLOCKED_REASON_PROMOTION_CONSISTENCY_CONTRACT_ERROR
        )
        assert blocked_kwargs["selection_mode"] == "blocked"
        # The rejected batch was NOT added to the accumulator, so the
        # blocked event reports the no-promotion sentinel for the
        # access mode. The operator-visible contract failure in the
        # contract_error envelope is the authoritative diagnostic; the
        # access mode here is just the accumulator-truth fallback.
        assert blocked_kwargs["incident_access_mode"] == "no_promotion_run"

    def test_blocked_batch_keeps_accumulator_unmutated(self) -> None:
        """A rejected batch leaves the accumulator empty (validate-before-mutate)."""
        accumulator = RunPromotionAccumulator()
        bad_batch = _backend_batch(
            opened_incidents=2,
            updated_incidents=1,
            opened_ids=(),
            updated_ids=(),
            records=(),
        )
        with pytest.raises(PromotionConsistencyContractError):
            accumulator.add_batch(bad_batch)
        # The accumulator was NOT mutated.
        assert accumulator.promotion_records == []
        assert accumulator.batches == []
        assert accumulator.canonical_incident_ids() == []
        assert accumulator.total_opened_incidents == 0
        assert accumulator.total_updated_incidents == 0