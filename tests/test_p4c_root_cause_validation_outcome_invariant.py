"""Regression test for P4c root-cause validation / normalized outcome invariant.

This test proves that Step 6b (validate_p4c_root_cause) and Step 7 (compute_p4c_outcome)
share the same source of truth for scheduling root-cause evidence validation.

The bug being tested:
    P4c root-cause validation FAILED (prose markers missing)
    P4c normalized outcome: SUCCESS (structured evidence complete)
    LAB RESULT: SUCCESS

The invariant:
    If scheduling_evidence is complete, Step 6b MUST PASS via structured_scheduling_evidence.
    Step 6b FAILED + normalized SUCCESS is a regression.

Run with:
    python -m pytest tests/test_p4c_root_cause_validation_outcome_invariant.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.k8s_diag_agent.collect.incident_scheduling_root_cause import (
    SchedulingRootCauseEvidence,
    check_scheduling_root_cause_complete,
)


class TestP4cRootCauseValidationOutcomeInvariant:
    """Tests for the P4c root-cause validation / outcome invariant.

    The invariant: Step 6b and compute_p4c_outcome must agree on scheduling evidence.
    A Step 6b root-cause validation FAILED state must not produce normalized outcome SUCCESS.
    """

    def test_complete_structured_evidence_prose_missing_step6b_passes(self) -> None:
        """Step 6b PASSES via structured_scheduling_evidence when prose markers missing.

        This is the EXACT scenario from the failing live log:
        - backend raw.signals has FailedScheduling
        - detection_evidence_selector_literal = k9b.dev/otel-lab-node=missing
        - extracted scheduling_evidence is complete
        - diagnosis prose markers are ALL missing
        - Step 6b should pass via structured_scheduling_evidence (not prose_fallback)
        """
        # Simulate the exact evidence shape from the failing live log
        complete_scheduling_evidence = {
            "namespace": "otel-demo",
            "workload_kind": "deployment",
            "workload_name": "shipping",
            "selector_key": "k9b.dev/otel-lab-node",
            "selector_value": "missing",
            "selector_literal": "k9b.dev/otel-lab-node=missing",
            "failed_scheduling": True,
            "unschedulable": True,
            "scheduler_message": (
                "0/1 nodes are available: 1 node(s) didn't match "
                "Pod node selector (k9b.dev/otel-lab-node)."
            ),
            "matching_nodes": (),
            "root_cause_summary": (
                "Deployment/shipping in otel-demo namespace is unschedulable due to "
                "nodeSelector constraint k9b.dev/otel-lab-node=missing - "
                "no nodes satisfy the pod's node selector requirement."
            ),
        }

        # Evidence with NO prose markers (exact scenario from live log)
        evidence = {
            "scheduling_evidence": complete_scheduling_evidence,
            "root_cause_summary": (
                "The deployment is unavailable because the pods cannot be scheduled. "
                "There are no available nodes that match the deployment requirements."
            ),
            "pass_count": 2,
            "pass_run_ids": ["run-001", "run-002"],
            "real_pass_artifacts_found": True,
            "read_only": True,
            "read_only_violations": [],
            "terminal_no_checks_accepted": True,
            "terminal_decision_reached": True,
        }

        # Validate structured evidence is complete
        scheduling_evidence = SchedulingRootCauseEvidence.from_dict(complete_scheduling_evidence)
        assert check_scheduling_root_cause_complete(scheduling_evidence) is True, (
            "This test requires complete scheduling evidence - test setup error"
        )

        # Now test Step 6b validation (structured path)
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase_p4c_structured_validation import (
            _validate_p4c_root_cause_structured,
        )

        success, validation_source, reason = _validate_p4c_root_cause_structured(evidence)

        # INVARIANT: Step 6b MUST PASS via structured_scheduling_evidence
        assert success is True, (
            f"Step 6b must PASS when scheduling_evidence is complete, got success={success}, "
            f"validation_source={validation_source}, reason={reason}"
        )
        assert validation_source == "structured_scheduling_evidence", (
            f"Step 6b must use structured_scheduling_evidence when available, "
            f"got validation_source={validation_source}"
        )

    def test_step6b_and_compute_p4c_outcome_agree_on_complete_structured_evidence(self) -> None:
        """Step 6b and compute_p4c_outcome must agree when structured evidence is complete."""
        complete_scheduling_evidence = {
            "namespace": "otel-demo",
            "workload_kind": "deployment",
            "workload_name": "shipping",
            "selector_key": "k9b.dev/otel-lab-node",
            "selector_value": "missing",
            "selector_literal": "k9b.dev/otel-lab-node=missing",
            "failed_scheduling": True,
            "unschedulable": True,
            "scheduler_message": "0/1 nodes are available: 1 node(s) didn't match Pod node selector.",
            "matching_nodes": (),
            "root_cause_summary": (
                "Deployment/shipping in otel-demo is unschedulable due to "
                "nodeSelector k9b.dev/otel-lab-node=missing."
            ),
        }

        evidence = {
            "scheduling_evidence": complete_scheduling_evidence,
            "root_cause_summary": "The deployment is unavailable.",
            "pass_count": 2,
            "pass_run_ids": ["run-001", "run-002"],
            "real_pass_artifacts_found": True,
            "read_only": True,
            "read_only_violations": [],
            "terminal_no_checks_accepted": True,
            "terminal_decision_reached": True,
        }

        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import (
            compute_p4c_outcome,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase_p4c_structured_validation import (
            _validate_p4c_root_cause_structured,
        )

        step6b_success, step6b_source, _ = _validate_p4c_root_cause_structured(evidence)
        p4c_outcome = compute_p4c_outcome(
            evidence,
            accept_terminal_single_pass=False,
            min_required_passes=2,
            require_root_cause_terms=True,
        )

        # INVARIANT: Both must agree
        assert step6b_success == p4c_outcome.success, (
            f"INVARIANT VIOLATION: Step 6b success={step6b_success} "
            f"but compute_p4c_outcome success={p4c_outcome.success}. "
            f"Step 6b source={step6b_source}, Outcome failures={p4c_outcome.failure_reasons}"
        )

        assert step6b_success is True, f"Step 6b must pass, got {step6b_success}"
        assert p4c_outcome.success is True, (
            f"compute_p4c_outcome must pass with complete structured evidence, "
            f"got success={p4c_outcome.success}, failures={p4c_outcome.failure_reasons}"
        )

    def test_no_split_brain_step6b_failed_outcome_success(self) -> None:
        """Regression: ensure no split-brain between Step 6b FAILED and outcome SUCCESS."""
        complete_scheduling_evidence = {
            "namespace": "otel-demo",
            "workload_kind": "deployment",
            "workload_name": "shipping",
            "selector_key": "k9b.dev/otel-lab-node",
            "selector_value": "missing",
            "selector_literal": "k9b.dev/otel-lab-node=missing",
            "failed_scheduling": True,
            "unschedulable": True,
            "scheduler_message": "0/1 nodes are available: 1 node(s) didn't match Pod node selector.",
            "matching_nodes": (),
            "root_cause_summary": (
                "Deployment/shipping unschedulable: nodeSelector k9b.dev/otel-lab-node=missing."
            ),
        }

        evidence = {
            "scheduling_evidence": complete_scheduling_evidence,
            "root_cause_summary": "The shipping deployment is experiencing availability issues.",
            "pass_count": 2,
            "pass_run_ids": ["run-001", "run-002"],
            "real_pass_artifacts_found": True,
            "read_only": True,
            "read_only_violations": [],
            "terminal_no_checks_accepted": True,
            "terminal_decision_reached": True,
        }

        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import (
            compute_p4c_outcome,
        )
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase_p4c_structured_validation import (
            _validate_p4c_root_cause_structured,
        )

        step6b_success, step6b_source, _ = _validate_p4c_root_cause_structured(evidence)
        p4c_outcome = compute_p4c_outcome(
            evidence,
            accept_terminal_single_pass=False,
            min_required_passes=2,
            require_root_cause_terms=True,
        )

        # REGRESSION CHECK
        assert not (step6b_success is False and p4c_outcome.success is True), (
            "REGRESSION: Step 6b FAILED but outcome SUCCESS - this is the split-brain bug."
        )
        assert not (step6b_success is True and p4c_outcome.success is False), (
            "REGRESSION: Step 6b PASSED but outcome FAIL - inconsistent validation."
        )

    def test_prose_fallback_used_only_when_structured_absent(self) -> None:
        """Prose fallback is only used when structured evidence is absent."""
        incomplete_scheduling_evidence = {
            "namespace": "otel-demo",
            "workload_kind": "deployment",
            "workload_name": "shipping",
            "selector_key": None,
            "selector_value": None,
            "selector_literal": None,
            "failed_scheduling": True,
            "unschedulable": False,
            "scheduler_message": None,
            "matching_nodes": (),
            "root_cause_summary": "Deployment scheduling issue.",
        }

        evidence = {
            "scheduling_evidence": incomplete_scheduling_evidence,
            "root_cause_summary": (
                "Deployment/shipping in otel-demo has FailedScheduling due to "
                "nodeSelector k9b.dev/otel-lab-node=missing."
            ),
        }

        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase_p4c_structured_validation import (
            _validate_p4c_root_cause_structured,
        )

        success, validation_source, reason = _validate_p4c_root_cause_structured(evidence)

        # Incomplete structured evidence must NOT fallback to prose
        assert success is False, f"Incomplete structured evidence must fail, got success={success}"
        assert validation_source == "failed", (
            f"Incomplete structured evidence must NOT use prose_fallback, "
            f"got validation_source={validation_source}"
        )


class TestP4cMalformedStructuredEvidenceRegression:
    """Regression tests for malformed structured evidence handling."""

    def test_malformed_structured_evidence_does_not_fallback_to_prose(self) -> None:
        """Malformed structured evidence must NOT fall through to prose fallback.

        The bug: structured evidence present but malformed could fall through to prose
        fallback, allowing lucky prose markers to mask the malformed evidence.

        The fix: malformed structured evidence returns failed with validation_source=malformed.
        """
        evidence = {
            "scheduling_evidence": {"not": "a valid SchedulingRootCauseEvidence"},
            "root_cause_summary": (
                "Deployment/shipping has FailedScheduling Unschedulable due to "
                "nodeSelector k9b.dev/otel-lab-node=missing."
            ),
        }

        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase_p4c_structured_validation import (
            _validate_p4c_root_cause_structured,
        )

        success, validation_source, reason = _validate_p4c_root_cause_structured(evidence)

        # Malformed structured evidence must NOT fall through to prose
        assert success is False, (
            f"Malformed structured evidence must fail, got success={success}"
        )
        assert validation_source == "failed", (
            f"Malformed structured evidence must return validation_source=failed, "
            f"got validation_source={validation_source}"
        )
        assert "malformed" in reason.lower() or "structured scheduling evidence" in reason.lower(), (
            f"Reason must mention malformed or structured scheduling evidence, got: {reason}"
        )


class TestP4cValidationSourceLogging:
    """Tests for validation_source logging in verdict dict."""

    def test_p4c_verdict_includes_validation_source(self) -> None:
        """P4c verdict dict must include validation_source for diagnostics."""
        complete_scheduling_evidence = {
            "namespace": "otel-demo",
            "workload_kind": "deployment",
            "workload_name": "shipping",
            "selector_key": "k9b.dev/otel-lab-node",
            "selector_value": "missing",
            "selector_literal": "k9b.dev/otel-lab-node=missing",
            "failed_scheduling": True,
            "unschedulable": True,
            "scheduler_message": "0/1 nodes are available.",
            "matching_nodes": (),
            "root_cause_summary": "Deployment/shipping unschedulable: nodeSelector mismatch.",
        }

        evidence = {
            "scheduling_evidence": complete_scheduling_evidence,
            "root_cause_summary": "Deployment unavailable.",
            "pass_count": 2,
            "pass_run_ids": [],
            "real_pass_artifacts_found": True,
            "read_only": True,
            "read_only_violations": [],
        }

        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase_p4c import (
            validate_p4c_root_cause,
        )

        result = validate_p4c_root_cause(evidence)
        verdict = result.get("p4c_verdict", {})

        assert "validation_source" in verdict, (
            "P4c verdict must include validation_source for diagnostics"
        )
        assert verdict["validation_source"] == "structured_scheduling_evidence", (
            f"validation_source must be structured_scheduling_evidence, "
            f"got {verdict['validation_source']}"
        )
