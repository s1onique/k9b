#!/usr/bin/env python3
"""Tests for image preflight modules (k9b_cnpg_image_preflight_*.py).

Tests:
- Image ref parsing
- HTTP error classification
- Output sanitization (no auth tokens leaked)
- Registry preflight result structures
- Node pull event classification
- TLS error classification
- CA certificate passthrough
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from k9b_cnpg_image_preflight_node import classify_pull_failure
from k9b_cnpg_image_preflight_registry import (
    _infer_component,
    classify_http_error,
    parse_image_ref,
    sanitize_error,
)
from k9b_cnpg_image_preflight_types import (
    FAIL_IMAGE_TLS,
    ImagePullSecretStatus,
    NodePullResult,
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
        from k9b_cnpg_image_preflight_types import FAIL_IMAGE_UNAUTHORIZED
        result = classify_http_error(401, "")
        assert result == FAIL_IMAGE_UNAUTHORIZED

    def test_403_maps_to_forbidden(self) -> None:
        """Should classify 403 as image_registry_forbidden."""
        from k9b_cnpg_image_preflight_types import FAIL_IMAGE_FORBIDDEN
        result = classify_http_error(403, "")
        assert result == FAIL_IMAGE_FORBIDDEN

    def test_404_maps_to_manifest_missing(self) -> None:
        """Should classify 404 as image_manifest_missing."""
        from k9b_cnpg_image_preflight_types import FAIL_IMAGE_MISSING
        result = classify_http_error(404, "")
        assert result == FAIL_IMAGE_MISSING

    def test_manifest_unknown_in_body_maps_to_manifest_missing(self) -> None:
        """Should detect manifest unknown in error body."""
        from k9b_cnpg_image_preflight_types import FAIL_IMAGE_MISSING
        result = classify_http_error(500, "manifest unknown")
        assert result == FAIL_IMAGE_MISSING

    def test_not_found_in_body_maps_to_manifest_missing(self) -> None:
        """Should detect not found in error body."""
        from k9b_cnpg_image_preflight_types import FAIL_IMAGE_MISSING
        result = classify_http_error(500, "image not found")
        assert result == FAIL_IMAGE_MISSING

    def test_unauthorized_in_body_maps_to_unauthorized(self) -> None:
        """Should detect unauthorized in error body."""
        from k9b_cnpg_image_preflight_types import FAIL_IMAGE_UNAUTHORIZED
        result = classify_http_error(500, "authentication required")
        assert result == FAIL_IMAGE_UNAUTHORIZED

    def test_forbidden_in_body_maps_to_forbidden(self) -> None:
        """Should detect forbidden in error body."""
        from k9b_cnpg_image_preflight_types import FAIL_IMAGE_FORBIDDEN
        result = classify_http_error(500, "access forbidden")
        assert result == FAIL_IMAGE_FORBIDDEN

    def test_unknown_error_maps_to_unknown(self) -> None:
        """Should classify unknown errors as image_registry_unknown_error."""
        from k9b_cnpg_image_preflight_types import FAIL_IMAGE_UNKNOWN
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
        from k9b_cnpg_image_preflight_types import FAIL_IMAGE_MISSING
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


class TestNodePullResult:
    """Tests for NodePullResult data class."""

    def test_to_dict_contains_all_fields(self) -> None:
        """Should serialize all fields to dict."""
        from k9b_cnpg_image_preflight_types import FAIL_NODE_PULL_BACKOFF
        result = NodePullResult(
            component="frontend",
            image_ref="registry.spbnix.com/gitinsky/k9b-frontend:ecacd81",
            pod_name="img-preflight-frontend-123456",
            success=False,
            failure_class=FAIL_NODE_PULL_BACKOFF,
            pod_phase="Failed",
            container_waiting_reason="ImagePullBackOff",
            container_waiting_message="failed to pull image",
            events_summary='[{"reason": "Failed"}]',
            timestamp="2026-06-23T08:00:00Z",
        )
        d = result.to_dict()
        assert d["component"] == "frontend"
        assert d["image_ref"] == "registry.spbnix.com/gitinsky/k9b-frontend:ecacd81"
        assert d["pod_name"] == "img-preflight-frontend-123456"
        assert d["success"] is False
        assert d["failure_class"] == FAIL_NODE_PULL_BACKOFF

    def test_to_dict_truncates_events_summary(self) -> None:
        """Should truncate events_summary to 500 chars."""
        long_events = "x" * 1000
        result = NodePullResult(
            component="frontend",
            image_ref="registry.spbnix.com/gitinsky/k9b-frontend:ecacd81",
            pod_name="test",
            success=True,
            events_summary=long_events,
            timestamp="2026-06-23T08:00:00Z",
        )
        d = result.to_dict()
        assert len(d["events_summary"]) <= 500


class TestNodePullEventClassification:
    """Tests for node pull failure event classification."""

    def test_parses_imagepullbackoff_with_manifest_unknown(self) -> None:
        """Should detect manifest unknown in ImagePullBackOff."""
        from k9b_cnpg_image_preflight_types import FAIL_NODE_IMAGE_MISSING
        events = {
            "items": [{
                "reason": "ImagePullBackOff",
                "message": "failed to pull and unpack image: failed to resolve reference: registry.spbnix.com/gitinsky/k9b-frontend:ecacd81: manifest unknown",
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        }
        failure_class, message = classify_pull_failure(events, "test-pod", "")
        assert failure_class == FAIL_NODE_IMAGE_MISSING
        assert "manifest unknown" in message.lower()

    def test_parses_errimagepull_with_not_found(self) -> None:
        """Should detect not found in ErrImagePull."""
        from k9b_cnpg_image_preflight_types import FAIL_NODE_IMAGE_MISSING
        events = {
            "items": [{
                "reason": "ErrImagePull",
                "message": "image not found in registry",
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        }
        failure_class, message = classify_pull_failure(events, "test-pod", "")
        assert failure_class == FAIL_NODE_IMAGE_MISSING

    def test_parses_unauthorized(self) -> None:
        """Should detect unauthorized."""
        from k9b_cnpg_image_preflight_types import FAIL_NODE_UNAUTHORIZED
        events = {
            "items": [{
                "reason": "ImagePullBackOff",
                "message": "unauthorized: authentication required",
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        }
        failure_class, message = classify_pull_failure(events, "test-pod", "")
        assert failure_class == FAIL_NODE_UNAUTHORIZED

    def test_parses_forbidden(self) -> None:
        """Should detect forbidden/denied."""
        from k9b_cnpg_image_preflight_types import FAIL_NODE_UNAUTHORIZED
        events = {
            "items": [{
                "reason": "ImagePullBackOff",
                "message": "access denied or forbidden",
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        }
        failure_class, message = classify_pull_failure(events, "test-pod", "")
        assert failure_class == FAIL_NODE_UNAUTHORIZED

    def test_parses_tls_error(self) -> None:
        """Should detect TLS/certificate failures."""
        from k9b_cnpg_image_preflight_types import FAIL_NODE_TLS
        events = {
            "items": [{
                "reason": "ImagePullBackOff",
                "message": "x509: certificate signed by unknown authority",
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        }
        failure_class, message = classify_pull_failure(events, "test-pod", "")
        assert failure_class == FAIL_NODE_TLS

    def test_parses_network_error(self) -> None:
        """Should detect network/DNS failures exactly as node_registry_network_error."""
        from k9b_cnpg_image_preflight_types import FAIL_NODE_NETWORK
        events = {
            "items": [{
                "reason": "ImagePullBackOff",
                "message": "dial tcp: lookup registry.spbnix.com: no such host",
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        }
        failure_class, message = classify_pull_failure(events, "test-pod", "")
        assert failure_class == FAIL_NODE_NETWORK, f"Expected {FAIL_NODE_NETWORK}, got {failure_class}"

    def test_defaults_to_pull_backoff(self) -> None:
        """Should default to node_image_pull_backoff for unknown reasons."""
        from k9b_cnpg_image_preflight_types import FAIL_NODE_PULL_BACKOFF
        events = {
            "items": [{
                "reason": "ImagePullBackOff",
                "message": "some pull error",
                "involvedObject": {"kind": "Pod", "name": "test-pod"}
            }]
        }
        failure_class, message = classify_pull_failure(events, "test-pod", "")
        assert failure_class == FAIL_NODE_PULL_BACKOFF


class TestNodePullDescribeClassification:
    """Tests for kubectl describe output classification."""

    def test_parses_imagepullbackoff(self) -> None:
        """Should parse ImagePullBackOff from describe output."""
        from k9b_cnpg_image_preflight_types import FAIL_NODE_PULL_BACKOFF
        describe = """
Name:             img-preflight-frontend-123
Namespace:        k9b-cnpg-lab-123
Status:           Failed
Conditions:
  Type           Status
  Init Container Ready  True
Ready:            False
Containers:
  test:
    State:          Waiting
      Reason:       ImagePullBackOff
    Message:        Back-off pulling image "registry.spbnix.com/gitinsky/k9b-frontend:ecacd81"
"""
        failure_class, message = classify_pull_failure({"items": []}, "test", describe)
        assert failure_class == FAIL_NODE_PULL_BACKOFF

    def test_parses_errimagepull_with_manifest_unknown(self) -> None:
        """Should parse ErrImagePull with manifest unknown."""
        from k9b_cnpg_image_preflight_types import FAIL_NODE_IMAGE_MISSING, FAIL_NODE_PULL_BACKOFF
        describe = """
Name:             img-preflight-frontend-123
Status:           Failed
Containers:
  test:
    State:          Waiting
      Reason:       ErrImagePull
    Message:        failed to resolve reference: manifest unknown
"""
        failure_class, message = classify_pull_failure({"items": []}, "test", describe)
        assert failure_class in (FAIL_NODE_IMAGE_MISSING, FAIL_NODE_PULL_BACKOFF)

    def test_no_match_for_empty_output(self) -> None:
        """Should return empty for empty/nomatch output."""
        describe = "No events."
        failure_class, message = classify_pull_failure({"items": []}, "test", describe)
        assert failure_class == ""


class TestCurlTlsErrorClassification:
    """Tests for curl exit 60 / SSL certificate problem classification."""

    def test_curl_exit_60_ssl_certificate_problem_classifies_as_tls_error(
        self, tmp_path: Path
    ) -> None:
        """Should classify curl exit 60 with SSL certificate problem as image_registry_tls_error."""
        from k9b_cnpg_image_preflight_registry import check_manifest_with_curl

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
        from k9b_cnpg_image_preflight_registry import check_manifest_with_curl

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
        from k9b_cnpg_image_preflight_registry import check_manifest_with_curl

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
        from k9b_cnpg_image_preflight_registry import check_manifest_with_curl

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


class TestImagePullSecretStatus:
    """Tests for ImagePullSecretStatus data class."""

    def test_to_dict_contains_all_fields(self) -> None:
        """Should serialize all fields to dict."""
        status = ImagePullSecretStatus(
            namespace="k9b-cnpg-lab-123",
            secrets_exist=True,
            secret_names=["reg-creds", "another-secret"],
            has_service_account_ref=True,
            service_account_name="default",
            error_message="",
        )
        d = status.to_dict()
        assert d["namespace"] == "k9b-cnpg-lab-123"
        assert d["secrets_exist"] is True
        assert d["secret_names"] == ["reg-creds", "another-secret"]
        assert d["has_service_account_ref"] is True
        assert d["service_account_name"] == "default"

    def test_no_secret_data_leaked(self) -> None:
        """Should not expose secret data types."""
        status = ImagePullSecretStatus(
            namespace="test",
            secrets_exist=True,
            secret_names=["reg-creds"],
        )
        d = status.to_dict()
        assert "data" not in d
        assert "dockerconfigjson" not in str(d)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
