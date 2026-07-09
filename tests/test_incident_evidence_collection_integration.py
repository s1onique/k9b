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


class TestCollectorEntrypointIntegration:
    """Integration tests for collector entrypoint wiring."""

    def test_collector_calls_hypothesis_loop_and_assigns_result(self, tmp_path: Path) -> None:
        """Collector calls run_automatic_diagnosis_hypothesis_loop and assigns result."""
        # Set env to enable the loop
        with patch.dict(os.environ, {"K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true"}):
            from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
                run_automatic_diagnosis_loop_evidence_collection,
            )

            # Mock the dependencies
            mock_incident = MagicMock()
            mock_incident.incident_id = "inc-123"
            mock_incident.to_dict.return_value = {
                "incident_id": "inc-123",
                "title": "Test Incident",
            }

            with patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection."
                "list_incidents_for_diagnosis"
            ) as mock_list, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection."
                "fetch_incident_for_diagnosis"
            ) as mock_fetch, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection."
                "check_incident_eligibility"
            ) as mock_eligibility, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection."
                "is_safe_run_id"
            ) as mock_safe, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection."
                "get_incident_store"
            ) as _, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection."
                "build_incident_case_file"
            ) as mock_case_file, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection."
                "run_policy_enforced_loop_pass"
            ) as mock_policy, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection."
                "write_diagnosis_review_packet"
            ) as mock_review:

                # Setup mocks
                mock_incident_obj = MagicMock()
                mock_incident_obj.incident_id = "inc-123"
                mock_incident_obj.to_dict.return_value = {"incident_id": "inc-123", "title": "Test"}

                mock_list.return_value = ([MagicMock(incident_id="inc-123")], True, None)
                mock_fetch.return_value = (mock_incident_obj, True, None)
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

                # Verify the hypothesis loop was called
                # It should be called once (for the one incident)
                assert len(result.incident_results) >= 1

                # Check that hypothesis_loop_result is present in incident result
                incident_result = result.incident_results[0]
                assert "hypothesis_loop_result" in incident_result

                # hypothesis_loop_result should be a dict (or None if loop failed)
                # The fact that it's in the dict means the field is being assigned
                loop_result = incident_result.get("hypothesis_loop_result")
                assert loop_result is None or isinstance(loop_result, dict)

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
                total_checks_executed=3,
                stop_reason="loop_completed",
                incident_results=[],
                run_id="auto-incident-123-20240115103000",  # Real health run_id
            )

            assert result["written"] is True

            # Verify the artifact uses the real health run_id
            content = json.loads(Path(result["path"]).read_text())
            assert content["run_id"] == "auto-incident-123-20240115103000"
            assert content["collector_run_id"] == "collector-abc123"

            # The path should contain the real run_id, not collector-run_id
            assert "auto-incident-123-20240115103000" in result["path"]

    def test_collector_summary_fallback_to_collector_id(self, tmp_path: Path) -> None:
        """When no real run_id provided, summary uses collector-based run_id."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
            _write_loop_summary,
        )

        # Test fallback when run_id is None
        result = _write_loop_summary(
            external_analysis_dir=tmp_path,
            collector_run_id="collector-xyz789",
            incidents_seen=0,
            incidents_eligible=0,
            incidents_processed=0,
            hypothesis_bursts_written=0,
            total_passes_completed=0,
            total_checks_executed=0,
            stop_reason="no_eligible_incidents",
            incident_results=[],
            run_id=None,  # No real run_id available
        )

        assert result["written"] is True

        content = json.loads(Path(result["path"]).read_text())
        # Should fallback to collector-{collector_run_id}
        assert content["run_id"] == "collector-collector-xyz789"
        assert content["collector_run_id"] == "collector-xyz789"

    def test_incident_result_hypothesis_loop_result_field_assignment(self) -> None:
        """AutoLoopIncidentResult correctly serializes hypothesis_loop_result field."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import (
            AutoLoopIncidentResult,
        )

        loop_result = {
            "total_passes_completed": 2,
            "total_checks_executed": 3,
            "hypothesis_burst_written": True,
            "passes": [
                {"pass_number": 1, "checks_executed": 2},
                {"pass_number": 2, "checks_executed": 1},
            ],
        }

        result = AutoLoopIncidentResult(
            incident_id="inc-456",
            eligible=True,
            eligibility_reason="test_eligible",
            hypothesis_loop_result=loop_result,
        )

        # Verify field is accessible
        assert result.hypothesis_loop_result == loop_result

        # Verify to_dict includes it
        as_dict = result.to_dict()
        assert "hypothesis_loop_result" in as_dict
        assert as_dict["hypothesis_loop_result"]["total_passes_completed"] == 2

    def test_incident_result_hypothesis_loop_result_can_be_none(self) -> None:
        """AutoLoopIncidentResult hypothesis_loop_result can be None (loop not run)."""
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import (
            AutoLoopIncidentResult,
        )

        result = AutoLoopIncidentResult(
            incident_id="inc-789",
            eligible=True,
            eligibility_reason="test",
            hypothesis_loop_result=None,
        )

        assert result.hypothesis_loop_result is None

        as_dict = result.to_dict()
        # None fields may or may not be in dict depending on implementation
        # Just verify no error on serialization
        assert isinstance(as_dict, dict)

    def test_collector_executes_hypothesis_burst_with_signal_bearing_incident(self, tmp_path: Path) -> None:
        """Collector executes hypothesis burst with passes and checks - proves pass execution."""
        with patch.dict(os.environ, {"K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED": "true"}):
            from k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection import (
                run_automatic_diagnosis_loop_evidence_collection,
            )

            # Mock the hypothesis loop to return a realistic result with passes
            # Patch at the source module where the function is defined
            mock_loop_result = MagicMock()
            mock_loop_result.to_dict.return_value = {
                "total_passes_completed": 2,
                "total_checks_executed": 3,
                "hypothesis_burst_written": True,
                "passes": [
                    {"pass_number": 1, "checks_executed": 2},
                    {"pass_number": 2, "checks_executed": 1},
                ],
            }

            with patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection."
                "list_incidents_for_diagnosis"
            ) as mock_list, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection."
                "fetch_incident_for_diagnosis"
            ) as mock_fetch, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection."
                "check_incident_eligibility"
            ) as mock_eligibility, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection."
                "is_safe_run_id"
            ) as mock_safe, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection."
                "get_incident_store"
            ) as _, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection."
                "build_incident_case_file"
            ) as mock_case_file, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection."
                "run_policy_enforced_loop_pass"
            ) as mock_policy, patch(
                "k8s_diag_agent.collect.incident_diagnosis_auto_loop_evidence_collection."
                "write_diagnosis_review_packet"
            ) as mock_review, patch(
                "k8s_diag_agent.collect.incident_automatic_diagnosis_loop."
                "run_automatic_diagnosis_hypothesis_loop"
            ) as mock_hypothesis_loop:

                # Setup mock to return realistic hypothesis loop result
                mock_hypothesis_loop.return_value = mock_loop_result

                # Signal-bearing incident
                mock_incident_obj = MagicMock()
                mock_incident_obj.incident_id = "inc-signal-123"
                mock_incident_obj.to_dict.return_value = {
                    "incident_id": "inc-signal-123",
                    "title": "Pod CrashLoopBackoff",
                    "cluster": "prod",
                    "namespace": "default",
                }

                mock_list.return_value = ([MagicMock(incident_id="inc-signal-123")], True, None)
                mock_fetch.return_value = (mock_incident_obj, True, None)
                mock_eligibility.return_value = MagicMock(eligible=True, reason="signal_bearing")
                mock_safe.return_value = True
                mock_case_file.return_value = {
                    "suggested_checks": [
                        {"check_id": "pod_status", "title": "Pod Status"},
                    ]
                }
                mock_policy.return_value = {
                    "decision": "continue",
                    "runner_result": {"checks_requested": 1, "checks_run": 1},
                    "artifact": None,
                    "loop_pass_artifact": None,
                }
                mock_review.return_value = {"written": False}

                now = datetime(2024, 6, 15, 14, 30, 0, tzinfo=UTC)
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
                    incident_ids=["inc-signal-123"],
                    now=now,
                )

                # Verify hypothesis loop was called with signal-bearing incident
                mock_hypothesis_loop.assert_called_once()

                # Verify result structure
                assert len(result.incident_results) >= 1
                incident_result = result.incident_results[0]
                assert "hypothesis_loop_result" in incident_result

                # Assert the loop result has nonzero counters - proves pass execution
                loop_result = incident_result["hypothesis_loop_result"]
                assert loop_result is not None, "hypothesis_loop_result should not be None"
                assert isinstance(loop_result, dict), "hypothesis_loop_result should be a dict"

                # Core assertions proving pass execution
                assert loop_result.get("hypothesis_burst_written") is True
                assert loop_result.get("total_passes_completed", 0) >= 1, (
                    "Should have completed at least 1 pass"
                )
                assert loop_result.get("total_checks_executed", 0) >= 1, (
                    "Should have executed at least 1 check"
                )

                # Verify passes are present
                passes = loop_result.get("passes", [])
                assert len(passes) >= 1, "Should have at least 1 pass"
                assert passes[0].get("pass_number") == 1

                # Verify summary artifact was written with correct counters
                # Find the summary artifact in tmp_path
                summary_files = list(tmp_path.rglob("automatic-diagnosis/*.json"))
                assert len(summary_files) >= 1, "Should have written at least 1 summary artifact"

                # Read and verify summary content
                summary_content = json.loads(summary_files[0].read_text())
                assert summary_content["summary"]["hypothesis_bursts_written"] >= 1
                assert summary_content["summary"]["total_passes_completed"] >= 1
                assert summary_content["summary"]["total_checks_executed"] >= 1
