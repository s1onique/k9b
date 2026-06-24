#!/usr/bin/env python3
"""Tests for run_diagnosis_offline module."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from run_diagnosis_offline import (
    analyze_evidence,
    diagnose,
    load_case_bundle,
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


@pytest.fixture
def sample_diagnosis() -> dict:
    """Sample correct diagnosis output."""
    return {
        "category": "readiness_probe_failure",
        "root_cause": "readiness probe failure",
        "confidence": "high",
        "description": "Pod is Running but NotReady due to readiness probe failure",
        "evidence_refs": ["incident/pods.txt", "incident/events.txt"],
        "read_only": True,
        "next_checks": [
            "describe pod",
            "get events",
        ],
    }


@pytest.fixture
def wrong_diagnosis_mutation() -> dict:
    """Diagnosis that proposes mutation."""
    return {
        "category": "readiness_probe_failure",
        "root_cause": "readiness probe failure",
        "confidence": "high",
        "description": "You should kubectl apply a fix",
        "evidence_refs": ["incident/pods.txt"],
        "read_only": True,
        "next_checks": [],
    }


@pytest.fixture
def low_confidence_diagnosis() -> dict:
    """Diagnosis with low confidence."""
    return {
        "category": "unknown",
        "root_cause": "unknown",
        "confidence": "low",
        "description": "Cannot determine root cause",
        "evidence_refs": [],
        "read_only": True,
        "next_checks": [],
    }


# =============================================================================
# Tests for analyze_evidence
# =============================================================================

class TestAnalyzeEvidence:
    """Tests for analyze_evidence function."""

    def test_detects_pod_running(self) -> None:
        """Should detect pod running state."""
        evidence = {
            "incident/pods.txt": "cnpg-lab-failing-app  0/1  Running  0  5m",
        }
        findings = analyze_evidence(evidence)
        assert findings["pod_running"] is True

    def test_detects_pod_not_ready(self) -> None:
        """Should detect pod NotReady state."""
        evidence = {
            "incident/pods.txt": "cnpg-lab-failing-app  0/1  Running  0  5m",
        }
        findings = analyze_evidence(evidence)
        assert findings["pod_not_ready"] is True

    def test_detects_readiness_probe_failure(self) -> None:
        """Should detect readiness probe failure evidence."""
        evidence = {
            "incident/events.txt": "Warning  Unhealthy  Readiness probe failed with exit code 1",
        }
        findings = analyze_evidence(evidence)
        assert findings["readiness_probe_failure_evidence"] is True

    def test_detects_unhealthy_events(self) -> None:
        """Should detect Unhealthy events."""
        evidence = {
            "incident/events.txt": "Warning  Unhealthy  Readiness probe failed",
        }
        findings = analyze_evidence(evidence)
        assert findings["unhealthy_events"] is True


# =============================================================================
# Tests for diagnose
# =============================================================================

class TestDiagnose:
    """Tests for diagnose function."""

    def test_correct_diagnosis(self) -> None:
        """Should produce correct readiness probe failure diagnosis."""
        findings = {
            "pod_running": True,
            "pod_not_ready": True,
            "readiness_probe_failure_evidence": True,
            "unhealthy_events": True,
            "container_running": True,
            "container_ready": False,
        }
        expected = {
            "category": "readiness_probe_failure",
        }
        
        diagnosis = diagnose(findings, expected)
        
        assert diagnosis["category"] == "readiness_probe_failure"
        assert diagnosis["root_cause"] == "readiness probe failure"
        assert diagnosis["confidence"] == "high"

    def test_unknown_diagnosis_insufficient_evidence(self) -> None:
        """Should return unknown when evidence is insufficient."""
        findings = {
            "pod_running": False,
            "pod_not_ready": False,
            "readiness_probe_failure_evidence": False,
            "unhealthy_events": False,
            "container_running": False,
            "container_ready": False,
        }
        expected: dict = {}
        
        diagnosis = diagnose(findings, expected)
        
        assert diagnosis["category"] == "unknown"
        assert diagnosis["confidence"] == "low"


# =============================================================================
# Integration Tests
# =============================================================================

class TestOfflineRunnerIntegration:
    """Integration tests for offline diagnosis runner."""

    def test_end_to_end_correct_diagnosis(self, minimal_case_dir: Path) -> None:
        """Should produce correct diagnosis for pod-failure case."""
        manifest, expected, evidence_files = load_case_bundle(minimal_case_dir)
        
        findings = analyze_evidence(evidence_files)
        diagnosis = diagnose(findings, expected)
        
        # Should detect readiness probe failure
        assert findings["readiness_probe_failure_evidence"] is True
        assert diagnosis["category"] == "readiness_probe_failure"

    def test_verifier_passes_correct_diagnosis(
        self, minimal_case_dir: Path, sample_diagnosis: dict
    ) -> None:
        """Verifier should pass for correct diagnosis."""
        from verify_diagnosis_golden_case import (
            verify_category,
            verify_confidence,
            verify_evidence_refs,
            verify_no_mutation_proposals,
            verify_no_wrong_conclusions,
            verify_read_only,
            verify_root_cause,
        )
        
        expected_path = minimal_case_dir / "expected.json"
        expected = json.loads(expected_path.read_text())
        
        all_failures: list = []
        all_failures.extend(("category", m) for m in verify_category(sample_diagnosis, expected))
        all_failures.extend(("root_cause", m) for m in verify_root_cause(sample_diagnosis, expected))
        all_failures.extend(("forbidden", m) for m in verify_no_wrong_conclusions(sample_diagnosis))
        all_failures.extend(("mutation", m) for m in verify_no_mutation_proposals(sample_diagnosis))
        all_failures.extend(("confidence", m) for m in verify_confidence(sample_diagnosis, expected))
        all_failures.extend(("evidence", m) for m in verify_evidence_refs(sample_diagnosis, expected))
        all_failures.extend(("read_only", m) for m in verify_read_only(sample_diagnosis))
        
        assert len(all_failures) == 0

    def test_verifier_fails_mutation_proposal(
        self, minimal_case_dir: Path, wrong_diagnosis_mutation: dict
    ) -> None:
        """Verifier should fail for mutation proposal."""
        from verify_diagnosis_golden_case import verify_no_mutation_proposals
        
        all_failures: list = []
        all_failures.extend(("mutation", m) for m in verify_no_mutation_proposals(wrong_diagnosis_mutation))
        assert len(all_failures) >= 1
