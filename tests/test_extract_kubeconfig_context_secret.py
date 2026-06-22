"""Integration tests for extract_kubeconfig_context_secret.py.

These tests use mocked subprocess calls to verify script behavior.
"""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from extract_kubeconfig_context_secret import run

# Minimal valid kubeconfig YAML for testing
VALID_KUBECONFIG_YAML = """apiVersion: v1
kind: Config
clusters:
- cluster:
    certificate-authority-data: LS0tLS1C==
    server: https://127.0.0.1:6443
  name: pve1-k3s-main
contexts:
- context:
    cluster: pve1-k3s-main
    user: admin
  name: pve1-k3s-main
current-context: pve1-k3s-main
users:
- name: admin
  user:
    token: eyJhbGc=
"""


def make_mock_subprocess(expected_context: str = "pve1-k3s-main") -> Callable[..., MagicMock]:
    """Create a mock subprocess.run that handles different kubectl commands."""
    def mock_run(*args: list[object], **kwargs: dict[str, object]) -> MagicMock:
        cmd = args[0] if args else kwargs.get("args", [])
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        
        # Check which kubectl command is being run
        if "get-contexts" in cmd:
            # Return just the context name, one per line
            result.stdout = f"{expected_context}\n"
        elif "current-context" in cmd:
            # Return just the current context
            result.stdout = f"{expected_context}\n"
        else:
            # Assume it's the config view command - return the kubeconfig YAML
            result.stdout = VALID_KUBECONFIG_YAML
        
        return result
    return mock_run


class TestRunFunction:
    """Integration tests for run() with mocked subprocess."""

    def test_missing_source_kubeconfig(self) -> None:
        """Should fail with useful error if source kubeconfig missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run(
                context="pve1-k3s-main",
                kubeconfig=Path(tmpdir) / "nonexistent",
                output=Path(tmpdir) / "output.b64",
                stdout=False,
                dry_run=False,
                force=False,
                allow_repo_output=True,
                kubectl_path="kubectl",
            )
            assert result == 1

    def test_dry_run_does_not_write(self) -> None:
        """Dry-run should not write output file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig_path = Path(tmpdir) / "config"
            kubeconfig_path.write_text(VALID_KUBECONFIG_YAML)
            output_path = Path(tmpdir) / "output.b64"

            with patch("extract_kubeconfig_context_secret.subprocess.run") as mock_run:
                mock_run.side_effect = make_mock_subprocess()

                result = run(
                    context="pve1-k3s-main",
                    kubeconfig=kubeconfig_path,
                    output=output_path,
                    stdout=False,
                    dry_run=True,
                    force=False,
                    allow_repo_output=True,
                    kubectl_path="kubectl",
                )

            assert result == 0
            assert not output_path.exists()

    def test_stdout_prints_only_base64(self) -> None:
        """Stdout mode should print only base64 to stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig_path = Path(tmpdir) / "config"
            kubeconfig_path.write_text(VALID_KUBECONFIG_YAML)
            output_path = Path(tmpdir) / "output.b64"

            with patch("extract_kubeconfig_context_secret.subprocess.run") as mock_run:
                mock_run.side_effect = make_mock_subprocess()

                result = run(
                    context="pve1-k3s-main",
                    kubeconfig=kubeconfig_path,
                    output=output_path,
                    stdout=True,
                    dry_run=False,
                    force=False,
                    allow_repo_output=True,
                    kubectl_path="kubectl",
                )

            assert result == 0
            # The output file should not have been created
            assert not output_path.exists()

    def test_repo_output_rejected_by_default(self) -> None:
        """Should reject output paths inside repo by default."""
        kubeconfig_path = Path.home() / ".kube" / "config"
        if not kubeconfig_path.exists():
            kubeconfig_path = Path("/tmp/fake.kubeconfig")
            kubeconfig_path.write_text(VALID_KUBECONFIG_YAML)

        # Use a path that would be inside the repo
        output_path = Path(__file__).parent.parent / "output.b64"
        try:
            result = run(
                context="pve1-k3s-main",
                kubeconfig=kubeconfig_path,
                output=output_path,
                stdout=False,
                dry_run=False,
                force=False,
                allow_repo_output=False,
                kubectl_path="kubectl",
            )
            assert result == 1
        finally:
            if output_path.exists():
                output_path.unlink()

    def test_status_text_no_raw_kubeconfig(self) -> None:
        """Status text should not contain raw kubeconfig content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig_path = Path(tmpdir) / "config"
            kubeconfig_path.write_text(VALID_KUBECONFIG_YAML)
            output_path = Path(tmpdir) / "output.b64"

            with patch("extract_kubeconfig_context_secret.subprocess.run") as mock_run:
                mock_run.side_effect = make_mock_subprocess()

                result = run(
                    context="pve1-k3s-main",
                    kubeconfig=kubeconfig_path,
                    output=output_path,
                    stdout=False,
                    dry_run=False,
                    force=False,
                    allow_repo_output=True,
                    kubectl_path="kubectl",
                )

            assert result == 0
            # The output file should exist and contain base64, not YAML
            content = output_path.read_text()
            assert "apiVersion" not in content
            assert "token:" not in content
            assert "certificate-authority-data:" not in content

    def test_wrong_context_validation_fails(self) -> None:
        """Validation should fail if extracted context doesn't match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig_path = Path(tmpdir) / "config"
            kubeconfig_path.write_text(VALID_KUBECONFIG_YAML)

            # Mock returns wrong context
            with patch("extract_kubeconfig_context_secret.subprocess.run") as mock_run:
                mock_run.side_effect = make_mock_subprocess(expected_context="wrong-context")

                result = run(
                    context="pve1-k3s-main",
                    kubeconfig=kubeconfig_path,
                    output=Path(tmpdir) / "output.b64",
                    stdout=False,
                    dry_run=False,
                    force=False,
                    allow_repo_output=True,
                    kubectl_path="kubectl",
                )

            assert result == 1

    def test_multiple_contexts_validation_fails(self) -> None:
        """Validation should fail if multiple contexts found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig_path = Path(tmpdir) / "config"
            kubeconfig_path.write_text(VALID_KUBECONFIG_YAML)

            def mock_multiple_contexts(
                *args: list[object], **kwargs: dict[str, object]
            ) -> MagicMock:
                cmd = args[0] if args else kwargs.get("args", [])
                result = MagicMock()
                result.returncode = 0
                result.stderr = ""
                
                if "get-contexts" in cmd:
                    # Return multiple contexts
                    result.stdout = "pve1-k3s-main\npve1-k3s-alt\n"
                elif "current-context" in cmd:
                    result.stdout = "pve1-k3s-main\n"
                else:
                    result.stdout = VALID_KUBECONFIG_YAML
                
                return result

            with patch("extract_kubeconfig_context_secret.subprocess.run") as mock_run:
                mock_run.side_effect = mock_multiple_contexts

                result = run(
                    context="pve1-k3s-main",
                    kubeconfig=kubeconfig_path,
                    output=Path(tmpdir) / "output.b64",
                    stdout=False,
                    dry_run=False,
                    force=False,
                    allow_repo_output=True,
                    kubectl_path="kubectl",
                )

            assert result == 1

    def test_missing_kubectl_fails(self) -> None:
        """Should fail with useful error if kubectl is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig_path = Path(tmpdir) / "config"
            kubeconfig_path.write_text(VALID_KUBECONFIG_YAML)

            # Mock kubectl not found
            with patch("extract_kubeconfig_context_secret.subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.returncode = 127
                mock_result.stdout = ""
                mock_result.stderr = "kubectl not found"
                mock_run.return_value = mock_result

                result = run(
                    context="pve1-k3s-main",
                    kubeconfig=kubeconfig_path,
                    output=Path(tmpdir) / "output.b64",
                    stdout=False,
                    dry_run=False,
                    force=False,
                    allow_repo_output=True,
                    kubectl_path="kubectl",
                )

            assert result == 1

    def test_kubectl_binary_missing_raises_filenotfound(self) -> None:
        """Should handle FileNotFoundError when kubectl binary is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig_path = Path(tmpdir) / "config"
            kubeconfig_path.write_text(VALID_KUBECONFIG_YAML)

            # Mock subprocess.run to raise FileNotFoundError
            with patch("extract_kubeconfig_context_secret.subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError("kubectl not found")

                result = run(
                    context="pve1-k3s-main",
                    kubeconfig=kubeconfig_path,
                    output=Path(tmpdir) / "output.b64",
                    stdout=False,
                    dry_run=False,
                    force=False,
                    allow_repo_output=True,
                    kubectl_path="kubectl",
                )

            assert result == 1

    def test_kubectl_nonzero_exit_fails(self) -> None:
        """Should fail if kubectl returns non-zero exit code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig_path = Path(tmpdir) / "config"
            kubeconfig_path.write_text(VALID_KUBECONFIG_YAML)

            # Mock kubectl failure
            with patch("extract_kubeconfig_context_secret.subprocess.run") as mock_run:
                mock_result = MagicMock()
                mock_result.returncode = 1
                mock_result.stdout = ""
                mock_result.stderr = "error: context not found"
                mock_run.return_value = mock_result

                result = run(
                    context="pve1-k3s-main",
                    kubeconfig=kubeconfig_path,
                    output=Path(tmpdir) / "output.b64",
                    stdout=False,
                    dry_run=False,
                    force=False,
                    allow_repo_output=True,
                    kubectl_path="kubectl",
                )

            assert result == 1

    def test_output_file_mode_0600(self) -> None:
        """Output file should have mode 0600."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig_path = Path(tmpdir) / "config"
            kubeconfig_path.write_text(VALID_KUBECONFIG_YAML)
            output_path = Path(tmpdir) / "output.b64"

            with patch("extract_kubeconfig_context_secret.subprocess.run") as mock_run:
                mock_run.side_effect = make_mock_subprocess()

                result = run(
                    context="pve1-k3s-main",
                    kubeconfig=kubeconfig_path,
                    output=output_path,
                    stdout=False,
                    dry_run=False,
                    force=False,
                    allow_repo_output=True,
                    kubectl_path="kubectl",
                )

            assert result == 0
            assert output_path.exists()
            mode = output_path.stat().st_mode & 0o777
            assert mode == 0o600

    def test_base64_is_one_line(self) -> None:
        """Base64 output should be a single line."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kubeconfig_path = Path(tmpdir) / "config"
            kubeconfig_path.write_text(VALID_KUBECONFIG_YAML)
            output_path = Path(tmpdir) / "output.b64"

            with patch("extract_kubeconfig_context_secret.subprocess.run") as mock_run:
                mock_run.side_effect = make_mock_subprocess()

                result = run(
                    context="pve1-k3s-main",
                    kubeconfig=kubeconfig_path,
                    output=output_path,
                    stdout=False,
                    dry_run=False,
                    force=False,
                    allow_repo_output=True,
                    kubectl_path="kubectl",
                )

            assert result == 0
            content = output_path.read_text()
            assert "\n" not in content
