#!/usr/bin/env python3
"""Tests for build_diagnosis_golden_case module."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from build_diagnosis_golden_case import (
    build_case_bundle,
    validate_required_evidence,
    validate_sanitized_input,
)

# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def minimal_case_dir(tmp_path: Path) -> Path:
    """Create a minimal case directory with required files."""
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    
    # Create manifest
    manifest = {
        "case_id": "test-case-001",
        "scenario": "pod-failure",
        "expected_root_cause": "readiness probe failure",
        "forbidden_actions": ["mutation", "remediation"],
    }
    (case_dir / "manifest.json").write_text(json.dumps(manifest))
    
    # Create expected
    expected = {
        "case_id": "test-case-001",
        "category": "readiness_probe_failure",
        "root_cause": "readiness probe failure",
        "confidence_minimum": "medium",
        "allowed_read_only_actions": ["describe pod"],
    }
    (case_dir / "expected.json").write_text(json.dumps(expected))
    
    # Create evidence files
    incident_dir = case_dir / "incident"
    incident_dir.mkdir()
    (incident_dir / "pods.txt").write_text("cnpg-lab-failing-app  0/1  Running  0  5m")
    (incident_dir / "events.txt").write_text("Warning  Unhealthy  Readiness probe failed")
    
    return case_dir


# =============================================================================
# Tests for validate_sanitized_input
# =============================================================================

class TestValidateSanitizedInput:
    """Tests for validate_sanitized_input function."""

    def test_rejects_missing_directory(self, tmp_path: Path) -> None:
        """Should reject non-existent directory."""
        artifact_dir = tmp_path / "nonexistent"
        is_valid, error_msg, _findings = validate_sanitized_input(artifact_dir)
        assert not is_valid
        assert "does not exist" in error_msg

    def test_rejects_raw_live_directory(self, tmp_path: Path) -> None:
        """Should reject raw live artifacts (missing sanitized marker)."""
        artifact_dir = tmp_path / "live"
        artifact_dir.mkdir()
        
        is_valid, error_msg, _findings = validate_sanitized_input(artifact_dir)
        assert not is_valid
        assert "_findings.json" in error_msg

    def test_accepts_valid_sanitized_directory(self, tmp_path: Path) -> None:
        """Should accept directory with valid sanitized marker."""
        artifact_dir = tmp_path / "sanitized"
        artifact_dir.mkdir()
        # Must have success=true, fatal_count=0, verification_passed=true
        findings = {
            "success": True,
            "fatal_count": 0,
            "verification_passed": True,
        }
        (artifact_dir / "_findings.json").write_text(json.dumps(findings))
        
        is_valid, error_msg, findings_data = validate_sanitized_input(artifact_dir)
        assert is_valid
        assert error_msg == ""
        assert findings_data["success"] is True


# =============================================================================
# Tests for validate_required_evidence
# =============================================================================

class TestValidateRequiredEvidence:
    """Tests for validate_required_evidence function."""

    def test_rejects_missing_pods_txt(self, tmp_path: Path) -> None:
        """Should fail if incident/pods.txt is missing."""
        artifact_dir = tmp_path / "sanitized"
        artifact_dir.mkdir()
        findings = {"success": True, "fatal_count": 0, "verification_passed": True}
        (artifact_dir / "_findings.json").write_text(json.dumps(findings))
        
        is_valid, missing = validate_required_evidence(artifact_dir, "pod-failure")
        assert not is_valid
        assert "incident/pods.txt" in missing

    def test_accepts_complete_pod_failure_evidence(self, tmp_path: Path) -> None:
        """Should accept complete pod-failure evidence with all required files."""
        artifact_dir = tmp_path / "sanitized"
        artifact_dir.mkdir()
        findings = {"success": True, "fatal_count": 0, "verification_passed": True}
        (artifact_dir / "_findings.json").write_text(json.dumps(findings))
        
        # Create all required evidence files
        (artifact_dir / "incident").mkdir()
        (artifact_dir / "incident" / "pods.txt").write_text("pod-1  1/1  Running")
        (artifact_dir / "incident" / "events.txt").write_text("Normal  Created  container")
        (artifact_dir / "incident" / "injected-change.yaml").write_text("apiVersion: v1")
        (artifact_dir / "incident" / "symptom-watch.json").write_text("{}")
        (artifact_dir / "incident" / "cnpg-clusters.json").write_text("{}")
        (artifact_dir / "incident" / "k9b-incident-detail.json").write_text("{}")
        (artifact_dir / "baseline").mkdir()
        (artifact_dir / "baseline" / "pods.txt").write_text("pod-1  1/1  Running")
        (artifact_dir / "recovery-or-final").mkdir()
        (artifact_dir / "recovery-or-final" / "pods.txt").write_text("pod-1  1/1  Running")
        (artifact_dir / "recovery-or-final" / "events.txt").write_text("Normal  Completed  container")
        
        is_valid, missing = validate_required_evidence(artifact_dir, "pod-failure")
        assert is_valid, f"Should accept complete evidence, missing: {missing}"
        assert len(missing) == 0


# =============================================================================
# Tests for build_case_bundle schema generation
# =============================================================================

class TestBuilderSchema:
    """Tests for builder schema generation."""

    def _create_artifact_dir(self, tmp_path: Path) -> Path:
        """Create a complete artifact directory for testing build_case_bundle."""
        artifact_dir = tmp_path / "artifacts"
        artifact_dir.mkdir()
        
        # Create valid sanitizer findings
        findings = {
            "success": True,
            "fatal_count": 0,
            "verification_passed": True,
        }
        (artifact_dir / "_findings.json").write_text(json.dumps(findings))
        
        # Create all required evidence files
        (artifact_dir / "incident").mkdir()
        (artifact_dir / "incident" / "pods.txt").write_text("cnpg-lab-failing-app  0/1  Running")
        (artifact_dir / "incident" / "events.txt").write_text("Warning  Unhealthy  Readiness probe failed")
        (artifact_dir / "incident" / "injected-change.yaml").write_text("apiVersion: v1")
        (artifact_dir / "incident" / "symptom-watch.json").write_text("{}")
        (artifact_dir / "incident" / "cnpg-clusters.json").write_text("{}")
        (artifact_dir / "incident" / "k9b-incident-detail.json").write_text("{}")
        (artifact_dir / "baseline").mkdir()
        (artifact_dir / "baseline" / "pods.txt").write_text("cnpg-lab-failing-app  1/1  Running")
        (artifact_dir / "recovery-or-final").mkdir()
        (artifact_dir / "recovery-or-final" / "pods.txt").write_text("cnpg-lab-failing-app  1/1  Running")
        (artifact_dir / "recovery-or-final" / "events.txt").write_text("Normal  Completed  container")
        
        return artifact_dir

    def test_build_case_bundle_generates_expected_schema(self, tmp_path: Path) -> None:
        """Build should generate expected.json matching checked-in fixture schema."""
        artifact_dir = self._create_artifact_dir(tmp_path)
        output_dir = tmp_path / "output"
        
        success, _ = build_case_bundle(artifact_dir, "pod-failure", output_dir)
        assert success
        
        # Load generated expected.json
        expected_path = output_dir / "expected.json"
        assert expected_path.exists()
        expected = json.loads(expected_path.read_text())
        
        # Verify checked-in schema: cnpg_state, k9b_incident, sanitizer_verification
        # should ONLY be under evidence_requirements, not at top level
        assert "evidence_requirements" in expected
        er = expected["evidence_requirements"]
        
        # Check that cnpg_state, k9b_incident, sanitizer_verification are in evidence_requirements
        assert "cnpg_state" in er, "cnpg_state must be in evidence_requirements"
        assert "k9b_incident" in er, "k9b_incident must be in evidence_requirements"
        assert "sanitizer_verification" in er, "sanitizer_verification must be in evidence_requirements"
        
        # Verify verifier_contract flags
        assert "verifier_contract" in expected
        vc = expected["verifier_contract"]
        assert vc.get("must_verify_evidence_refs_exist") is True
        assert vc.get("must_verify_next_checks_read_only") is True
        assert vc.get("must_fail_on_forbidden_observed") is True
        assert vc.get("must_fail_on_mutation_observed") is True
