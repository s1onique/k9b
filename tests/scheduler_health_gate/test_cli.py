"""Tests for scheduler health gate CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.scheduler_health_gate.cli import create_arg_parser, main


class TestCreateArgParser:
    """Tests for argument parser creation."""

    def test_has_kubeconfig_arg(self) -> None:
        """Parser has --kubeconfig argument."""
        parser = create_arg_parser()
        args = parser.parse_args(["--kubeconfig", "/path/to/kubeconfig"])
        assert args.kubeconfig == "/path/to/kubeconfig"

    def test_has_namespace_arg(self) -> None:
        """Parser has --namespace argument."""
        parser = create_arg_parser()
        args = parser.parse_args(["--namespace", "test-ns"])
        assert args.namespace == "test-ns"

    def test_has_artifact_dir_arg(self) -> None:
        """Parser has --artifact-dir argument."""
        parser = create_arg_parser()
        args = parser.parse_args(["--artifact-dir", "/tmp/artifacts"])
        assert args.artifact_dir == "/tmp/artifacts"

    def test_has_json_flag(self) -> None:
        """Parser has --json flag."""
        parser = create_arg_parser()
        args = parser.parse_args(["--kubeconfig", "/fake", "--json"])
        assert args.json is True

    def test_defaults_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Parser uses environment variables for defaults."""
        monkeypatch.setenv("KUBECONFIG", "/env/kubeconfig")
        monkeypatch.setenv("NAMESPACE", "env-ns")
        monkeypatch.setenv("ARTIFACT_DIR", "/env/artifacts")
        
        parser = create_arg_parser()
        args = parser.parse_args([])
        
        assert args.kubeconfig == "/env/kubeconfig"
        assert args.namespace == "env-ns"
        assert args.artifact_dir == "/env/artifacts"


class TestMainExitCodes:
    """Tests for CLI exit codes."""

    def test_returns_1_when_kubeconfig_missing(self) -> None:
        """Returns exit code 1 when kubeconfig is not provided."""
        exit_code = main(["--kubeconfig", ""])
        assert exit_code == 1

    def test_returns_0_on_healthy_scheduler(
        self,
        monkeypatch: pytest.MonkeyPatch,
        healthy_deployment_response: dict[str, Any],
        healthy_pods_response: dict[str, Any],
        temp_artifact_dir: Path,
    ) -> None:
        """Returns exit code 0 when scheduler is healthy."""
        def mock_get_deployment(kubeconfig: str, namespace: str) -> dict[str, Any]:
            return healthy_deployment_response

        def mock_get_pods(kubeconfig: str, namespace: str, selector: str = "") -> dict[str, Any]:
            return healthy_pods_response

        def mock_get_events(kubeconfig: str, namespace: str, limit: int = 50) -> list[dict[str, Any]]:
            return []

        def mock_get_selector(kubeconfig: str, namespace: str, deployment_name: str) -> str:
            return "app.kubernetes.io/name=k9b-scheduler"

        def mock_collect_logs(
            kubeconfig: str, namespace: str, selector: str, tail_lines: int = 100
        ) -> dict[str, str]:
            return {}

        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_deployment_status",
            mock_get_deployment,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_pods",
            mock_get_pods,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_namespace_events",
            mock_get_events,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_pod_selector",
            mock_get_selector,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.collect_scheduler_logs",
            mock_collect_logs,
        )

        exit_code = main([
            "--kubeconfig", "/fake/kubeconfig",
            "--namespace", "test-ns",
            "--artifact-dir", str(temp_artifact_dir),
        ])
        
        assert exit_code == 0

    def test_returns_1_on_failed_scheduler(
        self,
        monkeypatch: pytest.MonkeyPatch,
        missing_deployment_response: dict[str, Any],
        temp_artifact_dir: Path,
    ) -> None:
        """Returns exit code 1 when scheduler is not found."""
        def mock_get_deployment(kubeconfig: str, namespace: str) -> dict[str, Any]:
            return missing_deployment_response

        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_deployment_status",
            mock_get_deployment,
        )

        exit_code = main([
            "--kubeconfig", "/fake/kubeconfig",
            "--namespace", "test-ns",
            "--artifact-dir", str(temp_artifact_dir),
        ])
        
        assert exit_code == 1


class TestMainJsonOutput:
    """Tests for JSON output."""

    def test_json_flag_does_not_crash(
        self,
        monkeypatch: pytest.MonkeyPatch,
        healthy_deployment_response: dict[str, Any],
        healthy_pods_response: dict[str, Any],
        temp_artifact_dir: Path,
    ) -> None:
        """JSON flag does not cause crashes and produces exit code 0."""
        def mock_get_deployment(kubeconfig: str, namespace: str) -> dict[str, Any]:
            return healthy_deployment_response

        def mock_get_pods(kubeconfig: str, namespace: str, selector: str = "") -> dict[str, Any]:
            return healthy_pods_response

        def mock_get_events(kubeconfig: str, namespace: str, limit: int = 50) -> list[dict[str, Any]]:
            return []

        def mock_get_selector(kubeconfig: str, namespace: str, deployment_name: str) -> str:
            return "app.kubernetes.io/name=k9b-scheduler"

        def mock_collect_logs(
            kubeconfig: str, namespace: str, selector: str, tail_lines: int = 100
        ) -> dict[str, str]:
            return {}

        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_deployment_status",
            mock_get_deployment,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_pods",
            mock_get_pods,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_namespace_events",
            mock_get_events,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.get_scheduler_pod_selector",
            mock_get_selector,
        )
        monkeypatch.setattr(
            "scripts.scheduler_health_gate.cli.collect_scheduler_logs",
            mock_collect_logs,
        )

        exit_code = main([
            "--kubeconfig", "/fake/kubeconfig",
            "--namespace", "test-ns",
            "--artifact-dir", str(temp_artifact_dir),
            "--json",
        ])
        
        assert exit_code == 0
