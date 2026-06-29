"""Tests for OTel Demo K8s-native diagnosis - Multi-pass Contract.

These tests verify the multi-pass diagnosis contract requirements.
"""

from __future__ import annotations


class TestMultiPassContract:
    """Test multi-pass diagnosis contract."""

    def test_min_required_passes_is_2(self) -> None:
        """Minimum required passes is 2 for multi-pass diagnosis."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import MIN_REQUIRED_PASSES

        assert MIN_REQUIRED_PASSES == 2

    def test_single_pass_fails_verification(self) -> None:
        """Single pass diagnosis should fail verification."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import _check_pass_count

        evidence = {"pass_count": 1}
        has_minimum, count = _check_pass_count(evidence)
        assert has_minimum is False
        assert count == 1

    def test_two_passes_pass_verification(self) -> None:
        """Two pass diagnosis should pass verification."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import _check_pass_count

        evidence = {"pass_count": 2}
        has_minimum, count = _check_pass_count(evidence)
        assert has_minimum is True
        assert count == 2

    def test_three_passes_pass_verification(self) -> None:
        """Three pass diagnosis should pass verification."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import _check_pass_count

        evidence = {"pass_count": 3}
        has_minimum, count = _check_pass_count(evidence)
        assert has_minimum is True
        assert count == 3


class TestRootCauseMatching:
    """Test root-cause term matching."""

    def test_shipping_term_detection(self) -> None:
        """Diagnosis should detect 'shipping' term."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import _check_root_cause_terms

        diagnosis = "The shipping deployment has an issue..."
        checks = _check_root_cause_terms(diagnosis)
        assert checks["mentions_shipping"] is True

    def test_node_selector_term_detection(self) -> None:
        """Diagnosis should detect nodeSelector term."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import _check_root_cause_terms

        diagnosis = "The deployment has nodeSelector constraints..."
        checks = _check_root_cause_terms(diagnosis)
        assert checks["mentions_node_selector"] is True

    def test_selector_key_detection(self) -> None:
        """Diagnosis should detect k9b.dev/otel-lab-node key."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import _check_root_cause_terms

        diagnosis = "The nodeSelector requires k9b.dev/otel-lab-node=missing"
        checks = _check_root_cause_terms(diagnosis)
        assert checks["mentions_selector_key"] is True

    def test_missing_value_detection(self) -> None:
        """Diagnosis should detect 'missing' value."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import _check_root_cause_terms

        diagnosis = "The required label value is 'missing'"
        checks = _check_root_cause_terms(diagnosis)
        assert checks["mentions_selector_value"] is True

    def test_unschedulable_detection(self) -> None:
        """Diagnosis should detect unschedulable state."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import _check_root_cause_terms

        diagnosis = "Pod is in Pending state due to being unschedulable"
        checks = _check_root_cause_terms(diagnosis)
        assert checks["mentions_no_matching_node"] is True

    def test_no_matching_node_regex(self) -> None:
        """Diagnosis should detect 'no matching node' patterns."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import _check_root_cause_terms

        patterns = [
            "No matching node found for nodeSelector",
            "no node matches the selector",
            "cannot schedule pod",
        ]
        for diagnosis in patterns:
            checks = _check_root_cause_terms(diagnosis)
            assert checks["mentions_no_matching_node"] is True, f"Failed for: {diagnosis}"


class TestReadOnlyContract:
    """Test read-only contract enforcement."""

    def test_no_mutating_patterns_in_checks(self) -> None:
        """Read-only checks should not contain mutating commands."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import _check_read_only_contract

        read_only_checks = [
            "kubectl_get_deployment",
            "kubectl_get_pods",
            "kubectl_get_events",
            "kubectl_get_nodes",
        ]
        is_read_only, violations = _check_read_only_contract(read_only_checks)
        assert is_read_only is True
        assert len(violations) == 0

    def test_mutating_apply_detected(self) -> None:
        """kubectl apply should be detected as mutating."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import _check_read_only_contract

        mutating_checks = ["kubectl apply -f deployment.yaml"]
        is_read_only, violations = _check_read_only_contract(mutating_checks)
        assert is_read_only is False
        assert len(violations) > 0

    def test_mutating_delete_detected(self) -> None:
        """kubectl delete should be detected as mutating."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import _check_read_only_contract

        mutating_checks = ["kubectl delete pod shipping-abc"]
        is_read_only, violations = _check_read_only_contract(mutating_checks)
        assert is_read_only is False

    def test_mutating_scale_detected(self) -> None:
        """kubectl scale should be detected as mutating."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import _check_read_only_contract

        mutating_checks = ["kubectl scale deployment shipping --replicas=0"]
        is_read_only, violations = _check_read_only_contract(mutating_checks)
        assert is_read_only is False

    def test_empty_checks_are_read_only(self) -> None:
        """Empty executed_checks list should be read-only."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_match import _check_read_only_contract

        is_read_only, violations = _check_read_only_contract([])
        assert is_read_only is True
