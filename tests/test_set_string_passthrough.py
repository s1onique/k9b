"""Regression tests: --set-string must be accepted by the CLI wrapper and passed to Helm.

These tests prevent the regression where GitHub Actions workflow calls passed
--set-string provider overrides through the baseline wrapper, but argparse
rejected them as unrecognized arguments.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from scripts.k9b_lab_helm import install_helm, render_manifest


class TestSetStringPassthrough:
    """Regression tests: --set-string must be accepted by the CLI wrapper and passed to Helm."""

    def test_cli_wrapper_accepts_repeated_set_string_flag(self) -> None:
        """CLI wrapper argparse must accept --set-string without raising."""
        cli = Path(__file__).parent.parent / "scripts" / "ensure_k9b_lab_baseline.py"
        # Smoke test: argparse must not reject --set-string before touching the cluster
        result = subprocess.run(
            [
                ".venv/bin/python", str(cli),
                "--lab-name", "test",
                "--chart-path", "./charts/k9b",
                "--artifact-dir", "/tmp/k9b-test-artifacts",
                "--kubeconfig", "/dev/null",
                "--set-string", "diagnosisProvider.enabled=true",
                "--set-string", "diagnosisProvider.provider=openai_compatible",
                "--set-string", "diagnosisProvider.baseUrl=https://example.invalid/v1",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # ArgumentError exit code is 2
        assert result.returncode != 2, \
            f"CLI wrapper must not reject --set-string as unrecognized. stderr: {result.stderr}"

    def test_render_manifest_passes_set_string_values_to_helm_template(self) -> None:
        """render_manifest must emit --set-string in the helm template argv."""
        captured_cmds: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            captured_cmds.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = "apiVersion: v1\nkind: Pod\n"
            result.stderr = ""
            return result

        chart = Path(__file__).parent.parent / "charts" / "k9b"
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("subprocess.run", side_effect=mock_run):
                render_manifest(
                    chart_path=str(chart),
                    values_path=None,
                    namespace="k9b",
                    release_name="k9b",
                    artifact_dir=Path(tmpdir),
                    set_string_values=[
                        "diagnosisProvider.enabled=true",
                        "diagnosisProvider.provider=openai_compatible",
                        "diagnosisProvider.baseUrl=https://example.invalid/v1",
                    ],
                )

        assert len(captured_cmds) == 1, f"Expected 1 helm call, got {len(captured_cmds)}"
        helm_cmd = captured_cmds[0]
        assert "--set-string" in helm_cmd, f"--set-string missing from helm argv: {helm_cmd}"
        # Verify each value appears as the arg immediately following a --set-string entry
        for val in [
            "diagnosisProvider.enabled=true",
            "diagnosisProvider.provider=openai_compatible",
            "diagnosisProvider.baseUrl=https://example.invalid/v1",
        ]:
            idx = helm_cmd.index(val)
            assert helm_cmd[idx - 1] == "--set-string", \
                f"Expected {val} to follow --set-string, but got: {helm_cmd[idx - 1]}"

    def test_install_helm_passes_set_string_values_to_helm_upgrade(self) -> None:
        """install_helm must emit --set-string in the helm upgrade argv."""
        captured_cmds: list[list[str]] = []

        def mock_run(cmd: list[str], **kwargs: Any) -> MagicMock:
            captured_cmds.append(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        chart = Path(__file__).parent.parent / "charts" / "k9b"
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("subprocess.run", side_effect=mock_run):
                install_helm(
                    kubeconfig="/dev/null",
                    chart_path=str(chart),
                    values_path=None,
                    namespace="k9b",
                    release_name="k9b",
                    artifact_dir=Path(tmpdir),
                    set_string_values=[
                        "diagnosisProvider.existingSecret=k9b-diagnosis-credentials",
                        "diagnosisProvider.apiKeyKey=K9B_DIAGNOSIS_API_KEY",
                    ],
                )

        assert len(captured_cmds) == 1, f"Expected 1 helm call, got {len(captured_cmds)}"
        helm_cmd = captured_cmds[0]
        assert "--set-string" in helm_cmd, f"--set-string missing from helm argv: {helm_cmd}"
        idx = helm_cmd.index("--set-string")
        assert helm_cmd[idx + 1] == "diagnosisProvider.existingSecret=k9b-diagnosis-credentials", \
            f"First --set-string value mismatch: {helm_cmd}"

    def test_render_and_install_both_support_set_string(self) -> None:
        """Both render_manifest and install_helm accept set_string_values parameter."""
        import inspect

        render_sig = inspect.signature(render_manifest)
        install_sig = inspect.signature(install_helm)

        assert "set_string_values" in render_sig.parameters, \
            "render_manifest must have set_string_values parameter"
        assert "set_string_values" in install_sig.parameters, \
            "install_helm must have set_string_values parameter"
