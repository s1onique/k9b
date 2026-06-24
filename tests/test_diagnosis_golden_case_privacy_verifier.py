#!/usr/bin/env python3
"""Tests for verify_diagnosis_golden_case_privacy module."""
from __future__ import annotations

import sys
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from verify_diagnosis_golden_case_privacy import (
    _ALLOWED_PLACEHOLDERS,
    _FORBIDDEN_PATTERNS,
    PrivacyFinding,
    _is_placeholder_only_line,
    scan_directory,
    scan_file,
    verify_golden_case_privacy,
)

# =============================================================================
# Helper Fixtures
# =============================================================================

@pytest.fixture
def temp_case_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test fixtures."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def temp_json_file(temp_case_dir: Path) -> Path:
    """Create a temporary JSON file."""
    file_path = temp_case_dir / "test.json"
    return file_path


@pytest.fixture
def temp_txt_file(temp_case_dir: Path) -> Path:
    """Create a temporary text file."""
    file_path = temp_case_dir / "test.txt"
    return file_path


# =============================================================================
# Tests for RFC1918 Private IP Detection
# =============================================================================

class TestRfc1918PrivateIpDetection:
    """Tests for RFC1918 private IP detection."""

    def test_detects_10_x_x_x(self, temp_json_file: Path) -> None:
        """Should detect 10.x.x.x private IPs."""
        temp_json_file.write_text('{"ip": "10.255.100.50"}', encoding="utf-8")
        findings = scan_file(temp_json_file)
        assert len(findings) == 1
        assert findings[0].pattern_class == "rfc1918_10"

    def test_detects_172_16_31_x_x(self, temp_json_file: Path) -> None:
        """Should detect 172.16-31.x.x private IPs."""
        temp_json_file.write_text('{"ip": "172.20.50.100"}', encoding="utf-8")
        findings = scan_file(temp_json_file)
        assert len(findings) == 1
        assert findings[0].pattern_class == "rfc1918_172"

    def test_detects_192_168_x_x(self, temp_json_file: Path) -> None:
        """Should detect 192.168.x.x private IPs."""
        temp_json_file.write_text('{"ip": "192.168.1.100"}', encoding="utf-8")
        findings = scan_file(temp_json_file)
        assert len(findings) == 1
        assert findings[0].pattern_class == "rfc1918_192"

    def test_allows_placeholder(self, temp_json_file: Path) -> None:
        """Should allow <PRIVATE_IP> placeholder."""
        temp_json_file.write_text('{"ip": "<PRIVATE_IP>"}', encoding="utf-8")
        findings = scan_file(temp_json_file)
        assert len(findings) == 0


# =============================================================================
# Tests for K8s Node Name Detection
# =============================================================================

class TestK8sNodeNameDetection:
    """Tests for internal K8s node name detection."""

    def test_detects_k3s_worker(self, temp_json_file: Path) -> None:
        """Should detect k3s-worker-* node names."""
        temp_json_file.write_text('{"node": "k3s-worker-01"}', encoding="utf-8")
        findings = scan_file(temp_json_file)
        assert len(findings) == 1
        assert findings[0].pattern_class == "k8s_node_worker"

    def test_detects_k3s_master(self, temp_json_file: Path) -> None:
        """Should detect k3s-master-* node names."""
        temp_json_file.write_text('{"node": "k3s-master-02"}', encoding="utf-8")
        findings = scan_file(temp_json_file)
        assert len(findings) == 1
        assert findings[0].pattern_class == "k8s_node_master"

    def test_allows_k8s_node_placeholder(self, temp_json_file: Path) -> None:
        """Should allow <K8S_NODE> placeholder."""
        temp_json_file.write_text('{"node": "<K8S_NODE>"}', encoding="utf-8")
        findings = scan_file(temp_json_file)
        assert len(findings) == 0


# =============================================================================
# Tests for Internal Namespace Detection
# =============================================================================

class TestInternalNamespaceDetection:
    """Tests for internal namespace detection."""

    def test_detects_k9b_cnpg_lab_namespace(self, temp_json_file: Path) -> None:
        """Should detect k9b-cnpg-lab-[0-9]+ namespace names."""
        temp_json_file.write_text('{"namespace": "k9b-cnpg-lab-12345678"}', encoding="utf-8")
        findings = scan_file(temp_json_file)
        assert len(findings) == 1
        assert findings[0].pattern_class == "internal_namespace"

    def test_allows_namespace_placeholder(self, temp_json_file: Path) -> None:
        """Should allow <LAB_NAMESPACE> placeholder."""
        temp_json_file.write_text('{"namespace": "<LAB_NAMESPACE>"}', encoding="utf-8")
        findings = scan_file(temp_json_file)
        assert len(findings) == 0


# =============================================================================
# Tests for Internal Domain Detection
# =============================================================================

class TestInternalDomainDetection:
    """Tests for internal domain detection."""

    def test_detects_harbor_spbnix_local(self, temp_json_file: Path) -> None:
        """Should detect harbor-*.spbnix.local domains.
        
        Note: harbor-prod.spbnix.local matches both harbor-*.spbnix.local
        and *.spbnix.local patterns, so we check for >= 1 finding.
        """
        temp_json_file.write_text('{"registry": "harbor-prod.spbnix.local"}', encoding="utf-8")
        findings = scan_file(temp_json_file)
        assert len(findings) >= 1
        # At least one should be the harbor pattern
        pattern_classes = {f.pattern_class for f in findings}
        assert "internal_domain_harbor" in pattern_classes

    def test_detects_registry_spbnix_com(self, temp_json_file: Path) -> None:
        """Should detect registry.spbnix.com domain."""
        temp_json_file.write_text('{"registry": "registry.spbnix.com"}', encoding="utf-8")
        findings = scan_file(temp_json_file)
        assert len(findings) == 1
        assert findings[0].pattern_class == "internal_domain_registry"

    def test_allows_registry_host_placeholder(self, temp_json_file: Path) -> None:
        """Should allow <REGISTRY_HOST> placeholder."""
        temp_json_file.write_text('{"registry": "<REGISTRY_HOST>"}', encoding="utf-8")
        findings = scan_file(temp_json_file)
        assert len(findings) == 0

    def test_allows_internal_domain_placeholder(self, temp_json_file: Path) -> None:
        """Should allow <INTERNAL_DOMAIN> placeholder."""
        temp_json_file.write_text('{"domain": "<INTERNAL_DOMAIN>"}', encoding="utf-8")
        findings = scan_file(temp_json_file)
        assert len(findings) == 0


# =============================================================================
# Tests for Raw Artifact Path Detection
# =============================================================================

class TestRawArtifactPathDetection:
    """Tests for raw artifact path detection."""

    def test_detects_lab_artifacts_live(self, temp_json_file: Path) -> None:
        """Should detect 'lab-artifacts/live' path."""
        temp_json_file.write_text('{"path": "lab-artifacts/live/some-file.json"}', encoding="utf-8")
        findings = scan_file(temp_json_file)
        assert len(findings) == 1
        assert findings[0].pattern_class == "raw_artifact_path"

    def test_allows_redacted_path_placeholder(self, temp_json_file: Path) -> None:
        """Should allow <REDACTED_RAW_ARTIFACT_DIR> placeholder."""
        temp_json_file.write_text('{"path": "<REDACTED_RAW_ARTIFACT_DIR>/file.json"}', encoding="utf-8")
        findings = scan_file(temp_json_file)
        assert len(findings) == 0

    def test_allows_sanitized_path_placeholder(self, temp_json_file: Path) -> None:
        """Should allow <SANITIZED_ARTIFACT_DIR> placeholder."""
        temp_json_file.write_text('{"path": "<SANITIZED_ARTIFACT_DIR>/file.json"}', encoding="utf-8")
        findings = scan_file(temp_json_file)
        assert len(findings) == 0


# =============================================================================
# Tests for Line Number Reporting
# =============================================================================

class TestLineNumberReporting:
    """Tests for line number reporting."""

    def test_reports_correct_line_number(self, temp_txt_file: Path) -> None:
        """Should report the correct line number for findings."""
        content = "line without private data\nline with 10.0.0.1 private IP\nanother line\n"
        temp_txt_file.write_text(content, encoding="utf-8")
        findings = scan_file(temp_txt_file)
        assert len(findings) == 1
        assert findings[0].line_number == 2

    def test_reports_multiple_findings(self, temp_txt_file: Path) -> None:
        """Should report multiple findings on different lines."""
        content = "10.0.0.1\n192.168.1.1\n<PRIVATE_IP>\n"
        temp_txt_file.write_text(content, encoding="utf-8")
        findings = scan_file(temp_txt_file)
        assert len(findings) == 2  # Two IPs, not the placeholder


# =============================================================================
# Tests for Placeholder-Only Line Detection
# =============================================================================

class TestPlaceholderOnlyLineDetection:
    """Tests for _is_placeholder_only_line helper."""

    def test_pure_placeholder_line(self) -> None:
        """Should identify line with only placeholders."""
        assert _is_placeholder_only_line("<PRIVATE_IP>")
        assert _is_placeholder_only_line("<K8S_NODE>")
        assert _is_placeholder_only_line("<LAB_NAMESPACE>")

    def test_multiple_placeholders(self) -> None:
        """Should handle lines with multiple placeholders."""
        assert _is_placeholder_only_line("<PRIVATE_IP> <K8S_NODE>")
        assert _is_placeholder_only_line("  <LAB_NAMESPACE>  ")

    def test_line_with_content(self) -> None:
        """Should not identify lines with actual content."""
        assert not _is_placeholder_only_line("ip: <PRIVATE_IP>")
        assert not _is_placeholder_only_line("10.0.0.1")

    def test_empty_line(self) -> None:
        """Should identify empty lines as placeholder-only."""
        assert _is_placeholder_only_line("")
        assert _is_placeholder_only_line("   ")


# =============================================================================
# Tests for Directory Scanning
# =============================================================================

class TestDirectoryScanning:
    """Tests for directory-level scanning."""

    def test_scans_nested_files(self, temp_case_dir: Path) -> None:
        """Should scan files in nested directories."""
        # Create nested structure
        nested_dir = temp_case_dir / "incident"
        nested_dir.mkdir()
        (nested_dir / "pods.txt").write_text("10.0.0.1", encoding="utf-8")

        findings = scan_directory(temp_case_dir)
        assert len(findings) == 1

    def test_skips_binary_files(self, temp_case_dir: Path) -> None:
        """Should skip binary files."""
        binary_file = temp_case_dir / "binary.bin"
        binary_file.write_bytes(b"\x00\x01\x02")

        findings = scan_directory(temp_case_dir)
        assert len(findings) == 0

    def test_skips_non_scannable_extensions(self, temp_case_dir: Path) -> None:
        """Should skip files with non-scannable extensions."""
        py_file = temp_case_dir / "script.py"
        py_file.write_text("10.0.0.1", encoding="utf-8")

        findings = scan_directory(temp_case_dir)
        assert len(findings) == 0  # .py files are not scanned

    def test_skips_git_directory(self, temp_case_dir: Path) -> None:
        """Should skip .git directory."""
        git_dir = temp_case_dir / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("10.0.0.1", encoding="utf-8")

        findings = scan_directory(temp_case_dir)
        assert len(findings) == 0


# =============================================================================
# Integration Tests
# =============================================================================

class TestPrivacyVerifierIntegration:
    """Integration tests for the privacy verifier."""

    def test_verify_clean_fixture(self, temp_case_dir: Path) -> None:
        """Should pass for fixture with only placeholders."""
        # Create a fixture-like structure with placeholders only
        incident_dir = temp_case_dir / "incident"
        incident_dir.mkdir()
        (incident_dir / "pods.txt").write_text(
            "NAME  READY  STATUS  IP  NODE\n"
            "app   1/1    Running  <PRIVATE_IP>  <K8S_NODE>\n",
            encoding="utf-8",
        )

        success, findings = verify_golden_case_privacy(temp_case_dir)
        assert success is True
        assert len(findings) == 0

    def test_verify_fixture_with_leaks(self, temp_case_dir: Path) -> None:
        """Should fail for fixture with private data."""
        incident_dir = temp_case_dir / "incident"
        incident_dir.mkdir()
        (incident_dir / "pods.txt").write_text(
            "NAME  READY  STATUS  IP  NODE\n"
            "app   1/1    Running  10.0.0.1  k3s-worker-01\n",
            encoding="utf-8",
        )

        success, findings = verify_golden_case_privacy(temp_case_dir)
        assert success is False
        assert len(findings) >= 2  # At least 2 findings (IP + node name)

    def test_finding_contains_file_and_line(self, temp_case_dir: Path) -> None:
        """Finding should contain file path and line number."""
        file_path = temp_case_dir / "test.txt"
        file_path.write_text("10.0.0.1", encoding="utf-8")

        success, findings = verify_golden_case_privacy(temp_case_dir)
        assert success is False
        assert len(findings) == 1
        assert "test.txt" in findings[0].file_path
        assert findings[0].line_number == 1

    def test_finding_has_bounded_excerpt(self, temp_case_dir: Path) -> None:
        """Finding excerpt should be bounded for safety."""
        # Create a finding with a very long line content
        finding = PrivacyFinding(
            file_path="test.txt",
            line_number=1,
            pattern_class="rfc1918_10",
            pattern_description="Test pattern",
            line_content="x" * 200,
        )
        report = finding.to_report()
        # Excerpt should be truncated in the report
        assert "..." in report, "Report should contain truncated excerpt"
        # But the finding should preserve the full line content
        assert len(finding.line_content) == 200, "Original line content should be preserved"


# =============================================================================
# Tests for Pattern Completeness
# =============================================================================

class TestPatternCompleteness:
    """Tests to ensure all required patterns are present."""

    def test_all_required_patterns_exist(self) -> None:
        """Verify all required patterns are defined."""
        pattern_classes = {p[0] for p in _FORBIDDEN_PATTERNS}

        required_patterns = {
            "rfc1918_10",
            "rfc1918_172",
            "rfc1918_192",
            "k8s_node_worker",
            "k8s_node_master",
            "internal_namespace",
            "internal_domain_harbor",
            "internal_domain_registry",
            "internal_domain_spbnix",
            "raw_artifact_path",
        }

        for required in required_patterns:
            assert required in pattern_classes, f"Missing required pattern: {required}"

    def test_all_placeholders_allowed(self) -> None:
        """Verify all placeholders are defined."""
        expected_placeholders = [
            "<PRIVATE_IP>",
            "<K8S_NODE>",
            "<LAB_NAMESPACE>",
            "<REGISTRY_HOST>",
            "<INTERNAL_DOMAIN>",
            "<REDACTED_RAW_ARTIFACT_DIR>",
            "<SANITIZED_ARTIFACT_DIR>",
        ]

        assert len(_ALLOWED_PLACEHOLDERS) == len(expected_placeholders)
