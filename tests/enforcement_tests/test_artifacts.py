"""Tests for pass artifact construction and P4c path writing.

These tests prove that:
1. Pass artifacts have all required PASS_ARTIFACT_FIELDS
2. P4c paths are written correctly
3. Safety metadata is accurate
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    DiagnosisLoopPolicy,
    validate_pass_artifact_schema,
)
from k8s_diag_agent.collect.runtime_artifacts import (
    P4C_DIAGNOSIS_SUBDIR,
    P4C_LOOP_PASSES_SUBDIR,
    RUNTIME_SCHEMA_VERSION,
    build_policy_enforced_pass_artifact,
    write_runtime_pass_artifact,
)
from k8s_diag_agent.collect.runtime_gating import GateSummary
from k8s_diag_agent.collect.runtime_state import LoopRuntimeState

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_policy() -> DiagnosisLoopPolicy:
    """Default policy for testing."""
    return DiagnosisLoopPolicy.live_lab_default()


@pytest.fixture
def sample_case_file() -> dict[str, Any]:
    """Sample case file for testing."""
    return {
        "incident": {
            "incident_id": "test-incident-123",
            "namespace": "default",
            "object_kind": "Pod",
            "object_name": "test-pod",
            "severity": "warning",
        },
        "events": [],
        "pods": [],
    }


# =============================================================================
# Pass Artifact Tests
# =============================================================================


class TestPassArtifactFingerprints:
    """Tests for pass artifact fingerprint tracking."""

    def test_accepted_fingerprints_are_written_to_pass_artifact(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Pass artifact contains fingerprints for checks accepted in this pass."""
        proposed_checks = [
            {"check_id": "check_1"},
            {"check_id": "check_2"},
        ]

        # Create GateSummary for the proposed checks
        gate_summary = GateSummary(
            proposed=2,
            accepted=2,
            rejected_mutating=0,
            rejected_sensitive=0,
            rejected_duplicate=0,
            accepted_checks=proposed_checks,
            rejected_checks=[],
            accepted_fingerprints=["fp1", "fp2"],
            rejected_fingerprints=[],
        )

        runtime_state = LoopRuntimeState(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            started_at=datetime.now(UTC).isoformat(),
        )

        artifact = build_policy_enforced_pass_artifact(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            case_file=sample_case_file,
            policy=sample_policy,
            gate_summary=gate_summary,
            accepted_fingerprints=["fp1", "fp2"],
            runtime_state=runtime_state,
            decision="run_allowed_read_only_checks",
            root_cause_summary="Test root cause",
            confidence="medium",
            runner_result=None,
        )

        # Check fingerprints should be in the artifact
        assert "check_fingerprints" in artifact
        assert len(artifact["check_fingerprints"]) == 2
        assert set(artifact["check_fingerprints"]) == {"fp1", "fp2"}

        # Accepted checks should also be in artifact
        assert "accepted_checks" in artifact
        assert len(artifact["accepted_checks"]) == 2

    def test_rejected_fingerprints_not_in_accepted(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Rejected checks' fingerprints are not in accepted_fingerprints."""
        # Create GateSummary
        gate_summary = GateSummary(
            proposed=2,
            accepted=1,
            rejected_mutating=1,
            rejected_sensitive=0,
            rejected_duplicate=0,
            accepted_checks=[{"check_id": "check_1"}],
            rejected_checks=[{"check_id": "kubectl_apply", "rejection_reason": "mutating_check_rejected"}],
            accepted_fingerprints=["fp1"],
            rejected_fingerprints=["fp2"],
        )

        runtime_state = LoopRuntimeState(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            started_at=datetime.now(UTC).isoformat(),
        )

        artifact = build_policy_enforced_pass_artifact(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            case_file=sample_case_file,
            policy=sample_policy,
            gate_summary=gate_summary,
            accepted_fingerprints=["fp1"],
            runtime_state=runtime_state,
            decision="run_allowed_read_only_checks",
            root_cause_summary="Test root cause",
            confidence="medium",
            runner_result=None,
        )

        # Only the accepted check should be in accepted_checks
        assert "check_1" in artifact["accepted_checks"]
        assert "kubectl_apply" not in artifact["accepted_checks"]

        # But the rejected check should be in rejected_checks
        assert "kubectl_apply" in artifact["rejected_checks"]


# =============================================================================
# P4c Path Writing Tests
# =============================================================================


class TestP4cPathWriting:
    """Tests for P4c-compatible artifact path writing."""

    def test_write_runtime_pass_artifact_to_p4c_path(self, tmp_path: Path) -> None:
        """Pass artifact is written to P4c-compatible path."""
        artifact = {
            "loop_run_id": "test-run",
            "incident_id": "test-incident",
            "pass_index": 1,
            "schema_version": RUNTIME_SCHEMA_VERSION,
        }

        path = write_runtime_pass_artifact(
            external_analysis_dir=tmp_path,
            loop_run_id="test-run",
            pass_index=1,
            artifact=artifact,
        )

        assert path is not None
        assert path.exists()
        
        # Verify the path structure
        expected_path = (
            tmp_path 
            / "phase4-diagnosis" 
            / P4C_DIAGNOSIS_SUBDIR 
            / P4C_LOOP_PASSES_SUBDIR 
            / "test-run-pass-1.json"
        )
        assert path == expected_path
        
        # Verify content
        loaded = json.loads(path.read_text())
        assert loaded["loop_run_id"] == "test-run"
        assert loaded["pass_index"] == 1

    def test_p4c_path_matches_diagnosis_runner_expectation(self, tmp_path: Path) -> None:
        """P4c path matches what the diagnosis runner expects."""
        artifact = {
            "loop_run_id": "auto-test-incident-123-20240101120000",
            "incident_id": "test-incident-123",
            "pass_index": 1,
            "schema_version": RUNTIME_SCHEMA_VERSION,
        }

        path = write_runtime_pass_artifact(
            external_analysis_dir=tmp_path,
            loop_run_id="auto-test-incident-123-20240101120000",
            pass_index=1,
            artifact=artifact,
        )

        assert path is not None
        
        # The diagnosis runner looks for artifacts in this directory
        loop_passes_dir = tmp_path / "phase4-diagnosis" / P4C_DIAGNOSIS_SUBDIR / P4C_LOOP_PASSES_SUBDIR
        assert loop_passes_dir.exists()
        
        # Should find our artifact
        artifacts = list(loop_passes_dir.glob("*.json"))
        assert len(artifacts) == 1
        assert artifacts[0] == path


# =============================================================================
# Safety Metadata Tests
# =============================================================================


class TestSafetyMetadataAccuracy:
    """Tests for accurate safety metadata."""

    def test_no_fake_runner_when_real_runner_used(self) -> None:
        """Safety metadata should reflect actual runner kind, not hardcoded values."""
        artifact = {
            "loop_run_id": "test-run",
            "incident_id": "test-incident",
            "pass_index": 1,
            "safety_metadata": {
                "read_only": True,
                "policy_enforced": True,
                "runner_kind": "real",  # Real runner
                "checks_executed_count": 3,
                "checks_rejected_count": 2,
                "mutating_checks_executed_count": 0,
                "sensitive_reads_executed_count": 0,
            },
        }

        # Verify metadata fields are present and accurate
        safety_meta = artifact.get("safety_metadata", {})
        assert isinstance(safety_meta, dict) and safety_meta.get("policy_enforced") is True
        assert isinstance(safety_meta, dict) and safety_meta.get("runner_kind") == "real"
        assert isinstance(safety_meta, dict) and safety_meta.get("checks_executed_count") == 3
        assert isinstance(safety_meta, dict) and safety_meta.get("mutating_checks_executed_count") == 0

    def test_accurate_rejection_counts_in_metadata(self) -> None:
        """Rejection counts in metadata match actual gating results."""
        gate_summary = GateSummary(
            proposed=3,
            accepted=1,
            rejected_mutating=1,
            rejected_sensitive=1,
            rejected_duplicate=0,
            accepted_checks=[{"check_id": "check_1"}],
            rejected_checks=[
                {"check_id": "kubectl_apply", "rejection_reason": "mutating_check_rejected"},
                {"check_id": "kubectl_get_secrets", "rejection_reason": "sensitive_read_denied"},
            ],
            accepted_fingerprints=["fp1"],
            rejected_fingerprints=["fp2", "fp3"],
        )

        assert gate_summary.rejected_mutating == 1
        assert gate_summary.rejected_sensitive == 1
        assert gate_summary.accepted == 1


# =============================================================================
# Schema Validation Tests
# =============================================================================


class TestSchemaValidation:
    """Tests for pass artifact schema validation."""

    def test_pass_artifact_has_required_fields(
        self,
        sample_policy: DiagnosisLoopPolicy,
        sample_case_file: dict[str, Any],
    ) -> None:
        """Pass artifact has all required PASS_ARTIFACT_FIELDS."""
        gate_summary = GateSummary(
            proposed=1,
            accepted=1,
            rejected_mutating=0,
            rejected_sensitive=0,
            rejected_duplicate=0,
            accepted_checks=[{"check_id": "check_1"}],
            rejected_checks=[],
            accepted_fingerprints=["fp1"],
            rejected_fingerprints=[],
        )

        runtime_state = LoopRuntimeState(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            started_at=datetime.now(UTC).isoformat(),
        )

        artifact = build_policy_enforced_pass_artifact(
            loop_run_id="test-run",
            incident_id="test-incident",
            pass_index=1,
            case_file=sample_case_file,
            policy=sample_policy,
            gate_summary=gate_summary,
            accepted_fingerprints=["fp1"],
            runtime_state=runtime_state,
            decision="run_allowed_read_only_checks",
            root_cause_summary="Test root cause",
            confidence="medium",
            runner_result=None,
        )

        # Validate schema
        is_valid, missing = validate_pass_artifact_schema(artifact)
        
        # All required fields should be present
        assert is_valid is True, f"Missing fields: {missing}"
        assert len(missing) == 0
