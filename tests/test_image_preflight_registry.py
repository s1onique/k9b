#!/usr/bin/env python3
"""Tests for image preflight registry operations.

Tests:
- Image ref parsing
- HTTP error classification
- Output sanitization (no auth tokens leaked)
- Registry preflight result structures
- CA certificate passthrough
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from k9b_cnpg_image_preflight_registry import (
    _infer_component,
    check_manifest_with_curl,
    classify_http_error,
    parse_image_ref,
    sanitize_error,
)
from k9b_cnpg_image_preflight_types import (
    FAIL_IMAGE_MISSING,
    FAIL_IMAGE_TLS,
    FAIL_IMAGE_UNAUTHORIZED,
    FAIL_IMAGE_FORBIDDEN,
    FAIL_IMAGE_UNKNOWN,
    RegistryResult,
)


class TestParseImageRef:
    """Tests for image reference parsing."""

    def test_parses_full_registry_path_with_tag(self) -> None:
        """Should parse registry.spbnix.com/gitinsky/k9b-frontend:ecacd81."""
        host, repo, tag = parse_image_ref(
            "registry.spbnix.com/gitinsky/k9b-frontend:ecacd81"
        )
        assert host == "registry.spbnix.com"
        assert repo == "gitinsky/k9b-frontend"
        assert tag == "ecacd81"

    def test_parses_backend_image_ref(self) -> None:
        """Should parse backend image reference."""
        host, repo, tag = parse_image_ref(
            "registry.spbnix.com/gitinsky/k9b-backend:v1.2.3"
        )
        assert host == "registry.spbnix.com"
        assert repo == "gitinsky/k9b-backend"
        assert tag == "v1.2.3"

    def test_parses_docker_hub_image(self) -> None:
        """Should parse docker hub images without registry."""
        host, repo, tag = parse_image_ref("nginx:latest")
        assert host == "docker.io"
        assert "nginx" in repo
        assert tag == "latest"

    def test_handles_digest_references(self) -> None:
        """Should strip digest and use tag from image ref."""
        host, repo, tag = parse_image_ref(
            "registry.spbnix.com/gitinsky/k9b@sha256:abc123"
        )
        assert host == "registry.spbnix.com"
        assert repo == "gitinsky/k9b"
        # Digest references without explicit tag default to "latest"
        assert tag == "latest"

    def test_defaults_tag_to_latest(self) -> None:
        """Should default to 'latest' tag when not specified."""
        host, repo, tag = parse_image_ref(
            "registry.spbnix.com/gitinsky/k9b"
        )
        assert tag == "latest"


class TestClassifyHttpError:
    """Tests for HTTP error classification."""

    def test_401_maps_to_unauthorized(self) -> None:
        """Should classify 401 as image_registry_unauthorized."""
        result = classify_http_error(401, "")
        assert result == FAIL_IMAGE_UNAUTHORIZED

    def test_403_maps_to_forbidden(self) -> None:
        """Should classify 403 as image_registry_forbidden."""
        result = classify_http_error(403, "")
        assert result == FAIL_IMAGE_FORBIDDEN

    def test_404_maps_to_manifest_missing(self) -> None:
        """Should classify 404 as image_manifest_missing."""
        result = classify_http_error(404, "")
        assert result == FAIL_IMAGE_MISSING

    def test_manifest_unknown_in_body_maps_to_manifest_missing(self) -> None:
        """Should detect manifest unknown in error body."""
        result = classify_http_error(500, "manifest unknown")
        assert result == FAIL_IMAGE_MISSING

    def test_not_found_in_body_maps_to_manifest_missing(self) -> None:
        """Should detect not found in error body."""
        result = classify_http_error(500, "image not found")
        assert result == FAIL_IMAGE_MISSING

    def test_unauthorized_in_body_maps_to_unauthorized(self) -> None:
        """Should detect unauthorized in error body."""
        result = classify_http_error(500, "authentication required")
        assert result == FAIL_IMAGE_UNAUTHORIZED

    def test_forbidden_in_body_maps_to_forbidden(self) -> None:
        """Should detect forbidden in error body."""
        result = classify_http_error(500, "access forbidden")
        assert result == FAIL_IMAGE_FORBIDDEN

    def test_unknown_error_maps_to_unknown(self) -> None:
        """Should classify unknown errors as image_registry_unknown_error."""
        result = classify_http_error(500, "internal server error")
        assert result == FAIL_IMAGE_UNKNOWN


class TestSanitizeError:
    """Tests for error message sanitization."""

    def test_removes_auth_headers(self) -> None:
        """Should remove Authorization headers."""
        msg = "Error: Authorization: Bearer secret123token"
        sanitized = sanitize_error(msg)
        assert "secret123token" not in sanitized
        assert "Authorization" not in sanitized

    def test_removes_bearer_tokens(self) -> None:
        """Should remove bearer tokens."""
        msg = "Authorization: Bearer ghp_longbase64token1234567890"
        sanitized = sanitize_error(msg)
        assert "[REDACTED]" in sanitized or "Bearer" not in sanitized

    def test_removes_password_patterns(self) -> None:
        """Should remove password= patterns."""
        msg = "password=mysecretpassword"
        sanitized = sanitize_error(msg)
        assert "mysecretpassword" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_removes_secret_patterns(self) -> None:
        """Should remove secret= patterns."""
        msg = "secret=mysupersecretvalue"
        sanitized = sanitize_error(msg)
        assert "mysupersecretvalue" not in sanitized

    def test_preserves_error_context(self) -> None:
        """Should preserve non-sensitive error context."""
        msg = "Connection refused to registry.spbnix.com:443"
        sanitized = sanitize_error(msg)
        assert "Connection refused" in sanitized
        assert "registry.spbnix.com" in sanitized

    def test_removes_base64_credentials(self) -> None:
        """Should redact long base64-like strings."""
        msg = "token=aHR0cHM6Ly9yZWdpc3RyeS5zcGJeZnguY29tL2F1dGg="
        sanitized = sanitize_error(msg)
        assert "aHR0cHM6Ly9yZWdpc3RyeS5zcGJeZnguY29tL2F1dGg=" not in sanitized


class TestRegistryPreflightResult:
    """Tests for RegistryPreflightResult data class."""

    def test_to_dict_contains_all_fields(self) -> None:
        """Should serialize all fields to dict."""
        result = RegistryResult(
            component="frontend",
            image_ref="registry.spbnix.com/gitinsky/k9b-frontend:ecacd81",
            registry_host="registry.spbnix.com",
            repository_path="gitinsky/k9b-frontend",
            tag="ecacd81",
            success=False,
            failure_class=FAIL_IMAGE_MISSING,
            status_code=404,
            error_message="manifest unknown",
            command_used="curl -I https://registry.spbnix.com/...",
            timestamp="2026-06-23T08:00:00Z",
        )
        d = result.to_dict()
        assert d["component"] == "frontend"
        assert d["image_ref"] == "registry.spbnix.com/gitinsky/k9b-frontend:ecacd81"
        assert d["registry_host"] == "registry.spbnix.com"
        assert d["success"] is False
        assert d["failure_class"] == FAIL_IMAGE_MISSING
        assert d["status_code"] == 404

    def test_to_dict_no_leaked_credentials(self) -> None:
        """Result dict should not contain credential fields."""
        result = RegistryResult(
            component="frontend",
            image_ref="registry.spbnix.com/gitinsky/k9b-frontend:ecacd81",
            registry_host="registry.spbnix.com",
            repository_path="gitinsky/k9b-frontend",
            tag="ecacd81",
            success=False,
            command_used="curl -u user:pass https://...",
            timestamp="2026-06-23T08:00:00Z",
        )
        d = result.to_dict()
        assert "password" not in d
        assert "secret" not in d
        assert "token" not in d


class TestInferComponentFromRef:
    """Tests for component inference from image reference."""

    def test_infers_frontend(self) -> None:
        """Should infer frontend from image ref."""
        result = _infer_component(
            "registry.spbnix.com/gitinsky/k9b-frontend:ecacd81"
        )
        assert result == "frontend"

    def test_infers_backend(self) -> None:
        """Should infer backend from image ref."""
        result = _infer_component(
            "registry.spbnix.com/gitinsky/k9b-backend:v1.0"
        )
        assert result == "backend"

    def test_infers_scheduler(self) -> None:
        """Should infer scheduler from image ref."""
        result = _infer_component(
            "registry.spbnix.com/gitinsky/k9b-scheduler:latest"
        )
        assert result == "scheduler"

    def test_returns_unknown_for_unmatched(self) -> None:
        """Should return unknown for unmatched patterns."""
        result = _infer_component("nginx:latest")
        assert result == "unknown"


class TestCurlTlsErrorClassification:
    """Tests for curl exit 60 / SSL certificate problem classification."""

    def test_curl_exit_60_ssl_certificate_problem_classifies_as_tls_error(
        self, tmp_path: Path
    ) -> None:
        """Should classify curl exit 60 with SSL certificate problem as image_registry_tls_error."""
        # Create a dummy CA cert file
        ca_cert = tmp_path / "ca.crt"
        ca_cert.write_text("-----BEGIN CERTIFICATE-----\nDUMMY\n-----END CERTIFICATE-----\n")

        # Mock subprocess.run to return exit code 60 with SSL error
        mock_proc = mock.Mock()
        mock_proc.returncode = 60
        mock_proc.stdout = ""  # No HTTP status when TLS fails
        mock_proc.stderr = "curl: (60) SSL certificate problem: unable to get local issuer certificate"

        with mock.patch("subprocess.run", return_value=mock_proc):
            result = check_manifest_with_curl(
                "harbor-pve1.spbnix.local/k9b/k9b-backend:test",
                ca_cert_path=str(ca_cert),
            )

        assert result["success"] is False
        assert result["failure_class"] == FAIL_IMAGE_TLS
        assert result["status_code"] == 0
        assert "SSL certificate problem" in result["error_message"]
        assert "local issuer certificate" in result["error_message"]
        assert "--cacert" in result["command_used"]

    def test_curl_exit_60_unable_to_get_local_issuer_classifies_as_tls_error(
        self, tmp_path: Path
    ) -> None:
        """Should classify 'unable to get local issuer certificate' as image_registry_tls_error."""
        # Create a dummy CA cert file
        ca_cert = tmp_path / "ca.crt"
        ca_cert.write_text("-----BEGIN CERTIFICATE-----\nDUMMY\n-----END CERTIFICATE-----\n")

        # Mock subprocess.run to return exit code 60 with different SSL error text
        mock_proc = mock.Mock()
        mock_proc.returncode = 60
        mock_proc.stdout = ""
        mock_proc.stderr = "curl: (60) SSL certificate problem: unable to get local issuer certificate"

        with mock.patch("subprocess.run", return_value=mock_proc):
            result = check_manifest_with_curl(
                "harbor-pve1.spbnix.local/k9b/k9b-frontend:v1",
                ca_cert_path=str(ca_cert),
            )

        assert result["failure_class"] == FAIL_IMAGE_TLS
        assert "unable to get local issuer certificate" in result["error_message"].lower()

    def test_ca_cert_path_passthrough_to_curl_command(self, tmp_path: Path) -> None:
        """Should include --cacert in curl command when ca_cert_path is provided."""
        ca_cert = tmp_path / "harbor-ca.crt"
        ca_cert.write_text("-----BEGIN CERTIFICATE-----\nDUMMY\n-----END CERTIFICATE-----\n")

        # Mock subprocess.run to return success
        mock_proc = mock.Mock()
        mock_proc.returncode = 0
        mock_proc.stdout = "200"
        mock_proc.stderr = ""

        with mock.patch("subprocess.run", return_value=mock_proc):
            result = check_manifest_with_curl(
                "harbor-pve1.spbnix.local/k9b/k9b-backend:test",
                ca_cert_path=str(ca_cert),
            )

        # Verify --cacert is in the command used
        assert "--cacert" in result["command_used"]
        assert str(ca_cert) in result["command_used"]
        assert result["success"] is True

    def test_no_ca_cert_when_not_provided(self) -> None:
        """Should not include --cacert when ca_cert_path is None."""
        mock_proc = mock.Mock()
        mock_proc.returncode = 0
        mock_proc.stdout = "200"
        mock_proc.stderr = ""

        with mock.patch("subprocess.run", return_value=mock_proc):
            result = check_manifest_with_curl(
                "harbor-pve1.spbnix.local/k9b/k9b-backend:test",
                # No ca_cert_path
            )

        # Verify --cacert is NOT in the command used
        assert "--cacert" not in result["command_used"]
        assert result["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
