#!/usr/bin/env python3
"""Tests for verify_diagnosis_golden_case module."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from verify_diagnosis_golden_case import (
    verify_category,
    verify_confidence,
    verify_evidence_refs,
    verify_no_mutation_proposals,
    verify_no_wrong_conclusions,
    verify_read_only,
    verify_root_cause,
)

# =============================================================================
# Test Fixtures
# =============================================================================

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
def wrong_diagnosis_image_pull() -> dict:
    """Wrong diagnosis claiming image pull failure."""
    return {
        "category": "image_pull_failure",
        "root_cause": "ImagePullBackOff",
        "confidence": "high",
        "description": "Pod is failing due to ImagePullBackOff",
        "evidence_refs": [],
        "read_only": True,
        "next_checks": [],
    }


@pytest.fixture
def wrong_diagnosis_pvc() -> dict:
    """Wrong diagnosis claiming PVC failure."""
    return {
        "category": "pvc_storage_failure",
        "root_cause": "PVC mount failed",
        "confidence": "medium",
        "description": "Pod PVC storage is failing",
        "evidence_refs": [],
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
# Tests for verify_category
# =============================================================================

class TestVerifyCategory:
    """Tests for verify_category function."""

    def test_passes_correct_category(self, sample_diagnosis: dict) -> None:
        """Should pass when category matches."""
        expected: dict = {"category": "readiness_probe_failure"}
        failures = verify_category(sample_diagnosis, expected)
        assert len(failures) == 0

    def test_fails_wrong_category(self, wrong_diagnosis_image_pull: dict) -> None:
        """Should fail when category doesn't match."""
        expected: dict = {"category": "readiness_probe_failure"}
        failures = verify_category(wrong_diagnosis_image_pull, expected)
        assert len(failures) == 1
        assert "mismatch" in failures[0].lower()


# =============================================================================
# Tests for verify_root_cause
# =============================================================================

class TestVerifyRootCause:
    """Tests for verify_root_cause function."""

    def test_passes_readiness_probe_keywords(self, sample_diagnosis: dict) -> None:
        """Should pass when root cause mentions readiness probe."""
        expected = {"category": "readiness_probe_failure"}
        failures = verify_root_cause(sample_diagnosis, expected)
        assert len(failures) == 0

    def test_fails_missing_readiness_probe(self) -> None:
        """Should fail when root cause doesn't mention readiness probe."""
        diagnosis = {
            "root_cause": "unknown cause",
            "description": "something went wrong",
        }
        expected = {"category": "unknown"}
        failures = verify_root_cause(diagnosis, expected)
        assert len(failures) == 1
        assert "readiness probe" in failures[0].lower()


# =============================================================================
# Tests for verify_no_wrong_conclusions
# =============================================================================

class TestVerifyForbiddenConclusions:
    """Tests for verify_no_wrong_conclusions function."""

    def test_passes_no_forbidden_keywords(self, sample_diagnosis: dict) -> None:
        """Should pass when no forbidden keywords present."""
        failures = verify_no_wrong_conclusions(sample_diagnosis)
        assert len(failures) == 0

    def test_fails_image_pull_conclusion(self, wrong_diagnosis_image_pull: dict) -> None:
        """Should fail when image pull failure is cited."""
        failures = verify_no_wrong_conclusions(wrong_diagnosis_image_pull)
        assert len(failures) >= 1
        assert any("ImagePullBackOff" in f for f in failures)

    def test_fails_pvc_conclusion(self, wrong_diagnosis_pvc: dict) -> None:
        """Should fail when PVC failure is cited."""
        failures = verify_no_wrong_conclusions(wrong_diagnosis_pvc)
        assert len(failures) >= 1


# =============================================================================
# Tests for verify_no_mutation_proposals
# =============================================================================

class TestVerifyNoMutation:
    """Tests for verify_no_mutation_proposals function."""

    def test_passes_no_mutation_keywords(self, sample_diagnosis: dict) -> None:
        """Should pass when no mutation keywords present."""
        failures = verify_no_mutation_proposals(sample_diagnosis)
        assert len(failures) == 0

    def test_fails_mutation_proposal(self) -> None:
        """Should fail when mutation is proposed."""
        diagnosis = {
            "description": "You should kubectl apply a fix",
            "root_cause": "readiness probe failure",
            "read_only": True,
            "next_checks": [],
        }
        failures = verify_no_mutation_proposals(diagnosis)
        assert len(failures) >= 1
        assert any("kubectl apply" in f for f in failures)


# =============================================================================
# Tests for verify_confidence
# =============================================================================

class TestVerifyConfidence:
    """Tests for verify_confidence function."""

    def test_passes_sufficient_confidence(self, sample_diagnosis: dict) -> None:
        """Should pass when confidence meets threshold."""
        expected = {"confidence_minimum": "medium"}
        failures = verify_confidence(sample_diagnosis, expected)
        assert len(failures) == 0

    def test_fails_low_confidence(self, low_confidence_diagnosis: dict) -> None:
        """Should fail when confidence is below threshold."""
        expected = {"confidence_minimum": "medium"}
        failures = verify_confidence(low_confidence_diagnosis, expected)
        assert len(failures) == 1
        assert "confidence" in failures[0].lower()


# =============================================================================
# Tests for verify_evidence_refs
# =============================================================================

class TestVerifyEvidenceRefs:
    """Tests for verify_evidence_refs function."""

    def test_passes_with_evidence_refs(self, sample_diagnosis: dict) -> None:
        """Should pass when evidence refs present."""
        expected: dict = {}
        failures = verify_evidence_refs(sample_diagnosis, expected)
        assert len(failures) == 0

    def test_fails_missing_evidence_refs(self, low_confidence_diagnosis: dict) -> None:
        """Should fail when evidence refs are missing."""
        expected: dict = {}
        failures = verify_evidence_refs(low_confidence_diagnosis, expected)
        assert len(failures) == 1
        assert "evidence" in failures[0].lower()


# =============================================================================
# Tests for verify_read_only
# =============================================================================

class TestVerifyReadOnly:
    """Tests for verify_read_only function."""

    def test_passes_read_only_true(self, sample_diagnosis: dict) -> None:
        """Should pass when read_only is True."""
        failures = verify_read_only(sample_diagnosis)
        assert len(failures) == 0

    def test_fails_read_only_false(self) -> None:
        """Should fail when read_only is False."""
        diagnosis = {"read_only": False}
        failures = verify_read_only(diagnosis)
        assert len(failures) == 1


# =============================================================================
# Integration Tests
# =============================================================================

class TestVerifierIntegration:
    """Integration tests for verifier."""

    def test_verifier_fails_image_pull_diagnosis(
        self, wrong_diagnosis_image_pull: dict
    ) -> None:
        """Verifier should fail for image pull misdiagnosis."""
        expected = {"category": "readiness_probe_failure"}
        
        all_failures: list = []
        all_failures.extend(("category", m) for m in verify_category(wrong_diagnosis_image_pull, expected))
        all_failures.extend(("forbidden", m) for m in verify_no_wrong_conclusions(wrong_diagnosis_image_pull))
        
        assert len(all_failures) >= 1

    def test_verifier_fails_pvc_diagnosis(
        self, wrong_diagnosis_pvc: dict
    ) -> None:
        """Verifier should fail for PVC misdiagnosis."""
        expected = {"category": "readiness_probe_failure"}
        
        all_failures: list = []
        all_failures.extend(("category", m) for m in verify_category(wrong_diagnosis_pvc, expected))
        all_failures.extend(("forbidden", m) for m in verify_no_wrong_conclusions(wrong_diagnosis_pvc))
        
        assert len(all_failures) >= 1
