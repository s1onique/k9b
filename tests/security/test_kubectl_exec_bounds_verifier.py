"""Tests for kubectl exec bounds verifier - regression tests for false negatives."""

from __future__ import annotations

import sys
from pathlib import Path
from textwrap import dedent

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import verify_kubectl_exec_bounds as verify_module  # noqa: E402

LOGS_UNSAFE_PATTERNS = verify_module.LOGS_UNSAFE_PATTERNS
is_kubectl_subprocess = verify_module.is_kubectl_subprocess
scan_file = verify_module.scan_file
should_skip_warning = verify_module.should_skip_warning


class TestIsKubectlSubprocess:
    """Tests for is_kubectl_subprocess() - verifies correct classification."""

    def test_kubectl_subprocess_run_is_detected(self) -> None:
        """kubectl subprocess.run with capture_output=True should be detected.
        
        This is the critical regression test: cmd = ["kubectl", ...] followed by
        subprocess.run(capture_output=True) must be classified as kubectl.
        """
        prev_lines = [
            'cmd = ["kubectl", "get", "pods"]',
        ]
        line = 'result = subprocess.run(cmd, capture_output=True)'
        
        assert is_kubectl_subprocess(line, prev_lines) is True

    def test_kubectl_with_capture_output_true_is_detected(self) -> None:
        """kubectl with capture_output=True should be detected."""
        prev_lines = [
            'cmd = ["kubectl", "get", "namespace", "kube-system", "-o", "json"]',
        ]
        line = 'output = subprocess.run(cmd, capture_output=True, text=True).stdout'
        
        assert is_kubectl_subprocess(line, prev_lines) is True

    def test_helm_subprocess_is_not_kubectl(self) -> None:
        """helm subprocess should NOT be classified as kubectl."""
        prev_lines = [
            'cmd = ["helm", "list", "-n", namespace]',
        ]
        line = 'result = subprocess.run(cmd, capture_output=True, text=True)'
        
        assert is_kubectl_subprocess(line, prev_lines) is False

    def test_build_script_subprocess_is_not_kubectl(self) -> None:
        """build script subprocess should NOT be classified as kubectl."""
        prev_lines = [
            'result = subprocess.run(["pack", "build", image], capture_output=True)',
        ]
        line = ''
        
        assert is_kubectl_subprocess(line, prev_lines) is False

    def test_command_runner_is_not_kubectl(self) -> None:
        """CommandRunner subprocess should NOT be classified as kubectl."""
        prev_lines = [
            'def _run_helm(cmd):',
            '    return runner(cmd)',
        ]
        line = 'result = runner(["helm", "template", chart])'
        
        assert is_kubectl_subprocess(line, prev_lines) is False

    def test_generic_subprocess_run_without_kubectl_is_not_kubectl(self) -> None:
        """Generic subprocess.run without kubectl indicator should NOT be classified as kubectl."""
        prev_lines = [
            'result = subprocess.run(["ls", "-la"], capture_output=True)',
        ]
        line = ''
        
        assert is_kubectl_subprocess(line, prev_lines) is False

    def test_kubectl_logs_subprocess_is_detected(self) -> None:
        """kubectl logs subprocess.run should be detected."""
        prev_lines = [
            'cmd = ["kubectl", "logs", "pod-xyz", "-n", "default"]',
        ]
        line = 'result = subprocess.run(cmd, capture_output=True, text=True)'
        
        assert is_kubectl_subprocess(line, prev_lines) is True


class TestShouldSkipWarning:
    """Tests for should_skip_warning() - verifies warning suppression logic."""

    def test_kubectl_subprocess_does_not_skip_warning(self) -> None:
        """kubectl subprocess with text=True should NOT skip warning."""
        prev_lines = [
            'cmd = ["kubectl", "get", "pods"]',
        ]
        line = 'output = subprocess.run(cmd, text=True).stdout'
        
        assert should_skip_warning(line, prev_lines) is False

    def test_external_analysis_skips_warning(self) -> None:
        """external_analysis paths should skip warnings."""
        prev_lines = [
            'def discover(self, context, external_analysis):',
            '    cmd = ["kubectl", "get", "pods"]',
        ]
        line = 'output = subprocess.run(cmd, text=True).stdout'
        
        assert should_skip_warning(line, prev_lines) is True

    def test_helm_skips_warning(self) -> None:
        """helm subprocess should skip warnings."""
        prev_lines = [
            'cmd = ["helm", "list"]',
        ]
        line = 'output = subprocess.run(cmd, text=True).stdout'
        
        assert should_skip_warning(line, prev_lines) is True


class TestLogsPatternDetection:
    """Tests for kubectl logs without bounds detection."""

    def test_logs_without_limit_bytes_fails(self) -> None:
        """kubectl logs without --limit-bytes should be flagged."""
        # Check that the pattern is defined correctly
        pattern_info = LOGS_UNSAFE_PATTERNS["kubectl logs"]
        assert "--limit-bytes" in pattern_info["require_flags"]

    def test_logs_without_time_bound_fails(self) -> None:
        """kubectl logs without --tail/--since/--since-time should be flagged."""
        pattern_info = LOGS_UNSAFE_PATTERNS["kubectl logs"]
        require_one_of = pattern_info["require_one_of"][0]
        assert "--tail" in require_one_of
        assert "--since" in require_one_of
        assert "--since-time" in require_one_of


class TestVerifierRegressionScenarios:
    """End-to-end regression tests for the verifier."""

    def test_kubectl_subprocess_run_false_negative_fixed(self, tmp_path: Path) -> None:
        """Regression test: kubectl subprocess.run was misclassified due to subprocess.run indicator.
        
        Before the fix, this code would NOT be flagged because "subprocess.run(" 
        was checked BEFORE "kubectl", causing false negatives.
        
        After the fix, this SHOULD be flagged.
        """
        # Create a test file with the problematic pattern
        test_file = tmp_path / "test_kubectl_subprocess.py"
        test_file.write_text(dedent("""
            import subprocess
            
            def get_pods():
                cmd = ["kubectl", "get", "pods", "-o", "json"]
                result = subprocess.run(cmd, capture_output=True)
                return result.stdout
        """))
        
        findings = scan_file(test_file)
        
        # Should find the capture_output=True violation
        errors = [f for f in findings if f["severity"] == "error"]
        assert len(errors) >= 1, "Should flag kubectl subprocess.run with capture_output=True"
        
        # Verify it's the capture_output=True pattern
        capture_errors = [f for f in errors if f["pattern"] == "capture_output=True"]
        assert len(capture_errors) >= 1

    def test_helm_subprocess_not_flagged(self, tmp_path: Path) -> None:
        """Regression test: helm subprocess should NOT be flagged."""
        test_file = tmp_path / "test_helm.py"
        test_file.write_text(dedent("""
            import subprocess
            
            def run_helm():
                cmd = ["helm", "list", "-n", "default"]
                result = subprocess.run(cmd, capture_output=True, text=True)
                return result.stdout
        """))
        
        findings = scan_file(test_file)
        
        # Should NOT find any errors for helm
        errors = [f for f in findings if f["severity"] == "error"]
        assert len(errors) == 0, "helm subprocess should not be flagged"

    def test_kubectl_logs_without_bounds_flagged(self, tmp_path: Path) -> None:
        """Regression test: kubectl logs without bounds should be flagged."""
        test_file = tmp_path / "test_logs.py"
        test_file.write_text(dedent("""
            import subprocess
            
            def get_logs():
                cmd = ["kubectl", "logs", "pod-xyz", "-n", "default"]
                result = subprocess.run(cmd, capture_output=True)
                return result.stdout
        """))
        
        findings = scan_file(test_file)
        
        # Should find both the capture_output violation and the logs bounds violation
        errors = [f for f in findings if f["severity"] == "error"]
        assert len(errors) >= 1, "Should flag kubectl logs without bounds"
