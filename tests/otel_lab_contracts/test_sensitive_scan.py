"""Tests for sensitive payload scanning."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


class TestSensitivePayloadScanHardening:
    """Tests for sensitive payload scan hardening."""

    def test_sensitive_payload_scan_rejects_bearer_token_even_with_sensitive_read_denied(self) -> None:
        """Scan rejects Bearer token even when sensitive_read_denied is also present."""
        from scripts.otel_lab_contracts import VerificationReport, scan_for_sensitive_payloads

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Contains both Bearer token AND sensitive_read_denied
            artifact = {
                "incident_id": "inc-123",
                "checks": [
                    {
                        "check_id": "kubectl_get_secrets",
                        "result": "sensitive_read_denied",
                    },
                    {
                        "check_id": "kubectl_get_pods",
                        "result": "Bearer eyJhbGciOiJSUzI1NiIs...",  # Real token!
                    },
                ],
            }
            (artifact_dir / "evidence.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = scan_for_sensitive_payloads(artifact_dir, report)

            assert result is False
            assert any("sensitive" in e.lower() or "forbidden" in e.lower() for e in report.errors)

    def test_sensitive_payload_scan_allows_only_sensitive_read_denied(self) -> None:
        """Scan allows artifact with only sensitive_read_denied and no real tokens."""
        from scripts.otel_lab_contracts import VerificationReport, scan_for_sensitive_payloads

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Contains only safe pattern, no real forbidden tokens
            artifact = {
                "incident_id": "inc-123",
                "checks": [
                    {
                        "check_id": "kubectl_get_secrets",
                        "result": "sensitive_read_denied",
                    },
                    {
                        "check_id": "kubectl_get_pods",
                        "result": "No pods found in namespace",
                    },
                ],
            }
            (artifact_dir / "evidence.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = scan_for_sensitive_payloads(artifact_dir, report)

            assert result is True
            assert report.passed is True


class TestSensitivePayloadScan:
    """Tests for sensitive payload scanning."""

    def test_sensitive_payload_scan_rejects_bearer_token(self) -> None:
        """Scan rejects artifacts with bearer token."""
        from scripts.otel_lab_contracts import VerificationReport, scan_for_sensitive_payloads

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            artifact = {
                "incident_id": "inc-123",
                "evidence": {
                    "token": "Bearer eyJhbGciOiJSUzI1NiIs...",
                },
            }
            (artifact_dir / "evidence.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = scan_for_sensitive_payloads(artifact_dir, report)

            assert result is False
            assert any("sensitive" in e.lower() or "forbidden" in e.lower() for e in report.errors)

    def test_sensitive_payload_scan_allows_sensitive_read_denied(self) -> None:
        """Scan allows safe patterns like sensitive_read_denied."""
        from scripts.otel_lab_contracts import VerificationReport, scan_for_sensitive_payloads

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            artifact = {
                "incident_id": "inc-123",
                "checks": [
                    {
                        "check_id": "kubectl_get_secrets",
                        "result": "sensitive_read_denied",
                    }
                ],
            }
            (artifact_dir / "evidence.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = scan_for_sensitive_payloads(artifact_dir, report)

            assert result is True
            assert report.passed is True

    def test_sensitive_payload_scan_rejects_kubeconfig(self) -> None:
        """Scan rejects artifacts with kubeconfig data."""
        from scripts.otel_lab_contracts import VerificationReport, scan_for_sensitive_payloads

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            artifact = {
                "incident_id": "inc-123",
                "evidence": {
                    "kubeconfig": "apiVersion: v1\nclusters:\n- cluster:\n    server: https://...",
                },
            }
            (artifact_dir / "evidence.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = scan_for_sensitive_payloads(artifact_dir, report)

            assert result is False
