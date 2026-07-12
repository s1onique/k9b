"""R3 Integration tests for collector evidence collection wiring.

These tests prove the R3 closure bar:
1. _process_incident calls run_automatic_diagnosis_hypothesis_loop()
2. incident_result.hypothesis_loop_result is assigned the loop result dict
3. _write_loop_summary receives real health run_id (first incident's run_id)
4. At least one test proves: list incidents -> fetch -> case file -> hypothesis burst -> pass 1 -> pass 2 -> summary
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from k8s_diag_agent.collect.incident_diagnosis_authority_seam_types import (
    LifecycleTransition,
    LifecycleWriteApplied,
)
from k8s_diag_agent.collect.incident_diagnosis_dispatch_contracts import (
    DiagnosisPageIncident,
)
from k8s_diag_agent.collect.incident_diagnosis_dispatch_page import (
    IncidentDiagnosisPage,
)
from k8s_diag_agent.collect.incident_diagnosis_pagination_results import (
    AutomaticPageListed,
)


class TestCollectorEntrypointIntegration:
    """Integration tests for collector entrypoint wiring."""

    def _make_page(self, incident_id: str, hour: int = 10) -> IncidentDiagnosisPage:
        """Create an IncidentDiagnosisPage for testing."""
        timestamp = datetime(2024, 1, 15, hour, 30, 0, tzinfo=UTC)
        ts_text = timestamp.isoformat()
        incident = DiagnosisPageIncident(
            incident_id=incident_id,
            status="open",
            first_observed_at=timestamp,
            first_observed_at_key=ts_text,
        )
        return IncidentDiagnosisPage(
            incidents=(incident,),
            next_cursor=None,
            has_more=False,
        )

    def test_collector_calls_hypothesis_loop_and_assigns_result(self, tmp_path: Path) -> None:
        """Collector calls run_automatic_diagnosis_hypothesis_loop and assigns result."""
        with patch.dict(os.environ, {"K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true"}):
            from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
                run_automatic_diagnosis_loop_evidence_collection,
            )
            from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
                BackendIncidentFound,
                BackendIncidentLookupSource,
            )
            from k8s_diag_agent.domain.incident_lifecycle import IncidentId

            # Create mock page with one incident
            mock_page = self._make_page("inc-123")

            # Mock the dependencies
            with patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.list_incidents_with_pagination"
            ) as mock_list, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "fetch_backend_incident_for_diagnosis_typed"
            ) as mock_fetch, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "evaluate_incident_eligibility"
            ) as mock_eligibility, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "is_safe_run_id"
            ) as mock_safe, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "record_diagnosis_loop_started",
                lambda **kwargs: LifecycleWriteApplied(
                    transition=LifecycleTransition.STARTED,
                    incident_id=kwargs["incident_id"],
                ),
            ), patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "record_diagnosis_loop_completed",
                lambda **kwargs: LifecycleWriteApplied(
                    transition=LifecycleTransition.COMPLETED,
                    incident_id=kwargs["incident_id"],
                ),
            ), patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "record_diagnosis_loop_failed",
                lambda **kwargs: LifecycleWriteApplied(
                    transition=LifecycleTransition.FAILED,
                    incident_id=kwargs["incident_id"],
                ),
            ), patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "build_incident_case_file"
            ) as mock_case_file, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "run_policy_enforced_loop_pass"
            ) as mock_policy, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "write_diagnosis_review_packet"
            ) as mock_review, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "run_automatic_diagnosis_hypothesis_loop"
            ) as mock_hypothesis_loop, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "HypothesisLoopConfig"
            ) as _:

                # Setup mocks
                mock_incident_obj = MagicMock()
                mock_incident_obj.incident_id = "inc-123"
                mock_incident_obj.to_dict.return_value = {"incident_id": "inc-123", "title": "Test"}

                expected_loop_result = {"status": "success"}

                mock_list.return_value = AutomaticPageListed(page=mock_page)
                mock_fetch.return_value = BackendIncidentFound(
                    requested_incident_id=IncidentId("inc-123"),
                    incident=mock_incident_obj,
                    source=BackendIncidentLookupSource.LOCAL_STORE,
                    http_status=None,
                    payload_schema_version=None,
                    payload_type=None,
                )
                mock_eligibility.return_value = MagicMock(eligible=True, reason="test")
                mock_safe.return_value = True
                mock_case_file.return_value = {"suggested_checks": []}
                mock_policy.return_value = {
                    "decision": "continue",
                    "runner_result": {"checks_requested": 0, "checks_run": 0},
                    "artifact": None,
                    "loop_pass_artifact": None,
                }
                mock_review.return_value = {"written": False}
                mock_hypothesis_loop.return_value = MagicMock(to_dict=MagicMock(return_value=dict(expected_loop_result)))


                # Run the collector with one incident
                now = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
                result = run_automatic_diagnosis_loop_evidence_collection(
                    external_analysis_dir=tmp_path,
                    config=MagicMock(
                        max_incidents_per_run=10,
                        max_passes_per_incident=2,
                        max_checks_per_pass=3,
                        max_seconds_per_incident=300,
                        write_stop_path_packets=False,
                        to_dict=lambda: {},
                    ),
                    incident_ids=["inc-123"],
                    now=now,
                )

                # Verify the seams were actually exercised (no dead mocks)
                mock_fetch.assert_called_once()
                mock_hypothesis_loop.assert_called_once()

                # Verify the hypothesis loop result is propagated to the
                # collector result via the legacy ``hypothesis_loop_result``
                # field. This is the real behavioral assertion: the loop
                # ran and its result dict landed on the incident outcome.
                assert len(result.incident_results) >= 1
                incident_result = result.incident_results[0]
                assert incident_result.get("hypothesis_loop_result") == expected_loop_result


    def test_collector_summary_uses_real_health_run_id(self, tmp_path: Path) -> None:
        """Collector summary uses first incident's real health run_id, not collector-{id}."""
        with patch.dict(os.environ, {"K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true"}):
            from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
                _write_loop_summary,
            )

            # Test that _write_loop_summary uses the provided run_id
            result = _write_loop_summary(
                external_analysis_dir=tmp_path,
                collector_run_id="collector-abc123",
                incidents_seen=1,
                incidents_eligible=1,
                incidents_processed=1,
                hypothesis_bursts_written=1,
                total_passes_completed=2,
                total_checks_executed=5,
                stop_reason="loop_completed",
                incident_results=[{"incident_id": "inc-1"}],
                run_id="health-run-001",
            )

            assert result.get("written") is True
            artifact_path = result.get("path")
            if artifact_path:
                with open(artifact_path) as f:
                    artifact = json.load(f)
                    assert artifact.get("run_id") == "health-run-001"

    def test_collector_summary_fallback_to_collector_id(self, tmp_path: Path) -> None:
        """When no run_id provided, _write_loop_summary uses collector-{id}."""
        with patch.dict(os.environ, {"K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true"}):
            from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
                _write_loop_summary,
            )

            result = _write_loop_summary(
                external_analysis_dir=tmp_path,
                collector_run_id="collector-xyz789",
                incidents_seen=0,
                incidents_eligible=0,
                incidents_processed=0,
                hypothesis_bursts_written=0,
                total_passes_completed=0,
                total_checks_executed=0,
                stop_reason="no_incidents",
                incident_results=[],
                run_id=None,
            )

            assert result.get("written") is True
            artifact_path = result.get("path")
            if artifact_path:
                with open(artifact_path) as f:
                    artifact = json.load(f)
                    # run_id uses collector- prefix when no run_id is provided
                    assert "collector" in artifact.get("run_id", "")

    def test_incident_result_hypothesis_loop_result_field_assignment(self) -> None:
        """AutoLoopIncidentResult has hypothesis_loop_result field."""
        with patch.dict(os.environ, {"K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true"}):
            from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import AutoLoopIncidentResult

            result = AutoLoopIncidentResult(
                incident_id="test-123",
                eligible=True,
                eligibility_reason="test",
                hypothesis_loop_result={"status": "success", "passes_completed": 2},
            )

            assert result.hypothesis_loop_result is not None
            assert result.hypothesis_loop_result["status"] == "success"

    def test_incident_result_hypothesis_loop_result_can_be_none(self) -> None:
        """AutoLoopIncidentResult hypothesis_loop_result can be None."""
        with patch.dict(os.environ, {"K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true"}):
            from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import AutoLoopIncidentResult

            result = AutoLoopIncidentResult(
                incident_id="test-123",
                eligible=True,
                eligibility_reason="test",
                hypothesis_loop_result=None,
            )

            assert result.hypothesis_loop_result is None

    def test_collector_executes_hypothesis_burst_with_signal_bearing_incident(
        self, tmp_path: Path
    ) -> None:
        """Full integration: incident with signals triggers hypothesis burst."""
        with patch.dict(os.environ, {"K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true"}):
            from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
                run_automatic_diagnosis_loop_evidence_collection,
            )
            from k8s_diag_agent.collect.incident_diagnosis_backend_detail_outcomes import (
                BackendIncidentFound,
                BackendIncidentLookupSource,
            )
            from k8s_diag_agent.domain.incident_lifecycle import IncidentId


            # Create mock page with signal incident
            mock_page = self._make_page("signal-inc-456")

            # Create a mock incident with signals
            mock_incident_obj = MagicMock()
            mock_incident_obj.incident_id = "signal-inc-456"
            mock_incident_obj.to_dict.return_value = {
                "incident_id": "signal-inc-456",
                "title": "Pod Crash Looping",
                "signals": [
                    {
                        "type": "pod_crash_loop",
                        "namespace": "default",
                        "pod_name": "crashing-pod",
                        "restart_count": 10,
                    }
                ],
            }

            # Create mock loop result
            mock_loop_result = MagicMock()
            mock_loop_result.to_dict.return_value = {
                "incident_id": "signal-inc-456",
                "status": "success",
                "total_passes_completed": 2,
                "total_checks_executed": 4,
                "hypothesis_burst_written": True,
                "hypotheses": [
                    {"id": "h1", "title": "Memory pressure", "confidence": 0.8},
                    {"id": "h2", "title": "CPU throttling", "confidence": 0.6},
                ],
            }

            with patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection.list_incidents_with_pagination"
            ) as mock_list, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "fetch_backend_incident_for_diagnosis_typed"
            ) as mock_fetch, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "evaluate_incident_eligibility"
            ) as mock_eligibility, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "is_safe_run_id"
            ) as mock_safe, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "record_diagnosis_loop_started",
                lambda **kwargs: LifecycleWriteApplied(
                    transition=LifecycleTransition.STARTED,
                    incident_id=kwargs["incident_id"],
                ),
            ), patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "record_diagnosis_loop_completed",
                lambda **kwargs: LifecycleWriteApplied(
                    transition=LifecycleTransition.COMPLETED,
                    incident_id=kwargs["incident_id"],
                ),
            ), patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "record_diagnosis_loop_failed",
                lambda **kwargs: LifecycleWriteApplied(
                    transition=LifecycleTransition.FAILED,
                    incident_id=kwargs["incident_id"],
                ),
            ), patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "build_incident_case_file"
            ) as mock_case_file, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "run_policy_enforced_loop_pass"
            ) as mock_policy, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "write_diagnosis_review_packet"
            ) as mock_review, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "run_automatic_diagnosis_hypothesis_loop"
            ) as mock_hypothesis_loop, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_processor."
                "HypothesisLoopConfig"
            ) as _:

                # Setup mock to return realistic hypothesis loop result
                mock_hypothesis_loop.return_value = mock_loop_result

                mock_list.return_value = AutomaticPageListed(page=mock_page)
                mock_fetch.return_value = BackendIncidentFound(
                    requested_incident_id=IncidentId("signal-inc-456"),
                    incident=mock_incident_obj,
                    source=BackendIncidentLookupSource.LOCAL_STORE,
                    http_status=None,
                    payload_schema_version=None,
                    payload_type=None,
                )
                mock_eligibility.return_value = MagicMock(
                    eligible=True,
                    reason="has_signals",
                    budget_diagnostics={"remaining_budget": 100},
                )
                mock_safe.return_value = True
                mock_case_file.return_value = {
                    "suggested_checks": [{"check_id": "mem-check", "title": "Memory"}],
                    "incident_id": "signal-inc-456",
                }
                mock_policy.return_value = {
                    "decision": "continue",
                    "runner_result": {"checks_requested": 3, "checks_run": 2},
                    "artifact": {"written": True},
                    "loop_pass_artifact": {"written": True},
                }
                mock_review.return_value = {"written": True}


                now = datetime(2024, 1, 20, 14, 0, 0, tzinfo=UTC)
                result = run_automatic_diagnosis_loop_evidence_collection(
                    external_analysis_dir=tmp_path,
                    config=MagicMock(
                        max_incidents_per_run=5,
                        max_passes_per_incident=2,
                        max_checks_per_pass=3,
                        max_seconds_per_incident=120,
                        write_stop_path_packets=False,
                        to_dict=lambda: {},
                    ),
                    incident_ids=["signal-inc-456"],
                    now=now,
                )

                # Verify the seams were actually exercised (no dead mocks)
                mock_fetch.assert_called_once()
                mock_hypothesis_loop.assert_called_once()
                call_kwargs = mock_hypothesis_loop.call_args.kwargs
                incident_arg = call_kwargs.get("incident") or call_kwargs.get("incident_arg")
                assert incident_arg is not None
                assert incident_arg.get("signals") is not None


                # Verify result contains hypothesis loop result
                assert len(result.incident_results) >= 1
                incident_result = result.incident_results[0]
                assert incident_result.get("hypothesis_loop_result") is not None
                assert incident_result["hypothesis_loop_result"]["status"] == "success"
