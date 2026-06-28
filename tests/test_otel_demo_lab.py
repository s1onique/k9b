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


class TestLiveModeVerifier:
    """Tests for live mode verification."""

    def test_live_verifier_fails_without_traffic(self, tmp_path: Path) -> None:
        """Live verifier fails when traffic-live.json is missing."""
        from scripts.k9b_otel_demo_lab_verify_live import verify_otel_demo_lab_live
        
        # Arrange
        injection_dir = tmp_path / "phase2-injected"
        injection_dir.mkdir(parents=True)
        (injection_dir / "pods.json").write_text('{"items": []}')
        (injection_dir / "flag-config-after.json").write_text('{"enabled": true}')
        
        # Act
        result = verify_otel_demo_lab_live(tmp_path)
        
        # Assert
        assert result["passed"] is False
        assert "live_traffic_not_attempted" in result["failure_classes"]

    def test_live_verifier_fails_with_zero_attempts(self, tmp_path: Path) -> None:
        """Live verifier fails when traffic attempts is zero."""
        from scripts.k9b_otel_demo_lab_verify_live import verify_otel_demo_lab_live
        
        # Arrange
        injection_dir = tmp_path / "phase2-injected"
        injection_dir.mkdir(parents=True)
        (injection_dir / "traffic-live.json").write_text('{"mode": "live", "actual_attempts": 0, "summary_found": true}')
        (injection_dir / "pods.json").write_text('{"items": []}')
        
        # Act
        result = verify_otel_demo_lab_live(tmp_path)
        
        # Assert
        assert result["passed"] is False
        assert "live_traffic_not_attempted" in result["failure_classes"]

    def test_live_verifier_fails_without_recommendationservice(self, tmp_path: Path) -> None:
        """Live verifier fails when recommendationservice evidence is missing."""
        from scripts.k9b_otel_demo_lab_verify_live import verify_otel_demo_lab_live
        
        # Arrange
        injection_dir = tmp_path / "phase2-injected"
        injection_dir.mkdir(parents=True)
        (injection_dir / "traffic-live.json").write_text('{"mode": "live", "actual_attempts": 10, "summary_found": true}')
        (injection_dir / "pods.json").write_text('{"items": [{"metadata": {"name": "frontend"}}]}')
        (injection_dir / "flag-config-after.json").write_text('{"enabled": true}')
        
        # Act
        result = verify_otel_demo_lab_live(tmp_path)
        
        # Assert
        assert result["passed"] is False
        assert "live_recommendationservice_evidence_missing" in result["failure_classes"]

    def test_live_verifier_fails_without_flag_enabled(self, tmp_path: Path) -> None:
        """Live verifier fails when feature flag is not enabled."""
        from scripts.k9b_otel_demo_lab_verify_live import verify_otel_demo_lab_live
        
        # Arrange
        injection_dir = tmp_path / "phase2-injected"
        injection_dir.mkdir(parents=True)
        (injection_dir / "traffic-live.json").write_text('{"mode": "live", "actual_attempts": 10, "summary_found": true}')
        (injection_dir / "pods.json").write_text('{"items": [{"metadata": {"name": "recommendationservice"}}]}')
        (injection_dir / "flag-config-after.json").write_text('{"flags": {"recommendationServiceCacheFailure": {"enabled": false}}}')
        
        # Act
        result = verify_otel_demo_lab_live(tmp_path)
        
        # Assert
        assert result["passed"] is False
        assert "live_feature_flag_not_enabled" in result["failure_classes"]

    def test_live_verifier_passes_with_minimal_live_fixture(self, tmp_path: Path) -> None:
        """Live verifier passes with minimal live fixture."""
        from scripts.k9b_otel_demo_lab_verify_live import verify_otel_demo_lab_live
        
        # Arrange - minimal live fixture
        injection_dir = tmp_path / "phase2-injected"
        injection_dir.mkdir(parents=True)
        
        # Traffic artifact with new shape
        (injection_dir / "traffic-live.json").write_text('{"mode": "live", "actual_attempts": 10, "summary_found": true, "success_count": 8, "failure_count": 2}')
        
        # Recommendationservice with symptom (restart count > 0)
        (injection_dir / "pods.json").write_text('''
        {"items": [
            {"metadata": {"name": "recommendationservice-abc"},
             "status": {"containerStatuses": [
                 {"restartCount": 2, "state": {"running": {}}}
             ]}}
        ]}''')
        
        # Flag before/after evidence
        (injection_dir / "flag-config-before.json").write_text(
            '{"flags": {"recommendationServiceCacheFailure": {"enabled": false}}}'
        )
        (injection_dir / "flag-config-after.json").write_text(
            '{"flags": {"recommendationServiceCacheFailure": {"enabled": true}}}'
        )
        
        # Diagnosis
        diagnosis_dir = tmp_path / "phase4-diagnosis"
        diagnosis_dir.mkdir(parents=True)
        (diagnosis_dir / "final-diagnosis.json").write_text(
            '{"mode": "live", "provider": "test", "affected_component": "recommendationservice"}'
        )
        
        # Act
        result = verify_otel_demo_lab_live(tmp_path)
        
        # Assert
        assert result["passed"] is True
        assert result.get("recommendationservice_found") is True
        assert result.get("flag_enabled") is True

    def test_live_verifier_fails_without_symptom_evidence(self, tmp_path: Path) -> None:
        """Live verifier fails when no symptom evidence present."""
        from scripts.k9b_otel_demo_lab_verify_live import verify_otel_demo_lab_live
        
        # Arrange - no symptom evidence (restart count 0, no waiting state, no logs)
        injection_dir = tmp_path / "phase2-injected"
        injection_dir.mkdir(parents=True)
        
        (injection_dir / "traffic-live.json").write_text('{"mode": "live", "actual_attempts": 10, "summary_found": true}')
        (injection_dir / "pods.json").write_text('''
        {"items": [
            {"metadata": {"name": "recommendationservice-abc"},
             "status": {"containerStatuses": [
                 {"restartCount": 0, "state": {"running": {}}}
             ]}}
        ]}''')
        (injection_dir / "flag-config-after.json").write_text(
            '{"flags": {"recommendationServiceCacheFailure": {"enabled": true}}}'
        )
        
        diagnosis_dir = tmp_path / "phase4-diagnosis"
        diagnosis_dir.mkdir(parents=True)
        (diagnosis_dir / "final-diagnosis.json").write_text('{"mode": "live"}')
        
        # Act
        result = verify_otel_demo_lab_live(tmp_path)
        
        # Assert
        assert result["passed"] is False
        assert "live_symptom_evidence_missing" in result["failure_classes"]

    def test_traffic_plan_contains_mode_scaffold(self, tmp_path: Path) -> None:
        """Verify traffic plan records scaffold mode."""
        from scripts.k9b_otel_demo_lab_traffic import record_traffic_plan
        
        # Arrange
        traffic_dir = tmp_path / "phase2-injected"
        traffic_dir.mkdir(parents=True)
        
        # Mock kubectl_json to return empty services
        import scripts.k9b_otel_demo_lab_traffic as traffic
        original = traffic.kubectl_json
        traffic.kubectl_json = lambda *args, **kwargs: type('obj', (object,), {'success': False})()
        
        try:
            # Act
            result = record_traffic_plan(str(tmp_path), tmp_path, 30)
            
            # Assert
            assert result.get("mode") == "scaffold"
        finally:
            traffic.kubectl_json = original
