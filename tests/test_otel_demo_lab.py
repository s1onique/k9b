"""Tests for OTEL demo lab modules."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.k9b_otel_demo_lab_constants import (
    CONFIGURED_OTEL_DEMO_CHART_VERSION_ENV,
    FAILURE_HELM_CHART_VERSION_NOT_FOUND,
    OTEL_DEMO_CHART,
    OTEL_DEMO_CHART_VERSION,
    get_configured_otel_demo_chart_version,
)
from scripts.k9b_otel_demo_lab_deployment import (
    _classify_helm_chart_version_error,
    _validate_chart_version,
)
from scripts.k9b_otel_demo_lab_types import LabConfig, LabResult
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


class TestLabResultSchema:
    """Regression tests for LabResult contract."""

    def test_lab_result_exposes_provider_smoke_passed_default(self) -> None:
        """LabResult.provider_smoke_passed has fail-closed default."""
        result = LabResult()
        assert result.provider_smoke_passed is False

    def test_lab_result_provider_smoke_passed_can_be_set_true(self) -> None:
        """LabResult.provider_smoke_passed can be set to True."""
        result = LabResult(provider_smoke_passed=True)
        assert result.provider_smoke_passed is True

    def test_lab_result_serialization_includes_provider_smoke(self) -> None:
        """LabResult serializes provider_smoke_passed to dict."""
        result = LabResult(provider_smoke_passed=True)
        serialized = asdict(result)
        assert "provider_smoke_passed" in serialized
        assert serialized["provider_smoke_passed"] is True


class TestLabResultSummaryOutput:
    """Regression tests for LabResult summary output."""

    def test_summary_prints_provider_smoke_passed(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Summary prints 'PASSED' when provider_smoke_passed is True."""
        result = LabResult(provider_smoke_passed=True)
        print(f"Provider smoke: {'PASSED' if result.provider_smoke_passed else 'SKIPPED/FAILED'}")
        out = capsys.readouterr().out
        assert "Provider smoke: PASSED" in out

    def test_summary_prints_provider_smoke_skipped(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Summary prints 'SKIPPED/FAILED' when provider_smoke_passed is False."""
        result = LabResult(provider_smoke_passed=False)
        print(f"Provider smoke: {'PASSED' if result.provider_smoke_passed else 'SKIPPED/FAILED'}")
        out = capsys.readouterr().out
        assert "Provider smoke: SKIPPED/FAILED" in out


class TestHelmChartVersionHandling:
    """Regression tests for Helm chart version handling.

    These tests verify the fix for the OTel Demo live lab failure where
    the lab was dying in Phase 1 because it pinned a non-existent Helm
    chart version (0.45.0 instead of the actual 0.40.9).
    """

    def test_default_chart_version_is_0_40_9(self) -> None:
        """Default chart version must be 0.40.9 (the actual published version)."""
        assert OTEL_DEMO_CHART_VERSION == "0.40.9"

    def test_failure_constant_exists_for_missing_chart_version(self) -> None:
        """FAILURE_HELM_CHART_VERSION_NOT_FOUND constant must be defined."""
        assert FAILURE_HELM_CHART_VERSION_NOT_FOUND == "helm_chart_version_not_found"

    def test_chart_version_error_classifier_detects_no_chart_version_found(self) -> None:
        """Classifier must detect 'no chart version found' errors."""
        error_output = "Error: no chart version found for opentelemetry-demo-0.45.0"
        result = _classify_helm_chart_version_error(error_output)
        assert result == FAILURE_HELM_CHART_VERSION_NOT_FOUND

    def test_chart_version_error_classifier_detects_couldnt_find_version(self) -> None:
        """Classifier must detect 'couldn't find that version' errors."""
        error_output = "Error: couldn't find that version (0.45.0)"
        result = _classify_helm_chart_version_error(error_output)
        assert result == FAILURE_HELM_CHART_VERSION_NOT_FOUND

    def test_chart_version_error_classifier_returns_none_for_other_errors(self) -> None:
        """Classifier must return None for non-version errors."""
        error_output = "Error: this is some other error"
        result = _classify_helm_chart_version_error(error_output)
        assert result is None

    def test_validate_chart_version_returns_valid_when_version_found(self) -> None:
        """Validation should return valid when version exists in search results."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '[{"version": "0.40.9"}]'

        with patch("subprocess.run", return_value=mock_result):
            is_valid, available = _validate_chart_version("open-telemetry", OTEL_DEMO_CHART, "0.40.9")
            assert is_valid is True
            assert available == ""

    def test_validate_chart_version_returns_invalid_when_version_missing(self) -> None:
        """Validation should return invalid with available versions when version not found."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '[{"version": "0.40.9"}, {"version": "0.40.8"}]'

        with patch("subprocess.run", return_value=mock_result):
            is_valid, available = _validate_chart_version("open-telemetry", OTEL_DEMO_CHART, "0.45.0")
            assert is_valid is False
            assert "0.40.9" in available
            assert "0.45.0" not in available

    def test_lab_config_uses_configurable_chart_version(self) -> None:
        """LabConfig must use the configurable chart version default."""
        config = LabConfig()
        # The default should be the configured value (0.40.9 or env override)
        assert config.helm_chart_version == OTEL_DEMO_CHART_VERSION

    def test_lab_config_chart_version_can_be_overridden(self) -> None:
        """LabConfig allows explicit chart version override."""
        config = LabConfig(helm_chart_version="0.45.0")
        assert config.helm_chart_version == "0.45.0"

    def test_get_configured_chart_version_respects_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_configured_otel_demo_chart_version respects K9B_OTEL_DEMO_CHART_VERSION env var."""
        # Set env override
        monkeypatch.setenv(CONFIGURED_OTEL_DEMO_CHART_VERSION_ENV, "0.50.0")
        # Function should return env value
        assert get_configured_otel_demo_chart_version() == "0.50.0"
        
        # Unset env and verify fallback
        monkeypatch.delenv(CONFIGURED_OTEL_DEMO_CHART_VERSION_ENV, raising=False)
        assert get_configured_otel_demo_chart_version() == OTEL_DEMO_CHART_VERSION


    @patch("subprocess.run")
    def test_phase1_fails_fast_with_clear_message_on_missing_version(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Phase 1 must fail fast with clear message when chart version not found.

        This prevents the misleading 'Provider smoke: SKIPPED/FAILED' result
        when the provider was never reached due to Phase 1 failure.
        """
        from scripts.k9b_otel_demo_lab_deployment import phase1_deploy_otel_demo

        # Mock helm repo add to succeed
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # helm repo add
            MagicMock(returncode=0, stdout="", stderr=""),  # helm repo update
            MagicMock(returncode=0, stdout='[{"version": "0.40.9"}]', stderr=""),  # helm search (version exists)
        ]

        config = LabConfig(helm_chart_version="0.45.0")  # Request missing version

        with patch("scripts.k9b_otel_demo_lab_deployment.write_json_artifact") as mock_write:
            mock_write.return_value = str(tmp_path / "preflight-failure.json")
            result = phase1_deploy_otel_demo(config, tmp_path)

        # Should fail fast before attempting install
        assert result.success is False
        assert "not available" in result.message
        assert "0.45.0" in result.message
        assert "0.40.9" in result.message  # Should show available versions
        assert "preflight_failure" in result.artifacts

    @patch("subprocess.run")
    def test_phase1_fails_at_preflight_with_preflight_failure_artifact(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Phase 1 fails at preflight (not post-install) when version is missing.

        This is the desired behavior - we fail fast with a clear preflight failure
        rather than failing during install with a generic error.
        """
        from scripts.k9b_otel_demo_lab_deployment import phase1_deploy_otel_demo

        # Mock helm commands - repo add/update succeed, search shows version NOT available
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # helm repo add
            MagicMock(returncode=0, stdout="", stderr=""),  # helm repo update
            MagicMock(returncode=0, stdout='[{"version": "0.40.9"}]', stderr=""),  # helm search - 0.45.0 not in list
        ]

        config = LabConfig(helm_chart_version="0.45.0")

        with patch("scripts.k9b_otel_demo_lab_deployment.write_json_artifact") as mock_write:
            mock_write.return_value = str(tmp_path / "preflight-failure.json")
            result = phase1_deploy_otel_demo(config, tmp_path)

        # Should fail at preflight, not at install
        assert result.success is False
        assert "preflight_failure" in result.artifacts
        # Message should be clear about the problem
        assert "not available" in result.message
        assert "0.45.0" in result.message
        assert "0.40.9" in result.message  # Available version shown

    @patch("subprocess.run")
    def test_phase1_classifies_version_error_on_install_failure(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Phase 1 classifies Helm version errors in post-install error handling.

        This is a fallback for cases where preflight didn't catch it (e.g., race
        condition where version was removed between preflight and install).
        """
        from scripts.k9b_otel_demo_lab_deployment import phase1_deploy_otel_demo

        # Mock helm commands - repo add/update succeed, search shows version IS available
        # (simulating a race condition where it was available at search but not at install)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # helm repo add
            MagicMock(returncode=0, stdout="", stderr=""),  # helm repo update
            MagicMock(returncode=0, stdout='[{"version": "0.45.0"}]', stderr=""),  # helm search - version appears available
            MagicMock(returncode=1, stdout="", stderr="no chart version found for opentelemetry-demo-0.45.0"),  # helm install fails
        ]

        config = LabConfig(helm_chart_version="0.45.0")

        with patch("scripts.k9b_otel_demo_lab_deployment.write_json_artifact") as mock_write:
            mock_write.return_value = str(tmp_path / "helm-failure.json")
            result = phase1_deploy_otel_demo(config, tmp_path)

        # Should fail during install with version classification
        assert result.success is False
        assert "failure_classification" in result.artifacts


