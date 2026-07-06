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

    def test_sensitive_payload_scan_allows_bare_kubeconfig_word(self) -> None:
        """Scan allows the bare word 'kubeconfig' (technical term, not credential)."""
        from scripts.otel_lab_contracts import VerificationReport, scan_for_sensitive_payloads

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # The word "kubeconfig" appears in explanatory text - should be allowed
            artifact = {
                "incident_id": "inc-123",
                "diagnostic_note": "This diagnosis used kubeconfig-based authentication to connect to the cluster.",
                "checks": [
                    {
                        "check_id": "kubectl_get_pods",
                        "result": "No pods found - check kubeconfig validity",
                    },
                ],
            }
            (artifact_dir / "evidence.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = scan_for_sensitive_payloads(artifact_dir, report)

            assert result is True
            assert report.passed is True

    def test_sensitive_payload_scan_rejects_client_certificate_data(self) -> None:
        """Scan rejects artifacts with client-certificate-data (real credential)."""
        from scripts.otel_lab_contracts import VerificationReport, scan_for_sensitive_payloads

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Real credential field - should be rejected
            artifact = {
                "incident_id": "inc-123",
                "evidence": {
                    "client-certificate-data": "LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0t...",
                },
            }
            (artifact_dir / "evidence.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = scan_for_sensitive_payloads(artifact_dir, report)

            assert result is False
            assert any("client-certificate-data" in e or "forbidden" in e.lower() for e in report.errors)

    def test_sensitive_payload_scan_rejects_client_key_data(self) -> None:
        """Scan rejects artifacts with client-key-data (real credential)."""
        from scripts.otel_lab_contracts import VerificationReport, scan_for_sensitive_payloads

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Real credential field - should be rejected
            artifact = {
                "incident_id": "inc-123",
                "evidence": {
                    "client-key-data": "LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0t...",
                },
            }
            (artifact_dir / "evidence.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = scan_for_sensitive_payloads(artifact_dir, report)

            assert result is False
            assert any("client-key-data" in e or "forbidden" in e.lower() for e in report.errors)

    def test_sensitive_payload_scan_rejects_token_field(self) -> None:
        """Scan rejects artifacts with token field containing non-empty value."""
        from scripts.otel_lab_contracts import VerificationReport, scan_for_sensitive_payloads

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Token field with value - should be rejected
            artifact = {
                "incident_id": "inc-123",
                "auth": {
                    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                },
            }
            (artifact_dir / "evidence.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = scan_for_sensitive_payloads(artifact_dir, report)

            assert result is False
            assert any("token" in e.lower() or "forbidden" in e.lower() for e in report.errors)

    def test_sensitive_payload_scan_rejects_private_key(self) -> None:
        """Scan rejects artifacts with private key PEM blocks."""
        from scripts.otel_lab_contracts import VerificationReport, scan_for_sensitive_payloads

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # Private key PEM - should be rejected
            artifact = {
                "incident_id": "inc-123",
                "credentials": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSk...\n-----END PRIVATE KEY-----",
            }
            (artifact_dir / "evidence.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = scan_for_sensitive_payloads(artifact_dir, report)

            assert result is False
            assert any("private key" in e.lower() or "forbidden" in e.lower() for e in report.errors)

    def test_sensitive_payload_scan_rejects_rsa_private_key(self) -> None:
        """Scan rejects artifacts with RSA private key PEM blocks."""
        from scripts.otel_lab_contracts import VerificationReport, scan_for_sensitive_payloads

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)

            # RSA Private key PEM - should be rejected
            artifact = {
                "incident_id": "inc-123",
                "credentials": "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA0Z3VS5...\n-----END RSA PRIVATE KEY-----",
            }
            (artifact_dir / "evidence.json").write_text(json.dumps(artifact))

            report = VerificationReport(passed=True)
            result = scan_for_sensitive_payloads(artifact_dir, report)

            assert result is False
            assert any("private key" in e.lower() or "forbidden" in e.lower() for e in report.errors)
