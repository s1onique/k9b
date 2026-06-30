"""Tests for Helm chart version handling."""
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
from scripts.k9b_otel_demo_lab_deployment_helm import _classify_helm_chart_version_error, _validate_chart_version
from scripts.k9b_otel_demo_lab_types import LabConfig


class TestHelmChartVersionHandling:
    """Regression tests for Helm chart version handling."""

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
        assert config.helm_chart_version == OTEL_DEMO_CHART_VERSION

    def test_lab_config_chart_version_can_be_overridden(self) -> None:
        """LabConfig allows explicit chart version override."""
        config = LabConfig(helm_chart_version="0.45.0")
        assert config.helm_chart_version == "0.45.0"

    def test_get_configured_chart_version_respects_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_configured_otel_demo_chart_version respects env var."""
        monkeypatch.setenv(CONFIGURED_OTEL_DEMO_CHART_VERSION_ENV, "0.50.0")
        assert get_configured_otel_demo_chart_version() == "0.50.0"
        monkeypatch.delenv(CONFIGURED_OTEL_DEMO_CHART_VERSION_ENV, raising=False)
        assert get_configured_otel_demo_chart_version() == OTEL_DEMO_CHART_VERSION

    @patch("subprocess.run")
    def test_phase1_fails_fast_with_clear_message_on_missing_version(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Phase 1 must fail fast with clear message when chart version not found."""
        from scripts.k9b_otel_demo_lab_deployment import phase1_deploy_otel_demo

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout='[{"version": "0.40.9"}]', stderr=""),
        ]

        config = LabConfig(helm_chart_version="0.45.0")

        with patch("scripts.k9b_otel_demo_lab_deployment.write_json_artifact") as mock_write:
            mock_write.return_value = str(tmp_path / "preflight-failure.json")
            result = phase1_deploy_otel_demo(config, tmp_path)

        assert result.success is False
        assert "not available" in result.message
        assert "0.45.0" in result.message
        assert "0.40.9" in result.message
        assert "preflight_failure" in result.artifacts

    @patch("subprocess.run")
    def test_phase1_fails_at_preflight_when_version_missing(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Phase 1 fails at preflight when version is missing."""
        from scripts.k9b_otel_demo_lab_deployment import phase1_deploy_otel_demo

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout='[{"version": "0.40.9"}]', stderr=""),
        ]

        config = LabConfig(helm_chart_version="0.45.0")

        with patch("scripts.k9b_otel_demo_lab_deployment.write_json_artifact") as mock_write:
            mock_write.return_value = str(tmp_path / "preflight-failure.json")
            result = phase1_deploy_otel_demo(config, tmp_path)

        assert result.success is False
        assert "preflight_failure" in result.artifacts
        assert "not available" in result.message

    @patch("subprocess.run")
    def test_phase1_classifies_version_error_on_install_failure(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Phase 1 classifies Helm version errors in post-install error handling."""
        from scripts.k9b_otel_demo_lab_deployment import phase1_deploy_otel_demo

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=0, stdout='[{"version": "0.45.0"}]', stderr=""),
            MagicMock(returncode=1, stdout="", stderr="no chart version found for opentelemetry-demo-0.45.0"),
        ]

        config = LabConfig(helm_chart_version="0.45.0")

        with patch("scripts.k9b_otel_demo_lab_deployment.write_json_artifact") as mock_write:
            mock_write.return_value = str(tmp_path / "helm-failure.json")
            result = phase1_deploy_otel_demo(config, tmp_path)

        assert result.success is False
        assert "failure_classification" in result.artifacts
