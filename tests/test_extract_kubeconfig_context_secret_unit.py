"""Unit tests for extract_kubeconfig_context_secret.py - pure functions.

These tests verify the pure functions without mocking subprocess.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from extract_kubeconfig_context_secret import (
    DEFAULT_CONTEXT,
    build_extraction_argv,
    encode_base64_one_line,
    is_repo_path,
    resolve_default_output_path,
    validate_kubeconfig_content,
    write_output_file,
)

# =============================================================================
# Pure function tests
# =============================================================================

class TestBuildExtractionArgv:
    """Tests for build_extraction_argv."""

    def test_default_args(self) -> None:
        """Command should include --context with default context."""
        argv = build_extraction_argv(
            "kubectl", Path("/home/user/.kube/config"), "pve1-k3s-main"
        )
        assert argv[0] == "kubectl"
        assert "--context" in argv
        ctx_idx = argv.index("--context")
        assert argv[ctx_idx + 1] == "pve1-k3s-main"

    def test_includes_minify_flatten_raw(self) -> None:
        """Command should include --minify, --flatten, --raw."""
        argv = build_extraction_argv(
            "kubectl", Path("/home/user/.kube/config"), "pve1-k3s-main"
        )
        assert "--minify" in argv
        assert "--flatten" in argv
        assert "--raw" in argv

    def test_includes_kubeconfig_flag(self) -> None:
        """Command should include --kubeconfig with path."""
        kubeconfig = Path("/home/user/.kube/config")
        argv = build_extraction_argv("kubectl", kubeconfig, "pve1-k3s-main")
        assert "--kubeconfig" in argv
        ctx_idx = argv.index("--kubeconfig")
        assert argv[ctx_idx + 1] == str(kubeconfig)

    def test_includes_output_yaml(self) -> None:
        """Command should include -o yaml."""
        argv = build_extraction_argv(
            "kubectl", Path("/home/user/.kube/config"), "pve1-k3s-main"
        )
        assert "-o" in argv
        idx = argv.index("-o")
        assert argv[idx + 1] == "yaml"

    def test_uses_list_not_string(self) -> None:
        """Command should return a list, not a string."""
        argv = build_extraction_argv(
            "kubectl", Path("/home/user/.kube/config"), "pve1-k3s-main"
        )
        assert isinstance(argv, list)
        assert not isinstance(argv, str)


class TestEncodeBase64OneLine:
    """Tests for encode_base64_one_line."""

    def test_output_is_one_line(self) -> None:
        """Encoded output should be a single line with no newlines."""
        data = b"test data with some content"
        result = encode_base64_one_line(data)
        assert "\n" not in result
        assert result.count("\n") == 0

    def test_output_is_ascii(self) -> None:
        """Encoded output should be ASCII-decodable."""
        data = b"test data"
        result = encode_base64_one_line(data)
        assert result.encode("ascii")


class TestResolveDefaultOutputPath:
    """Tests for resolve_default_output_path."""

    def test_context_in_filename(self) -> None:
        """Output path should include context name."""
        path = resolve_default_output_path("pve1-k3s-main")
        assert "pve1-k3s-main" in str(path)

    def test_b64_extension(self) -> None:
        """Output path should have .b64 extension."""
        path = resolve_default_output_path("pve1-k3s-main")
        assert str(path).endswith(".b64")

    def test_under_tmp(self) -> None:
        """Default output should be under /tmp."""
        path = resolve_default_output_path("pve1-k3s-main")
        assert str(path).startswith("/tmp/")

    def test_default_context_is_pve1_k3s_main(self) -> None:
        """DEFAULT_CONTEXT should be pve1-k3s-main."""
        assert DEFAULT_CONTEXT == "pve1-k3s-main"


class TestIsRepoPath:
    """Tests for is_repo_path."""

    def test_tmp_is_not_repo(self) -> None:
        """Paths under /tmp should not be detected as repo paths."""
        assert is_repo_path(Path("/tmp/kubeconfig.b64")) is False

    def test_kubeconfig_is_not_repo(self) -> None:
        """Paths with .kube/config should not be detected as repo paths."""
        assert is_repo_path(Path.home() / ".kube" / "config") is False


class TestValidateKubeconfigContent:
    """Tests for validate_kubeconfig_content."""

    def test_valid_kubeconfig(self) -> None:
        """Valid kubeconfig with all markers should pass."""
        content = """apiVersion: v1
kind: Config
clusters:
- cluster:
    certificate-authority-data: LS0tLS1C...
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
    token: eyJhbGc...
"""
        assert validate_kubeconfig_content(content) is True

    def test_missing_apiVersion(self) -> None:
        """Content missing apiVersion should fail."""
        content = """kind: Config
clusters:
contexts:
users:
"""
        assert validate_kubeconfig_content(content) is False

    def test_missing_kind(self) -> None:
        """Content missing kind should fail."""
        content = """apiVersion: v1
clusters:
contexts:
users:
"""
        assert validate_kubeconfig_content(content) is False

    def test_missing_clusters(self) -> None:
        """Content missing clusters should fail."""
        content = """apiVersion: v1
kind: Config
contexts:
users:
"""
        assert validate_kubeconfig_content(content) is False

    def test_missing_contexts(self) -> None:
        """Content missing contexts should fail."""
        content = """apiVersion: v1
kind: Config
clusters:
users:
"""
        assert validate_kubeconfig_content(content) is False

    def test_missing_users(self) -> None:
        """Content missing users should fail."""
        content = """apiVersion: v1
kind: Config
clusters:
contexts:
"""
        assert validate_kubeconfig_content(content) is False


class TestWriteOutputFile:
    """Tests for write_output_file."""

    def test_creates_file(self) -> None:
        """Should create the output file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.b64"
            result = write_output_file(path, "dGVzdA==", force=False)
            assert result == ""
            assert path.exists()

    def test_sets_0600_permissions(self) -> None:
        """Output file should have mode 0600."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.b64"
            write_output_file(path, "dGVzdA==", force=False)
            mode = path.stat().st_mode & 0o777
            assert mode == 0o600

    def test_refuses_overwrite_without_force(self) -> None:
        """Should refuse to overwrite existing file without --force."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.b64"
            path.write_text("existing")
            result = write_output_file(path, "new", force=False)
            assert "exists" in result.lower()
            assert path.read_text() == "existing"

    def test_allows_overwrite_with_force(self) -> None:
        """Should overwrite existing file with --force."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.b64"
            path.write_text("existing")
            result = write_output_file(path, "new", force=True)
            assert result == ""
            assert path.read_text() == "new"


class TestArgumentParser:
    """Tests for CLI argument parsing."""

    def test_default_context_is_pve1_k3s_main(self) -> None:
        """Default context should be pve1-k3s-main."""
        from extract_kubeconfig_context_secret import create_arg_parser
        parser = create_arg_parser()
        args = parser.parse_args([])
        assert args.context == "pve1-k3s-main"

    def test_custom_context(self) -> None:
        """Should accept custom context."""
        from extract_kubeconfig_context_secret import create_arg_parser
        parser = create_arg_parser()
        args = parser.parse_args(["--context", "custom-context"])
        assert args.context == "custom-context"

    def test_stdout_flag(self) -> None:
        """Should accept --stdout flag."""
        from extract_kubeconfig_context_secret import create_arg_parser
        parser = create_arg_parser()
        args = parser.parse_args(["--stdout"])
        assert args.stdout is True

    def test_dry_run_flag(self) -> None:
        """Should accept --dry-run flag."""
        from extract_kubeconfig_context_secret import create_arg_parser
        parser = create_arg_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_force_flag(self) -> None:
        """Should accept --force flag."""
        from extract_kubeconfig_context_secret import create_arg_parser
        parser = create_arg_parser()
        args = parser.parse_args(["--force"])
        assert args.force is True

    def test_allow_repo_output_flag(self) -> None:
        """Should accept --allow-repo-output flag."""
        from extract_kubeconfig_context_secret import create_arg_parser
        parser = create_arg_parser()
        args = parser.parse_args(["--allow-repo-output"])
        assert args.allow_repo_output is True
