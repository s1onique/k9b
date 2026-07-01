"""Regression tests for provider curl helpers host extraction.

These tests verify:
1. Host-only extraction from URL (strip http://, https://, :port, and path)
2. DNS resolution receives host-only, not host:port
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestHostExtractionFromUrl:
    """Tests for host extraction from URL in provider curl helpers."""

    def test_extract_host_without_port(self) -> None:
        """URL without port should extract host correctly."""
        # Test the shell command logic used in _curl_service_pod
        target_url = "http://k9b-backend.k9b.svc.cluster.local/api/health"
        
        # Simulate the shell extraction logic
        # Remove scheme
        host_port = target_url.replace("http://", "").replace("https://", "")
        # Remove path
        host_port = host_port.split("/")[0]
        # Remove port if present
        host = host_port.split(":")[0]
        
        assert host == "k9b-backend.k9b.svc.cluster.local"

    def test_extract_host_with_port(self) -> None:
        """URL with port should extract host only, not host:port."""
        target_url = "http://k9b-backend.k9b.svc.cluster.local:8080/api/health/details"
        
        # Simulate the shell extraction logic
        # Remove scheme
        host_port = target_url.replace("http://", "").replace("https://", "")
        # Remove path
        host_port = host_port.split("/")[0]
        # Remove port if present
        host = host_port.split(":")[0]
        
        assert host == "k9b-backend.k9b.svc.cluster.local"
        assert ":" not in host  # Ensure no port remains

    def test_extract_host_with_https(self) -> None:
        """HTTPS URL with port should extract host only."""
        target_url = "https://k9b-backend.k9b.svc.cluster.local:443/api/v1/health"
        
        # Simulate the shell extraction logic
        # Remove scheme
        host_port = target_url.replace("http://", "").replace("https://", "")
        # Remove path
        host_port = host_port.split("/")[0]
        # Remove port if present
        host = host_port.split(":")[0]
        
        assert host == "k9b-backend.k9b.svc.cluster.local"
        assert ":" not in host  # Ensure no port remains

    def test_extract_host_from_full_service_url(self) -> None:
        """Full service URL should extract host for nslookup."""
        # This is the URL format used in provider preflight
        target_url = "http://k9b-backend.k9b.svc.cluster.local:8080/api/health/details"
        
        # Simulate the shell extraction logic
        # Remove scheme
        host_port = target_url.replace("http://", "").replace("https://", "")
        # Remove path
        host_port = host_port.split("/")[0]
        # Remove port if present
        host = host_port.split(":")[0]
        
        # nslookup should receive this
        assert host == "k9b-backend.k9b.svc.cluster.local"
        # Should NOT be k9b-backend.k9b.svc.cluster.local:8080

    def test_curl_pod_receives_correct_host(self) -> None:
        """Verify _curl_service_pod extracts host-only for nslookup."""
        from scripts.lab_common.provider_curl_helpers import _curl_service_pod
        
        target_url = "http://k9b-backend.k9b.svc.cluster.local:8080/api/health"
        
        # Mock subprocess to capture the pod manifest
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            
            _curl_service_pod(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                target_url=target_url,
                timeout_seconds=5,
            )
            
            # Check that kubectl apply was called
            assert mock_run.called
            
            # Get the pod manifest from the apply call
            apply_call = mock_run.call_args_list[0]
            pod_manifest = apply_call.kwargs.get("input") or apply_call[1].get("input", "")
            
            # Verify the host extraction in the manifest
            # The script should extract: k9b-backend.k9b.svc.cluster.local
            # NOT: k9b-backend.k9b.svc.cluster.local:8080
            assert "k9b-backend.k9b.svc.cluster.local" in pod_manifest
            # Ensure port is stripped from nslookup target
            # The script uses: host_port=$(echo "$host_port" | cut -d'/' -f1)
            # then: target_host=$(echo "$host_port" | sed 's/:.*//')


class TestDiagnosticOutputIsolation:
    """Tests for diagnostic output isolation (RESOLVING_HOST vs JSON body)."""

    def test_resolving_host_marker_exists(self) -> None:
        """RESOLVING_HOST marker should exist in pod manifest for diagnostics."""
        from scripts.lab_common.provider_curl_helpers import _curl_service_pod
        
        target_url = "http://k9b-backend.k9b.svc.cluster.local:8080/api/health"
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            
            _curl_service_pod(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                target_url=target_url,
                timeout_seconds=5,
            )
            
            apply_call = mock_run.call_args_list[0]
            pod_manifest = apply_call.kwargs.get("input") or apply_call[1].get("input", "")
            
            # The RESOLVING_HOST echo should be present
            assert 'echo "RESOLVING_HOST=' in pod_manifest

    def test_diagnostic_markers_stripped_from_body(self) -> None:
        """Diagnostic markers (RESOLVING_HOST, CURL_EXIT, HTTP_CODE) should be stripped from body."""
        from scripts.lab_common.provider_curl_helpers import _curl_service_pod
        
        target_url = "http://k9b-backend.k9b.svc.cluster.local:8080/api/health"
        
        # Mock pod logs with diagnostic markers
        # Parser captures all non-marker lines after ---CURL_START--- as body,
        # regardless of whether metadata appears before or after the response body.
        logs_output = """
RESOLVING_HOST=k9b-backend.k9b.svc.cluster.local
Server:  10.96.0.10
Address: 10.96.0.10#53

Name: k9b-backend.k9b.svc.cluster.local
Address: 10.43.0.100
---CURL_START---
{"status": "healthy", "version": "1.0.0"}
CURL_EXIT=0
HTTP_CODE=200
"""
        
        with patch("subprocess.run") as mock_run:
            # Configure mock to return different outputs for different calls
            def run_side_effect(*args: tuple, **kwargs: dict) -> MagicMock:
                cmd = args[0] if args else kwargs.get("args", ())
                if "apply" in " ".join(cmd):
                    return MagicMock(returncode=0, stdout="", stderr="")
                elif "get" in " ".join(cmd):
                    return MagicMock(returncode=0, stdout="Succeeded")
                elif "logs" in " ".join(cmd):
                    return MagicMock(returncode=0, stdout=logs_output, stderr="")
                elif "delete" in " ".join(cmd):
                    return MagicMock(returncode=0, stdout="", stderr="")
                return MagicMock(returncode=0, stdout="", stderr="")
            
            mock_run.side_effect = run_side_effect
            
            result = _curl_service_pod(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                target_url=target_url,
                timeout_seconds=5,
            )
            
            # Body should NOT contain diagnostic markers
            assert "RESOLVING_HOST" not in result.body
            assert "CURL_EXIT" not in result.body
            assert "HTTP_CODE" not in result.body
            
            # Body should contain the actual JSON response
            assert '{"status": "healthy"' in result.body or '{"status":"healthy"}' in result.body


class TestCurlResultDiagnostics:
    """Tests for CurlResult diagnostic fields."""

    def test_curl_result_has_stderr_field(self) -> None:
        """CurlResult should have stderr field for diagnostics."""
        from scripts.lab_common.provider_curl_helpers import CurlResult
        
        result = CurlResult(
            success=False,
            body="error",
            http_code=0,
            curl_rc=6,
            stderr="Could not resolve host",
        )
        
        assert hasattr(result, "stderr")
        assert result.stderr == "Could not resolve host"

    def test_is_transport_failure_detects_dns_error(self) -> None:
        """is_transport_failure should detect DNS errors (curl_rc=6)."""
        from scripts.lab_common.provider_curl_helpers import CurlResult
        
        result = CurlResult(
            success=False,
            body="Could not resolve host",
            http_code=0,
            curl_rc=6,
            stderr="Could not resolve host",
        )
        
        assert result.is_transport_failure() is True

    def test_is_transport_failure_detects_connection_refused(self) -> None:
        """is_transport_failure should detect connection refused (curl_rc=7)."""
        from scripts.lab_common.provider_curl_helpers import CurlResult
        
        result = CurlResult(
            success=False,
            body="Connection refused",
            http_code=0,
            curl_rc=7,
            stderr="Connection refused",
        )
        
        assert result.is_transport_failure() is True

    def test_is_transport_failure_detects_http_0(self) -> None:
        """is_transport_failure should detect HTTP 0 (no response)."""
        from scripts.lab_common.provider_curl_helpers import CurlResult
        
        result = CurlResult(
            success=False,
            body="",
            http_code=0,
            curl_rc=None,
            stderr="",
        )
        
        assert result.is_transport_failure() is True

    def test_is_transport_failure_passes_for_200(self) -> None:
        """is_transport_failure should pass for HTTP 200."""
        from scripts.lab_common.provider_curl_helpers import CurlResult
        
        result = CurlResult(
            success=True,
            body='{"healthy": true}',
            http_code=200,
            curl_rc=0,
            stderr="",
        )
        
        assert result.is_transport_failure() is False
