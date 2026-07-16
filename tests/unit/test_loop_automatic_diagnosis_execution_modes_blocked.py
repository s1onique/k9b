"""Blocked-path orchestration tests for automatic diagnosis execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from k8s_diag_agent.collect.incident_identity_hardening import (
    PromotionConsistencyContractError,
)
from k8s_diag_agent.collect.incident_promotion_accumulator import (
    RunPromotionAccumulator,
)
from k8s_diag_agent.health.loop_runner_execute import (
    BLOCKED_REASON_PROMOTION_CONSISTENCY_CONTRACT_ERROR,
    _derive_automatic_diagnosis_inputs,
    execute_health_loop_run,
)


class TestExecuteHealthLoopRunBlockedPath:
    """The blocked path short-circuits BEFORE the collector runs."""

    def _accumulator_with_contract_error(self) -> RunPromotionAccumulator:
        accumulator = RunPromotionAccumulator()
        accumulator.last_contract_error = PromotionConsistencyContractError(
            "test blocked: contract error",
            opened_incidents=1,
            updated_incidents=0,
            promotion_record_count=0,
            opened_id_count=1,
            updated_id_count=0,
            missing_canonical_ids=(),
        )
        return accumulator

    def test_blocked_helper_decision_is_blocked(self) -> None:
        """A contract error yields a blocked execution decision."""
        accumulator = self._accumulator_with_contract_error()
        (
            _,
            _,
            _,
            _,
            execution,
        ) = _derive_automatic_diagnosis_inputs(accumulator)
        assert execution.is_blocked
        assert not execution.should_run
        assert execution.blocked_reason == "promotion_consistency_contract_error"

    def test_blocked_branch_does_not_invoke_collector(self) -> None:
        """The real orchestration boundary must not call the collector."""

        class _StubRunner:
            def __init__(self) -> None:
                self.run_id = "r13-blocked-test"
                self.run_label = "r13-blocked-test"
                self._events: list[tuple[str, str, dict[str, Any]]] = []
                self._diagnosis_calls: list[dict[str, Any]] = []
                from unittest.mock import MagicMock

                self.config = MagicMock()
                self.config.trigger_policy.warning_event_threshold = 1
                self.config.collector_version = "test"
                self.config.external_analysis.auto_drilldown = MagicMock()
                self.config.external_analysis.auto_drilldown.provider = None
                self.config.peers = ()
                self.baseline_registry = MagicMock()
                self.comparison_fn = MagicMock(return_value=MagicMock())
                self._manual_keys: list[Any] = []
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

            def _run_monitoring_discovery(
                self,
                records: Any,
                directories: Any,
                promotion_accumulator: Any = None,
            ) -> None:
                del records, directories
                promotion_accumulator.last_contract_error = (
                    PromotionConsistencyContractError(
                        "r13: synthetic contract error",
                        opened_incidents=1,
                        updated_incidents=0,
                        promotion_record_count=0,
                        opened_id_count=1,
                        updated_id_count=0,
                        missing_canonical_ids=(),
                    )
                )

            def _log_event(self, *args: Any, **kwargs: Any) -> None:
                self._events.append(
                    (
                        args[0] if args else "",
                        args[2] if len(args) >= 3 else "",
                        kwargs,
                    )
                )

            def _run_automatic_diagnosis_loop(
                self,
                external_analysis_dir: Any,
                *,
                diagnosis_selection: Any = None,
                promotion_result_summary: Any = None,
                backend_endpoint_identity: Any = None,
            ) -> Any:
                del external_analysis_dir, backend_endpoint_identity
                self._diagnosis_calls.append(
                    {
                        "diagnosis_selection": diagnosis_selection,
                        "incident_access_mode": (
                            promotion_result_summary.get("incident_access_mode")
                            if isinstance(promotion_result_summary, dict)
                            else None
                        ),
                    }
                )
                raise AssertionError(
                    "collector must NOT be invoked for a blocked run"
                )

            def _write_review_artifact(
                self,
                assessments: Any,
                drilldowns: Any,
                directories: Any,
            ) -> tuple[Any, list[Any]]:
                del assessments, drilldowns
                return (directories.get("reviews") or directories.get("review"), [])

            def _prune_external_analysis_history(self, path: Any) -> None:
                del path

            def _derive_incident_linkage_context(self, records: Any) -> None:
                del records

        runner = _StubRunner()
        with __import__("tempfile").TemporaryDirectory() as td:
            tmp_path = Path(td)
            directories = {
                "history": tmp_path / "history.json",
                "assessments": tmp_path / "assessments",
                "notifications": tmp_path / "notifications",
                "drilldowns": tmp_path / "drilldowns",
                "external_analysis": tmp_path / "external_analysis",
                "root": tmp_path,
                "reviews": tmp_path / "reviews",
            }
            for path in directories.values():
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

        assert runner._diagnosis_calls == []
        blocked_events = [
            event
            for event in runner._events
            if event[2].get("event") == "automatic_diagnosis_blocked"
        ]
        assert len(blocked_events) == 1
        blocked_kwargs = blocked_events[0][2]
        assert blocked_kwargs["blocked_reason"] == (
            BLOCKED_REASON_PROMOTION_CONSISTENCY_CONTRACT_ERROR
        )
        assert blocked_kwargs["selection_mode"] == "blocked"
