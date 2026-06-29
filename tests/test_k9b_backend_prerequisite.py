"""Tests for k9b backend prerequisite checks (Phase P0)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.k9b_otel_demo_lab_constants import (
    FAILURE_BACKEND_DEPLOYMENT_MISSING,
    FAILURE_BACKEND_NAMESPACE_MISSING,
    FAILURE_BACKEND_ROLLOUT_NOT_READY,
    FAILURE_BACKEND_SERVICE_MISSING,
    K9B_BACKEND_PORT,
    K9B_BACKEND_SERVICE,
    K9B_NAMESPACE,
)
from scripts.k9b_otel_demo_lab_types import LabConfig


class TestBackendPrerequisiteFailureClasses:
    """Test backend prerequisite failure class constants."""

    def test_backend_namespace_missing_defined(self) -> None:
        """FAILURE_BACKEND_NAMESPACE_MISSING constant must be defined."""
        assert FAILURE_BACKEND_NAMESPACE_MISSING == "backend_namespace_missing"

    def test_backend_service_missing_defined(self) -> None:
        """FAILURE_BACKEND_SERVICE_MISSING constant must be defined."""
        assert FAILURE_BACKEND_SERVICE_MISSING == "backend_service_missing"

    def test_backend_deployment_missing_defined(self) -> None:
        """FAILURE_BACKEND_DEPLOYMENT_MISSING constant must be defined."""
        assert FAILURE_BACKEND_DEPLOYMENT_MISSING == "backend_deployment_missing"

    def test_backend_rollout_not_ready_defined(self) -> None:
        """FAILURE_BACKEND_ROLLOUT_NOT_READY constant must be defined."""
        assert FAILURE_BACKEND_ROLLOUT_NOT_READY == "backend_rollout_not_ready"


class TestPhase0K9bBackendPrerequisite:
    """Test Phase P0 k9b backend prerequisite checks."""

    @patch("subprocess.run")
    def test_phase_p0_fails_fast_when_namespace_missing(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Phase P0 must fail with backend_namespace_missing when namespace doesn't exist."""
        from scripts.k9b_otel_demo_lab_provider_health import phase_p0_k9b_backend_prerequisite

        mock_run.return_value = MagicMock(returncode=1, stderr='Error from server (NotFound): namespaces "k9b" not found')

        config = LabConfig(kubeconfig="/fake/kubeconfig")
        result = phase_p0_k9b_backend_prerequisite(config, tmp_path)

        assert result.success is False
        assert result.phase == "p0-k9b-backend-prerequisite"
        assert result.message == "k9b namespace 'k9b' does not exist"
        assert "prerequisite_failure" in result.artifacts

    @patch("subprocess.run")
    def test_phase_p0_fails_fast_when_service_missing(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Phase P0 must fail with backend_service_missing when service doesn't exist."""
        from scripts.k9b_otel_demo_lab_provider_health import phase_p0_k9b_backend_prerequisite

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=1, stderr='Error from server (NotFound): services "k9b-backend" not found'),
        ]

        config = LabConfig(kubeconfig="/fake/kubeconfig")
        result = phase_p0_k9b_backend_prerequisite(config, tmp_path)

        assert result.success is False
        assert result.phase == "p0-k9b-backend-prerequisite"
        assert "service" in result.message and "k9b-backend" in result.message
        assert "prerequisite_failure" in result.artifacts

    @patch("subprocess.run")
    def test_phase_p0_fails_fast_when_deployment_missing(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Phase P0 must fail with backend_deployment_missing when deployment doesn't exist."""
        from scripts.k9b_otel_demo_lab_provider_health import phase_p0_k9b_backend_prerequisite

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=1, stderr='Error from server (NotFound): deployments "k9b-backend" not found'),
        ]

        config = LabConfig(kubeconfig="/fake/kubeconfig")
        result = phase_p0_k9b_backend_prerequisite(config, tmp_path)

        assert result.success is False
        assert result.phase == "p0-k9b-backend-prerequisite"
        assert "deployment" in result.message and "k9b-backend" in result.message
        assert "prerequisite_failure" in result.artifacts

    @patch("subprocess.run")
    def test_phase_p0_fails_fast_when_rollout_not_ready(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Phase P0 must fail with backend_rollout_not_ready when deployment not ready."""
        from scripts.k9b_otel_demo_lab_provider_health import phase_p0_k9b_backend_prerequisite

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=1, stdout="", stderr='error: deployment "k9b-backend" exceeded its progress deadline'),
        ]

        config = LabConfig(kubeconfig="/fake/kubeconfig")
        result = phase_p0_k9b_backend_prerequisite(config, tmp_path)

        assert result.success is False
        assert result.phase == "p0-k9b-backend-prerequisite"
        assert "not ready" in result.message.lower() or "progress deadline" in result.message.lower()
        assert "prerequisite_failure" in result.artifacts

    @patch("subprocess.run")
    def test_phase_p0_passes_when_all_prerequisites_exist(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Phase P0 must pass when namespace, service, and deployment all exist and are ready."""
        from scripts.k9b_otel_demo_lab_provider_health import phase_p0_k9b_backend_prerequisite

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout='deployment "k9b-backend" successfully rolled out'),
        ]

        config = LabConfig(kubeconfig="/fake/kubeconfig")
        result = phase_p0_k9b_backend_prerequisite(config, tmp_path)

        assert result.success is True
        assert result.phase == "p0-k9b-backend-prerequisite"
        assert "prerequisite_pass" in result.artifacts

    @patch("subprocess.run")
    def test_phase_p0_writes_target_info_in_failure_artifact(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Phase P0 prerequisite failure artifact includes target info."""
        import json

        from scripts.k9b_otel_demo_lab_provider_health import phase_p0_k9b_backend_prerequisite

        mock_run.return_value = MagicMock(returncode=1, stderr='namespaces "k9b" not found')

        config = LabConfig(kubeconfig="/fake/kubeconfig")
        result = phase_p0_k9b_backend_prerequisite(config, tmp_path)

        assert result.success is False
        failure_artifact_path = result.artifacts.get("prerequisite_failure")
        assert failure_artifact_path is not None

        failure_data = json.loads(Path(failure_artifact_path).read_text())

        assert failure_data["target"]["namespace"] == K9B_NAMESPACE
        assert failure_data["target"]["service"] == K9B_BACKEND_SERVICE
        assert failure_data["target"]["port"] == K9B_BACKEND_PORT
