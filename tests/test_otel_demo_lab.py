"""Tests for OTEL demo lab modules."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from scripts.k9b_otel_demo_lab_verify import (
    VerificationResult,
    _verify_diagnosis,
    _verify_injection,
)


class TestOtelDemoLabVerifier:
    """Tests for the diagnosis oracle verifier."""

    def test_verify_injection_finds_recommendationservice(self, tmp_path: Path) -> None:
        """Pass case: pods contain recommendationservice."""
        # Arrange - use correct phase directory name
        injection_dir = tmp_path / "phase2-injected"
        injection_dir.mkdir(parents=True)
        (injection_dir / "pods.json").write_text(
            '{"items": [{"metadata": {"name": "recommendationservice-abc123"}}]}'
        )
        (injection_dir / "events.json").write_text('{"items": []}')
        (injection_dir / "injection-command.json").write_text('{"command": "inject"}')

        # Act
        result = _verify_injection(tmp_path)

        # Assert
        assert result["passed"] is True
        assert result["recommendationservice_evidence"] is True

    def test_verify_injection_fails_without_recommendationservice(self, tmp_path: Path) -> None:
        """Fail case: no recommendationservice in pods."""
        # Arrange
        injection_dir = tmp_path / "phase2-injected"
        injection_dir.mkdir(parents=True)
        (injection_dir / "pods.json").write_text(
            '{"items": [{"metadata": {"name": "frontend-xyz789"}}]}'
        )
        (injection_dir / "events.json").write_text('{"items": []}')
        (injection_dir / "injection-command.json").write_text('{"command": "inject"}')

        # Act
        result = _verify_injection(tmp_path)

        # Assert
        assert result["passed"] is True  # Phase passes, but evidence is False
        assert result["recommendationservice_evidence"] is False

    def test_verify_diagnosis_finds_recommendationservice(self, tmp_path: Path) -> None:
        """Pass case: diagnosis mentions recommendationservice and feature flag."""
        # Arrange - use correct phase directory name
        diagnosis_dir = tmp_path / "phase4-diagnosis"
        diagnosis_dir.mkdir(parents=True)
        (diagnosis_dir / "final-diagnosis.json").write_text(
            '{"diagnosis": "The recommendationservice has a cache failure due to feature flag."}'
        )

        # Act
        result = _verify_diagnosis(tmp_path)

        # Assert
        assert result["passed"] is True
        assert result["recommendationservice_mentioned"] is True
        assert result["feature_flag_evidence_found"] is True

    def test_verify_diagnosis_fails_without_recommendationservice(self, tmp_path: Path) -> None:
        """Fail case: diagnosis doesn't mention recommendationservice."""
        # Arrange
        diagnosis_dir = tmp_path / "phase4-diagnosis"
        diagnosis_dir.mkdir(parents=True)
        (diagnosis_dir / "final-diagnosis.json").write_text(
            '{"diagnosis": "The frontend has high latency."}'
        )

        # Act
        result = _verify_diagnosis(tmp_path)

        # Assert
        assert result["passed"] is False
        assert result.get("recommendationservice_mentioned") is False

    def test_verification_result_serialization(self) -> None:
        """Verify VerificationResult can be serialized."""
        result = VerificationResult(
            passed=True,
            failure_classes=[],
            details={},
            recommendationservice_found=True,
            feature_flag_evidence_found=True,
        )
        serialized = asdict(result)
        assert serialized["passed"] is True
        assert serialized["recommendationservice_found"] is True
