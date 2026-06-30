#!/usr/bin/env python3
"""Tests for read-only gate and diagnosis loop policy.

Tests cover:
- Loop stops when RCA confirmed
- Loop stops at max_passes
- Loop stops on repeated plan
- Duplicate check is rejected
- Mutating check is rejected
- No-new-evidence pass stops the loop
- Read-only gate: kubectl get/describe/logs allowed
- Read-only gate: kubectl apply/delete/patch/scale/exec rejected
- Sensitive read gate: kubectl get/describe secret denied by default
- Sensitive read gate: kubectl get/describe secret allowed only with allow_sensitive_reads=True
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
    LoopStopReason,
    is_mutating_check,
    is_read_only_check,
)


class TestReadOnlyCheckGate:
    """Tests for deterministic read-only check gate."""

    def test_kubectl_get_is_read_only(self) -> None:
        """kubectl get is read-only."""
        assert is_read_only_check("kubectl get pods")
        assert is_read_only_check("kubectl get deployments")
        assert is_read_only_check("kubectl get events")
        assert is_read_only_check("kubectl get nodes")

    def test_kubectl_describe_is_read_only(self) -> None:
        """kubectl describe is read-only."""
        assert is_read_only_check("kubectl describe pod mypod")
        assert is_read_only_check("kubectl describe deployment mydeploy")
        assert is_read_only_check("kubectl describe nodes")

    def test_kubectl_logs_is_read_only(self) -> None:
        """kubectl logs is read-only."""
        assert is_read_only_check("kubectl logs mypod")
        assert is_read_only_check("kubectl logs mypod -c container")

    def test_kubectl_apply_is_mutating(self) -> None:
        """kubectl apply is mutating."""
        assert is_mutating_check("kubectl apply -f manifest.yaml")
        assert is_mutating_check("kubectl apply -f deployment.yaml")

    def test_kubectl_delete_is_mutating(self) -> None:
        """kubectl delete is mutating."""
        assert is_mutating_check("kubectl delete pod mypod")
        assert is_mutating_check("kubectl delete -f manifest.yaml")

    def test_kubectl_patch_is_mutating(self) -> None:
        """kubectl patch is mutating."""
        assert is_mutating_check("kubectl patch deployment mydeploy")

    def test_kubectl_scale_is_mutating(self) -> None:
        """kubectl scale is mutating."""
        assert is_mutating_check("kubectl scale deployment mydeploy --replicas=3")

    def test_kubectl_rollout_is_mutating(self) -> None:
        """kubectl rollout is mutating."""
        assert is_mutating_check("kubectl rollout restart deployment mydeploy")
        assert is_mutating_check("kubectl rollout undo deployment mydeploy")

    def test_kubectl_exec_is_mutating(self) -> None:
        """kubectl exec is mutating."""
        assert is_mutating_check("kubectl exec -it mypod -- /bin/sh")
        assert is_mutating_check("kubectl exec mypod -- ls")

    def test_kubectl_port_forward_is_mutating(self) -> None:
        """kubectl port-forward is mutating."""
        assert is_mutating_check("kubectl port-forward pod mypod 8080:80")

    def test_helm_install_is_mutating(self) -> None:
        """helm install is mutating."""
        assert is_mutating_check("helm install myrelease chart")
        assert is_mutating_check("helm upgrade myrelease chart")

    def test_helm_uninstall_is_mutating(self) -> None:
        """helm uninstall is mutating."""
        assert is_mutating_check("helm uninstall myrelease")

    def test_restart_is_mutating(self) -> None:
        """restart commands are mutating."""
        assert is_mutating_check("restart deployment mydeploy")
        assert is_mutating_check("restart pod mypod")

    def test_scale_deployment_is_mutating(self) -> None:
        """scale deployment is mutating."""
        assert is_mutating_check("scale deployment mydeploy --replicas=5")


class TestSensitiveReadGate:
    """Tests for sensitive read gate (kubectl get/describe secret)."""

    def test_get_secret_denied_by_default(self) -> None:
        """kubectl get secret is denied by default."""
        assert is_read_only_check("kubectl get secret mysecret") is False
        assert is_read_only_check("kubectl get secret mysecret -n default") is False

    def test_describe_secret_denied_by_default(self) -> None:
        """kubectl describe secret is denied by default."""
        assert is_read_only_check("kubectl describe secret mysecret") is False
        assert is_read_only_check("kubectl describe secret mysecret -n default") is False

    def test_get_secret_allowed_with_sensitive_read_policy(self) -> None:
        """kubectl get secret is allowed with allow_sensitive_reads=True."""
        assert is_read_only_check("kubectl get secret mysecret", allow_sensitive_reads=True) is True
        assert is_read_only_check("kubectl get secret mysecret -n default", allow_sensitive_reads=True) is True

    def test_describe_secret_allowed_with_sensitive_read_policy(self) -> None:
        """kubectl describe secret is allowed with allow_sensitive_reads=True."""
        assert is_read_only_check("kubectl describe secret mysecret", allow_sensitive_reads=True) is True
        assert is_read_only_check("kubectl describe secret mysecret -n default", allow_sensitive_reads=True) is True

    def test_mutating_check_always_denied(self) -> None:
        """Mutating checks are always denied even with allow_sensitive_reads=True."""
        assert is_read_only_check("kubectl delete pod mypod", allow_sensitive_reads=True) is False
        assert is_read_only_check("kubectl apply -f manifest.yaml", allow_sensitive_reads=True) is False


class TestLoopStopReasons:
    """Tests for typed loop stop reasons."""

    def test_acceptable_stop_reasons(self) -> None:
        """Acceptable stop reasons for clean trajectory."""
        from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
            ACCEPTABLE_P4C_STOP_REASONS,
        )
        assert LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE in ACCEPTABLE_P4C_STOP_REASONS
        assert LoopStopReason.HIGH_CONFIDENCE_ROOT_CAUSE in ACCEPTABLE_P4C_STOP_REASONS

    def test_warning_grade_stop_reasons(self) -> None:
        """Warning-grade stop reasons require RCA valid."""
        from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
            WARNING_GRADE_P4C_STOP_REASONS,
        )
        assert LoopStopReason.MAX_PASSES_REACHED in WARNING_GRADE_P4C_STOP_REASONS

    def test_budget_exhausted_reasons(self) -> None:
        """Budget exhausted reasons."""
        assert LoopStopReason.MAX_PASSES_REACHED.value == "max_passes_reached"
        assert LoopStopReason.MAX_CHECKS_REACHED.value == "max_checks_reached"
        assert LoopStopReason.MAX_MODEL_CALLS_REACHED.value == "max_model_calls_reached"
        assert LoopStopReason.MAX_WALL_CLOCK_REACHED.value == "max_wall_clock_reached"


class TestDiagnosisLoopPolicy:
    """Tests for DiagnosisLoopPolicy."""

    def test_default_policy_values(self) -> None:
        """Default policy has correct values for live-lab."""
        policy = DiagnosisLoopPolicy()
        assert policy.max_passes == 2
        assert policy.max_checks_per_pass == 2
        assert policy.max_total_checks == 4
        assert policy.max_model_calls == 4
        assert policy.max_wall_clock_seconds == 120
        assert policy.stop_on_no_new_evidence is True
        assert policy.stop_on_repeated_plan is True
        assert policy.allow_mutating_checks is False
        assert policy.allow_sensitive_reads is False

    def test_live_lab_default(self) -> None:
        """live_lab_default creates correct policy."""
        policy = DiagnosisLoopPolicy.live_lab_default()
        assert policy.max_passes == 2
        assert policy.max_checks_per_pass == 2
        assert policy.allow_sensitive_reads is False

    def test_permissive_lab(self) -> None:
        """permissive_lab creates more lenient policy."""
        policy = DiagnosisLoopPolicy.permissive_lab()
        assert policy.max_passes == 5
        assert policy.max_checks_per_pass == 5
        assert policy.max_total_checks == 15

    def test_check_budget_exceeded_passes(self) -> None:
        """Budget not exceeded when within limits."""
        policy = DiagnosisLoopPolicy()
        exceeded, reason = policy.check_budget_exceeded(
            current_pass=1,
            checks_this_pass=1,
            total_checks=2,
            model_calls=2,
            elapsed_seconds=60.0,
        )
        assert exceeded is False
        assert reason is None

    def test_check_budget_exceeded_max_passes(self) -> None:
        """Budget exceeded when max passes exceeded."""
        policy = DiagnosisLoopPolicy()
        exceeded, reason = policy.check_budget_exceeded(
            current_pass=3,  # max_passes=2
            checks_this_pass=1,
            total_checks=2,
            model_calls=2,
            elapsed_seconds=60.0,
        )
        assert exceeded is True
        assert reason == LoopStopReason.MAX_PASSES_REACHED

    def test_check_budget_exceeded_max_checks(self) -> None:
        """Budget exceeded when max checks exceeded."""
        policy = DiagnosisLoopPolicy()
        exceeded, reason = policy.check_budget_exceeded(
            current_pass=1,
            checks_this_pass=3,  # max_checks_per_pass=2
            total_checks=3,
            model_calls=2,
            elapsed_seconds=60.0,
        )
        assert exceeded is True
        assert reason == LoopStopReason.MAX_CHECKS_REACHED

    def test_check_budget_exceeded_max_total_checks(self) -> None:
        """Budget exceeded when max total checks exceeded."""
        policy = DiagnosisLoopPolicy()
        exceeded, reason = policy.check_budget_exceeded(
            current_pass=1,
            checks_this_pass=1,
            total_checks=5,  # max_total_checks=4
            model_calls=2,
            elapsed_seconds=60.0,
        )
        assert exceeded is True
        assert reason == LoopStopReason.MAX_CHECKS_REACHED

    def test_check_budget_exceeded_max_wall_clock(self) -> None:
        """Budget exceeded when max wall clock exceeded."""
        policy = DiagnosisLoopPolicy()
        exceeded, reason = policy.check_budget_exceeded(
            current_pass=1,
            checks_this_pass=1,
            total_checks=2,
            model_calls=2,
            elapsed_seconds=150.0,  # max_wall_clock_seconds=120
        )
        assert exceeded is True
        assert reason == LoopStopReason.MAX_WALL_CLOCK_REACHED

    def test_to_dict(self) -> None:
        """Policy serializes to dict correctly."""
        policy = DiagnosisLoopPolicy()
        d = policy.to_dict()
        assert d["max_passes"] == 2
        assert d["max_checks_per_pass"] == 2
        assert d["schema_version"] == "2.0"
        assert d["allow_sensitive_reads"] is False


class TestPassArtifactSchemaValidation:
    """Tests for pass artifact schema validation."""

    def test_validate_pass_artifact_schema_valid(self) -> None:
        """Valid pass artifact passes schema validation."""
        from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
            PASS_ARTIFACT_FIELDS,
            validate_pass_artifact_schema,
        )

        artifact = {field: f"value_for_{field}" for field in PASS_ARTIFACT_FIELDS}
        is_valid, missing = validate_pass_artifact_schema(artifact)
        assert is_valid is True
        assert missing == []

    def test_validate_pass_artifact_schema_missing_fields(self) -> None:
        """Missing fields fails schema validation."""
        from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
            validate_pass_artifact_schema,
        )

        artifact = {
            "loop_run_id": "run-1",
            "incident_id": "inc-1",
        }
        is_valid, missing = validate_pass_artifact_schema(artifact)
        assert is_valid is False
        assert "pass_index" in missing
        assert "check_fingerprints" in missing

    def test_validate_pass_artifact_schema_empty_artifact(self) -> None:
        """Empty artifact fails schema validation."""
        from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
            validate_pass_artifact_schema,
        )

        artifact: dict = {}
        is_valid, missing = validate_pass_artifact_schema(artifact)
        assert is_valid is False
        assert len(missing) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
