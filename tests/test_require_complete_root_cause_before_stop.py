"""Regression tests for require_complete_root_cause_before_stop propagation.

These tests verify that the require_complete_root_cause_before_stop flag is properly
propagated through the diagnosis loop call chain:

1. run_one_read_only_diagnosis_loop_pass
2. plan_one_read_only_diagnosis_loop_pass
3. plan_next_diagnosis_pass

Bug: The planner was not receiving the require_complete_root_cause_before_stop flag,
causing P4c to accept terminal_no_checks_proposed when root cause was incomplete.

The log showed:
    [pass 2/5] Terminal no-checks decision with 2 passes: stopping loop

But the diagnosis lacked required terms: shipping, nodeSelector, k9b.dev/otel-lab-node
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from k8s_diag_agent.collect.incident_diagnosis_loop_orchestrator import (
    plan_one_read_only_diagnosis_loop_pass,
)
from k8s_diag_agent.collect.incident_diagnosis_loop_planner import (
    plan_next_diagnosis_pass,
)


class TestRequireCompleteRootCauseBeforeStopPropagation:
    """Tests for require_complete_root_cause_before_stop flag propagation."""

    def test_plan_next_diagnosis_pass_respects_flag_with_incomplete_root_cause(self) -> None:
        """Planner should NOT stop when require_complete_root_cause=True and root cause is incomplete.

        This is the core bug: when require_complete_root_cause_before_stop=True,
        the planner should continue the loop when root cause terms are missing.
        """
        # Diagnosis with incomplete root cause (missing shipping, nodeSelector, etc.)
        diagnosis_report: dict[str, Any] = {
            "diagnosis": {
                "category": "deployment_unavailable",
                "confidence": "medium",
                "likely_causes": [
                    "The shipping deployment is experiencing issues"
                ],
            }
        }

        # Minimal case file
        case_file: dict[str, Any] = {
            "incident": {
                "incident_id": "test-incident",
                "namespace": "otel-demo",
                "object_kind": "Deployment",
                "object_name": "shipping",
            }
        }

        # With require_complete_root_cause_before_stop=True, should continue (not stop)
        result = plan_next_diagnosis_pass(
            incident_id="test-incident",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            prior_loop_state=None,
            now=datetime.now(UTC),
            require_complete_root_cause_before_stop=True,
        )

        # Should NOT be a stop decision when root cause is incomplete
        decision = result.get("decision", "")
        assert decision != "stop_no_checks_proposed", (
            f"Expected non-stop decision with incomplete root cause, got: {decision}"
        )

    def test_plan_next_diagnosis_pass_stops_with_complete_root_cause(self) -> None:
        """Planner should stop when require_complete_root_cause=True and root cause is complete.

        When root cause contains all required terms (shipping, nodeSelector, etc.),
        the planner may stop with either stop_root_cause_found (if credible) or
        stop_no_checks_proposed (if root cause is complete but not yet credible).
        """
        # Diagnosis with complete root cause
        diagnosis_report: dict[str, Any] = {
            "diagnosis": {
                "category": "deployment_unavailable",
                "confidence": "high",
                "likely_causes": [
                    "shipping deployment is unavailable because its Pod template has nodeSelector "
                    "k9b.dev/otel-lab-node=missing, and no node matches that selector"
                ],
                "supporting_evidence": [
                    "FailedScheduling event: pod shipping-xxx did not match Pod's node affinity/selector"
                ],
            }
        }

        case_file: dict[str, Any] = {
            "incident": {
                "incident_id": "test-incident",
                "namespace": "otel-demo",
                "object_kind": "Deployment",
                "object_name": "shipping",
            }
        }

        result = plan_next_diagnosis_pass(
            incident_id="test-incident",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            prior_loop_state=None,
            now=datetime.now(UTC),
            require_complete_root_cause_before_stop=True,
        )

        # Should be a terminal stop decision when root cause is complete
        # May be stop_root_cause_found (if credible) or stop_no_checks_proposed
        decision = result.get("decision", "")
        assert decision in ("stop_no_checks_proposed", "stop_root_cause_found"), (
            f"Expected terminal stop decision with complete root cause, got: {decision}"
        )

    def test_plan_one_read_only_diagnosis_loop_pass_passes_flag(self) -> None:
        """plan_one_read_only_diagnosis_loop_pass should propagate the flag to planner."""
        diagnosis_report: dict[str, Any] = {
            "diagnosis": {
                "category": "deployment_unavailable",
                "confidence": "medium",
                "likely_causes": [
                    "The shipping deployment is experiencing issues"
                ],
            }
        }

        case_file: dict[str, Any] = {
            "incident": {
                "incident_id": "test-incident",
                "namespace": "otel-demo",
                "object_kind": "Deployment",
                "object_name": "shipping",
            }
        }

        # Call the planner-only function with the flag
        result = plan_one_read_only_diagnosis_loop_pass(
            incident_id="test-incident",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            run_id="test-run",
            prior_loop_state=None,
            now=datetime.now(UTC),
            require_complete_root_cause_before_stop=True,
        )

        # Should NOT be a stop decision when root cause is incomplete
        decision = result.get("decision", "")
        assert decision != "stop_no_checks_proposed", (
            f"Expected non-stop decision with incomplete root cause, got: {decision}"
        )

    def test_default_behavior_stops_without_flag(self) -> None:
        """Without the flag, planner should stop on no proposals (default behavior)."""
        diagnosis_report: dict[str, Any] = {
            "diagnosis": {
                "category": "deployment_unavailable",
                "confidence": "medium",
                "likely_causes": [
                    "The shipping deployment is experiencing issues"
                ],
            }
        }

        case_file: dict[str, Any] = {
            "incident": {
                "incident_id": "test-incident",
                "namespace": "otel-demo",
                "object_kind": "Deployment",
                "object_name": "shipping",
            }
        }

        # Default: require_complete_root_cause_before_stop=False
        result = plan_next_diagnosis_pass(
            incident_id="test-incident",
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            prior_loop_state=None,
            now=datetime.now(UTC),
            # No explicit flag - defaults to False
        )

        # Default behavior: should stop on no proposals
        decision = result.get("decision", "")
        assert decision == "stop_no_checks_proposed", (
            f"Expected stop_no_checks_proposed with default flag (False), got: {decision}"
        )


class TestP4cScenarioSimulation:
    """Simulates the exact P4c failure scenario from the bug report."""

    def test_two_passes_with_incomplete_root_cause_should_not_stop_early(self) -> None:
        """Simulates the bug: 2 passes with incomplete root cause should NOT stop.

        The bug report showed:
            [pass 2/5] Terminal no-checks decision with 2 passes: stopping loop

        But the diagnosis lacked: shipping, nodeSelector, k9b.dev/otel-lab-node
        """
        # Simulate first pass with incomplete root cause
        diagnosis_report_pass1: dict[str, Any] = {
            "diagnosis": {
                "category": "deployment_unavailable",
                "confidence": "medium",
                "likely_causes": [
                    "The deployment appears to be unavailable"
                ],
            }
        }

        case_file: dict[str, Any] = {
            "incident": {
                "incident_id": "otel-demo-deployment-shipping-deployment_unavailable",
                "namespace": "otel-demo",
                "object_kind": "Deployment",
                "object_name": "shipping",
            }
        }

        # Pass 1: Should continue (no proposals, but continue in lab-strict mode)
        result1 = plan_next_diagnosis_pass(
            incident_id="otel-demo-deployment-shipping-deployment_unavailable",
            case_file=case_file,
            diagnosis_report=diagnosis_report_pass1,
            prior_loop_state=None,
            now=datetime.now(UTC),
            require_complete_root_cause_before_stop=True,
        )

        # Should NOT stop on pass 1 - root cause incomplete
        assert result1.get("decision") != "stop_no_checks_proposed", (
            "Pass 1 should NOT stop with incomplete root cause in lab-strict mode"
        )

        # Simulate second pass also with incomplete root cause
        diagnosis_report_pass2: dict[str, Any] = {
            "diagnosis": {
                "category": "deployment_unavailable",
                "confidence": "medium",
                "likely_causes": [
                    "The shipping deployment has an issue"
                    # Missing: nodeSelector, k9b.dev/otel-lab-node, FailedScheduling
                ],
            }
        }

        # Pass 2: Should also continue - root cause still incomplete
        # Use cast to satisfy mypy (result is dict, but type checker expects Mapping)
        prior_state: Mapping[str, object] | None = cast(
            Mapping[str, object] | None, result1.get("loop_state")
        )
        result2 = plan_next_diagnosis_pass(
            incident_id="otel-demo-deployment-shipping-deployment_unavailable",
            case_file=case_file,
            diagnosis_report=diagnosis_report_pass2,
            prior_loop_state=prior_state,
            now=datetime.now(UTC),
            require_complete_root_cause_before_stop=True,
        )

        # Should NOT stop on pass 2 - root cause still incomplete
        assert result2.get("decision") != "stop_no_checks_proposed", (
            "Pass 2 should NOT stop with incomplete root cause in lab-strict mode"
        )
