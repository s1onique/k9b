#!/usr/bin/env python3
"""Runtime contract tests for policy-enforced diagnosis loop."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    PASS_ARTIFACT_FIELDS,
    DiagnosisLoopPolicy,
    LoopStopReason,
    validate_pass_artifact_schema,
)
from k8s_diag_agent.collect.incident_diagnosis_loop_runtime import (
    RUNTIME_SCHEMA_VERSION,
    GateSummary,
    build_policy_enforced_pass_artifact,
    gate_checks,
    run_policy_enforced_loop_pass,
)


# Fixtures
@pytest.fixture
def default_policy() -> DiagnosisLoopPolicy:
    return DiagnosisLoopPolicy.live_lab_default()

@pytest.fixture
def permissive_policy() -> DiagnosisLoopPolicy:
    return DiagnosisLoopPolicy.permissive_lab()

@pytest.fixture
def sample_case_file() -> dict[str, Any]:
    return {
        "incident": {"incident_id": "INC-001", "namespace": "default", "object_kind": "Pod", "object_name": "my-pod", "severity": "warning"},
        "signals": [{"type": "warning", "message": "CPU throttling"}],
        "events": [{"type": "Warning", "reason": "BackOff"}],
    }

@pytest.fixture
def sample_orchestrator_result() -> dict[str, Any]:
    return {
        "decision": "run_allowed_read_only_checks",
        "loop_update": {
            "pass_index": 1,
            "proposed_next_checks": [
                {"check_id": "kubectl_get_pods", "parameters": {"namespace": "default"}},
                {"check_id": "kubectl_describe_pod", "parameters": {"name": "my-pod"}},
            ],
            "root_cause_candidate": {"summary": "CPU throttling due to limits", "confidence": "medium"},
        },
        "runner_result": {"results": [{"check_id": "kubectl_get_pods", "status": "completed", "parameters": {}}, {"check_id": "kubectl_describe_pod", "status": "completed", "parameters": {}}]},
    }

# Test gate_checks
class TestGateChecks:
    def test_rejects_kubectl_patch(self, default_policy: DiagnosisLoopPolicy) -> None:
        # Pattern: "kubectl patch" matches MUTATING_ACTION_PATTERNS
        summary = gate_checks([{"check_id": "kubectl patch deployment", "parameters": {}}], default_policy, set())
        assert summary.rejected_mutating == 1 and summary.accepted == 0

    def test_rejects_kubectl_delete(self, default_policy: DiagnosisLoopPolicy) -> None:
        # Pattern: "kubectl delete" matches MUTATING_ACTION_PATTERNS
        assert gate_checks([{"check_id": "kubectl delete pod", "parameters": {}}], default_policy, set()).rejected_mutating == 1

    def test_rejects_kubectl_apply(self, default_policy: DiagnosisLoopPolicy) -> None:
        # Pattern: "kubectl apply" matches MUTATING_ACTION_PATTERNS
        assert gate_checks([{"check_id": "kubectl apply", "parameters": {}}], default_policy, set()).rejected_mutating == 1

    def test_rejects_kubectl_get_secret(self, default_policy: DiagnosisLoopPolicy) -> None:
        # Pattern: "kubectl get secret" matches SENSITIVE_READ_PATTERNS
        summary = gate_checks([{"check_id": "kubectl get secret", "parameters": {}}], default_policy, set())
        assert summary.rejected_sensitive == 1 and summary.accepted == 0

    def test_rejects_kubectl_describe_secret(self, default_policy: DiagnosisLoopPolicy) -> None:
        # Pattern: "kubectl describe secret" matches SENSITIVE_READ_PATTERNS
        assert gate_checks([{"check_id": "kubectl describe secret", "parameters": {}}], default_policy, set()).rejected_sensitive == 1

    def test_allows_read_only_checks(self, default_policy: DiagnosisLoopPolicy) -> None:
        proposed = [
            {"check_id": "kubectl get pods", "parameters": {"namespace": "default"}},
            {"check_id": "kubectl describe pod", "parameters": {"name": "my-pod"}},
            {"check_id": "kubectl logs", "parameters": {"name": "my-pod"}},
        ]
        summary = gate_checks(proposed, default_policy, set())
        assert summary.proposed == 3 and summary.accepted == 3

    def test_rejects_duplicate_fingerprints(self, default_policy: DiagnosisLoopPolicy) -> None:
        # First check accepted, second check rejected as duplicate
        content = "kubectl_get_pods:" + json.dumps({"namespace": "default"}, sort_keys=True)
        seen_fp = hashlib.sha256(content.encode()).hexdigest()[:16]
        summary = gate_checks([{"check_id": "kubectl_get_pods", "parameters": {"namespace": "default"}}] * 2, default_policy, {seen_fp})
        assert summary.rejected_duplicate == 2 and summary.accepted == 0

    def test_allows_mutating_with_permissive_policy(self, permissive_policy: DiagnosisLoopPolicy) -> None:
        # Create a truly permissive policy
        permissive = DiagnosisLoopPolicy(allow_mutating_checks=True, allow_sensitive_reads=False)
        summary = gate_checks([{"check_id": "kubectl patch deployment", "parameters": {}}], permissive, set())
        assert summary.rejected_mutating == 0 and summary.accepted == 1

    def test_allows_sensitive_with_permissive_policy(self, permissive_policy: DiagnosisLoopPolicy) -> None:
        # Create a truly permissive policy
        permissive = DiagnosisLoopPolicy(allow_mutating_checks=False, allow_sensitive_reads=True)
        summary = gate_checks([{"check_id": "kubectl get secret", "parameters": {}}], permissive, set())
        assert summary.rejected_sensitive == 0 and summary.accepted == 1

    def test_gate_summary_fields(self, default_policy: DiagnosisLoopPolicy) -> None:
        summary = gate_checks([{"check_id": "kubectl_get_pods", "parameters": {}}], default_policy, set())
        assert hasattr(summary, "proposed") and hasattr(summary, "accepted") and hasattr(summary, "rejected_checks")

# Test build_policy_enforced_pass_artifact
class TestBuildArtifact:
    def test_artifact_has_all_pass_fields(self, sample_orchestrator_result: dict, sample_case_file: dict, default_policy: DiagnosisLoopPolicy) -> None:
        artifact = build_policy_enforced_pass_artifact(
            orchestrator_result=sample_orchestrator_result, loop_run_id="run-001", incident_id="INC-001",
            case_file=sample_case_file, policy=default_policy,
            gate_summary=GateSummary(proposed=2, accepted=2, rejected_mutating=0, rejected_sensitive=0, rejected_duplicate=0, accepted_checks=[], rejected_checks=[]),
            seen_fingerprints=set(), now=datetime(2026, 6, 30, 12, 0, 0, tzinfo=UTC),
        )
        for field in PASS_ARTIFACT_FIELDS:
            assert field in artifact, f"Missing: {field}"

    def test_artifact_schema_validation(self, sample_orchestrator_result: dict, sample_case_file: dict, default_policy: DiagnosisLoopPolicy) -> None:
        artifact = build_policy_enforced_pass_artifact(
            orchestrator_result=sample_orchestrator_result, loop_run_id="run-001", incident_id="INC-001",
            case_file=sample_case_file, policy=default_policy,
            gate_summary=GateSummary(proposed=2, accepted=2, rejected_mutating=0, rejected_sensitive=0, rejected_duplicate=0, accepted_checks=[], rejected_checks=[]),
            seen_fingerprints=set(), now=datetime(2026, 6, 30, 12, 0, 0, tzinfo=UTC),
        )
        is_valid, missing = validate_pass_artifact_schema(artifact)
        assert is_valid is True, f"Missing: {missing}"

    def test_artifact_contains_runtime_metadata(self, sample_orchestrator_result: dict, sample_case_file: dict, default_policy: DiagnosisLoopPolicy) -> None:
        artifact = build_policy_enforced_pass_artifact(
            orchestrator_result=sample_orchestrator_result, loop_run_id="run-001", incident_id="INC-001",
            case_file=sample_case_file, policy=default_policy,
            gate_summary=GateSummary(proposed=2, accepted=1, rejected_mutating=0, rejected_sensitive=1, rejected_duplicate=0, accepted_checks=[], rejected_checks=[]),
            seen_fingerprints=set(), now=datetime(2026, 6, 30, 12, 0, 0, tzinfo=UTC),
        )
        assert artifact["schema_version"] == RUNTIME_SCHEMA_VERSION and artifact["gate_summary"]["rejected_sensitive"] == 1

    def test_artifact_safety_metadata(self, sample_orchestrator_result: dict, sample_case_file: dict, default_policy: DiagnosisLoopPolicy) -> None:
        artifact = build_policy_enforced_pass_artifact(
            orchestrator_result=sample_orchestrator_result, loop_run_id="run-001", incident_id="INC-001",
            case_file=sample_case_file, policy=default_policy,
            gate_summary=GateSummary(proposed=2, accepted=2, rejected_mutating=0, rejected_sensitive=0, rejected_duplicate=0, accepted_checks=[], rejected_checks=[]),
            seen_fingerprints=set(), now=datetime(2026, 6, 30, 12, 0, 0, tzinfo=UTC),
        )
        safety = artifact["safety_metadata"]
        assert safety["read_only"] is True and safety["policy_enforced"] is True and safety["allow_mutating_checks"] is False

    def test_stop_reason_mapped(self, sample_orchestrator_result: dict, sample_case_file: dict, default_policy: DiagnosisLoopPolicy) -> None:
        result = dict(sample_orchestrator_result)
        result["decision"] = "stop_budget_exhausted"
        artifact = build_policy_enforced_pass_artifact(
            orchestrator_result=result, loop_run_id="run-001", incident_id="INC-001",
            case_file=sample_case_file, policy=default_policy,
            gate_summary=GateSummary(proposed=2, accepted=2, rejected_mutating=0, rejected_sensitive=0, rejected_duplicate=0, accepted_checks=[], rejected_checks=[]),
            seen_fingerprints=set(), now=datetime(2026, 6, 30, 12, 0, 0, tzinfo=UTC),
        )
        assert artifact["stop_reason"] == LoopStopReason.MAX_CHECKS_REACHED.value

# Test run_policy_enforced_loop_pass
class TestRunPolicyEnforced:
    def test_raises_on_unsafe_run_id(self, sample_case_file: dict, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unsafe run_id"):
            run_policy_enforced_loop_pass(incident_id="INC-001", external_analysis_dir=tmp_path, case_file=sample_case_file, diagnosis_report={}, run_id="../../etc/passwd")

    def test_raises_on_empty_run_id(self, sample_case_file: dict, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unsafe run_id"):
            run_policy_enforced_loop_pass(incident_id="INC-001", external_analysis_dir=tmp_path, case_file=sample_case_file, diagnosis_report={}, run_id="")

    def test_returns_augmented_result(self, sample_case_file: dict, tmp_path: Path) -> None:
        result = run_policy_enforced_loop_pass(incident_id="INC-001", external_analysis_dir=tmp_path, case_file=sample_case_file, diagnosis_report={}, run_id="test-run-001", policy=None, fake_handlers={})
        assert result["policy_enforced"] is True and "policy" in result and "pass_artifact" in result

    def test_pass_artifact_in_result(self, sample_case_file: dict, tmp_path: Path) -> None:
        result = run_policy_enforced_loop_pass(incident_id="INC-001", external_analysis_dir=tmp_path, case_file=sample_case_file, diagnosis_report={}, run_id="test-run-002", policy=None, fake_handlers={})
        artifact = result["pass_artifact"]
        assert isinstance(artifact, dict)
        is_valid, missing = validate_pass_artifact_schema(artifact)
        assert is_valid is True, f"Missing: {missing}"

    def test_policy_artifact_path_written(self, sample_case_file: dict, tmp_path: Path) -> None:
        result = run_policy_enforced_loop_pass(incident_id="INC-001", external_analysis_dir=tmp_path, case_file=sample_case_file, diagnosis_report={}, run_id="test-run-003", policy=None, fake_handlers={})
        path_str = str(result["policy_pass_artifact_path"])
        assert path_str is not None
        artifact_path = Path(path_str)
        assert artifact_path.exists()
        with open(artifact_path) as f:
            written = json.load(f)
        is_valid, missing = validate_pass_artifact_schema(written)
        assert is_valid is True, f"Missing: {missing}"

    def test_uses_provided_policy(self, sample_case_file: dict, tmp_path: Path) -> None:
        custom_policy = DiagnosisLoopPolicy(max_passes=5, max_checks_per_pass=10, allow_mutating_checks=True)
        result = run_policy_enforced_loop_pass(incident_id="INC-001", external_analysis_dir=tmp_path, case_file=sample_case_file, diagnosis_report={}, run_id="test-run-004", policy=custom_policy, fake_handlers={})
        policy_result = result.get("policy")
        assert isinstance(policy_result, dict) and policy_result["max_passes"] == 5 and policy_result["allow_mutating_checks"] is True

    def test_deterministic_with_fixed_datetime(self, sample_case_file: dict, tmp_path: Path) -> None:
        fixed_now = datetime(2026, 6, 30, 12, 0, 0, tzinfo=UTC)
        result1 = run_policy_enforced_loop_pass(incident_id="INC-001", external_analysis_dir=tmp_path, case_file=sample_case_file, diagnosis_report={}, run_id="test-run-005", policy=None, fake_handlers={}, now=fixed_now)
        result2 = run_policy_enforced_loop_pass(incident_id="INC-001", external_analysis_dir=tmp_path, case_file=sample_case_file, diagnosis_report={}, run_id="test-run-006", policy=None, fake_handlers={}, now=fixed_now)
        assert result1["pass_artifact"]["generated_at"] == result2["pass_artifact"]["generated_at"]  # type: ignore[index]

# Test integration scenarios
class TestIntegration:
    def test_multiple_passes_track_fingerprints(self, default_policy: DiagnosisLoopPolicy) -> None:
        summary1 = gate_checks([{"check_id": "kubectl_get_pods", "parameters": {"namespace": "default"}}], default_policy, set())
        assert summary1.accepted == 1
        content = "kubectl_get_pods:" + json.dumps({"namespace": "default"}, sort_keys=True)
        fp = hashlib.sha256(content.encode()).hexdigest()[:16]
        summary2 = gate_checks([{"check_id": "kubectl_get_pods", "parameters": {"namespace": "default"}}], default_policy, {fp})
        assert summary2.accepted == 0 and summary2.rejected_duplicate == 1

    def test_mixed_checks_gating(self, default_policy: DiagnosisLoopPolicy) -> None:
        # Use check_ids that match actual patterns in gates
        proposed = [
            {"check_id": "kubectl get pods", "parameters": {}},
            {"check_id": "kubectl patch deployment", "parameters": {}},  # matches "kubectl patch"
            {"check_id": "kubectl get secret", "parameters": {}},      # matches "kubectl get secret"
            {"check_id": "kubectl describe pod", "parameters": {}},
        ]
        summary = gate_checks(proposed, default_policy, set())
        assert summary.proposed == 4 and summary.accepted == 2 and summary.rejected_mutating == 1 and summary.rejected_sensitive == 1

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
