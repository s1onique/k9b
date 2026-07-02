"""Regression tests for P0b provider health JSON parsing.

These tests verify that the P0b provider preflight correctly handles the
"Extra data" JSON parse error caused by curl metadata contaminating the
response body.

Bug: The old parser was including CURL_EXIT= and HTTP_CODE= lines in the
body because shell script outputs: ---CURL_START---, CURL_EXIT, HTTP_CODE,
body, STDERR_BLOCK. The parser captured all lines after ---CURL_START---
as body, including the metadata lines.

Fix: The parser now extracts only non-metadata lines from the body region,
filtering out CURL_EXIT=, HTTP_CODE=, RESOLVING_HOST=, NO_RESPONSE_BODY,
and nslookup output lines.
"""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

# =============================================================================
# Acceptance Test 1: Plain valid JSON
# =============================================================================

def test_plain_valid_json_parses_successfully() -> None:
    """Plain valid JSON body should parse successfully.
    
    Acceptance test 1: No provider_health_invalid_json for valid JSON.
    """
    from scripts.lab_common.provider_curl_helpers import _curl_service_pod

    raw_output = """RESOLVING_HOST=k9b-backend.k9b.svc.cluster.local
---CURL_START---
CURL_EXIT=0
HTTP_CODE=200
{"healthy": true, "dependencies": []}
STDERR_BLOCK
"""

    with _mock_pod_execution(raw_output):
        result = _curl_service_pod(
            kubeconfig="/fake/kubeconfig",
            namespace="k9b",
            target_url="http://k9b-backend.k9b.svc.cluster.local:8080/api/health/details",
            timeout_seconds=5,
        )

    # Should parse correctly
    assert result.http_code == 200
    assert result.curl_rc == 0
    
    # Body should be valid JSON
    parsed = json.loads(result.body)
    assert parsed["healthy"] is True
    assert parsed["dependencies"] == []


# =============================================================================
# Acceptance Test 2: Valid JSON plus known wrapper/marker output
# =============================================================================

def test_valid_json_with_curl_wrapper_parses_correctly() -> None:
    """Valid JSON plus curl/status/stderr block should extract only JSON body.
    
    Acceptance test 2: Body extraction should not include wrapper metadata.
    """
    from scripts.lab_common.provider_curl_helpers import _curl_service_pod

    raw_output = """RESOLVING_HOST=k9b-backend.k9b.svc.cluster.local
Server: 10.43.0.10
Address: 10.43.0.10#53

---CURL_START---
CURL_EXIT=0
HTTP_CODE=200
{"healthy": true, "timestamp": "2026-06-16T10:00:00Z", "version": "1.0"}
STDERR_BLOCK
"""

    with _mock_pod_execution(raw_output):
        result = _curl_service_pod(
            kubeconfig="/fake/kubeconfig",
            namespace="k9b",
            target_url="http://k9b-backend.k9b.svc.cluster.local:8080/api/health/details",
            timeout_seconds=5,
        )

    # Body should NOT contain markers
    assert "RESOLVING_HOST" not in result.body
    assert "CURL_EXIT" not in result.body
    assert "HTTP_CODE" not in result.body
    assert "STDERR_BLOCK" not in result.body
    assert "Server:" not in result.body
    
    # Body should be valid JSON
    parsed = json.loads(result.body)
    assert parsed["healthy"] is True
    assert "timestamp" in parsed


# =============================================================================
# Acceptance Test 3: Valid JSON plus STDERR_BLOCK
# =============================================================================

def test_json_body_before_stderr_block_extracted_correctly() -> None:
    """Body before STDERR_BLOCK should not include stderr text.
    
    Acceptance test 3: stderr text should not be in json.loads().
    """
    from scripts.lab_common.provider_curl_helpers import _curl_exec_pod

    raw_output = """---CURL_START---
CURL_EXIT=0
HTTP_CODE=200
{"healthy": true, "status": "available"}
STDERR_BLOCK
some stderr text here
"""

    def run_side_effect(*args: tuple, **kwargs: dict) -> MagicMock:
        return MagicMock(returncode=0, stdout=raw_output, stderr="")

    with patch("subprocess.run", side_effect=run_side_effect):
        result = _curl_exec_pod(
            kubeconfig="/fake/kubeconfig",
            namespace="k9b",
            deployment="k9b-backend",
            container="backend",
            target_url="http://localhost:8080/api/health/details",
            timeout_seconds=5,
        )

    # Body should not contain STDERR_BLOCK or text after it
    assert "STDERR_BLOCK" not in result.body
    assert "some stderr text" not in result.body
    
    # Body should be valid JSON
    parsed = json.loads(result.body)
    assert parsed["healthy"] is True


# =============================================================================
# Acceptance Test 4: Genuinely invalid JSON
# =============================================================================

def test_genuinely_invalid_json_reports_correct_error() -> None:
    """Invalid JSON body should fail with provider_health_invalid_json.
    
    Acceptance test 4: JSON parse error should include line/column and body prefix.
    """
    from scripts.lab_common.provider_preflight import (
        FAILURE_PROVIDER_HEALTH_INVALID_JSON,
        run_provider_preflight,
    )

    # Actually invalid JSON (not just contaminated)
    invalid_body = '{"bad json'
    
    def make_curl_result() -> MagicMock:
        result = MagicMock()
        result.success = True
        result.body = invalid_body
        result.http_code = 200
        result.curl_rc = 0
        result.stderr = ""
        return result

    with patch(
        "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
        return_value=make_curl_result(),
    ), patch(
        "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
        return_value=make_curl_result(),
    ):
        with TemporaryDirectory() as tmpdir:
            result = run_provider_preflight(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                service="k9b-backend",
                port=8080,
                artifact_dir=Path(tmpdir),
            )

    # Should fail with INVALID_JSON classification
    assert result.passed is False
    assert result.failure_class == FAILURE_PROVIDER_HEALTH_INVALID_JSON
    assert "JSON parse error" in result.message


# =============================================================================
# Acceptance Test 5: Concatenated JSON without markers
# =============================================================================

def test_concatenated_json_without_markers_fails_strict_parsing() -> None:
    """Concatenated JSON should fail strict parsing (no silent acceptance).
    
    Acceptance test 5: {"healthy": true}{"extra": true} should fail as invalid.
    This prevents masking malformed server responses.
    
    Note: Concatenated JSON is now classified as output_contaminated because
    raw_decode successfully parses the first JSON object with trailing bytes.
    This is the correct classification for "valid JSON + extra data".
    """
    from scripts.lab_common.provider_preflight import (
        FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
        run_provider_preflight,
    )

    # Concatenated JSON without markers - server response issue
    concatenated_body = '{"healthy": true}{"extra": true}'
    
    def make_curl_result() -> MagicMock:
        result = MagicMock()
        result.success = True
        result.body = concatenated_body
        result.http_code = 200
        result.curl_rc = 0
        result.stderr = ""
        return result

    with patch(
        "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
        return_value=make_curl_result(),
    ), patch(
        "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
        return_value=make_curl_result(),
    ):
        with TemporaryDirectory() as tmpdir:
            result = run_provider_preflight(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                service="k9b-backend",
                port=8080,
                artifact_dir=Path(tmpdir),
            )

    # Should fail - this is valid JSON + trailing bytes (output contamination)
    assert result.passed is False
    assert result.failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED


# =============================================================================
# Acceptance Test 6: Non-200 HTTP response
# =============================================================================

def test_non_200_http_preserves_classification() -> None:
    """Non-200 HTTP responses should not be turned into JSON parse failures.
    
    Acceptance test 6: HTTP failures should be classified by status, not JSON parsing.
    """
    from scripts.lab_common.provider_preflight import run_provider_preflight

    # Valid JSON but HTTP 500
    valid_json_body = '{"error": "internal server error"}'
    
    def make_curl_result() -> MagicMock:
        result = MagicMock()
        result.success = False  # HTTP 500 is not success
        result.body = valid_json_body
        result.http_code = 500
        result.curl_rc = 0
        result.stderr = ""
        return result

    with patch(
        "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
        return_value=make_curl_result(),
    ), patch(
        "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
        return_value=make_curl_result(),
    ):
        with TemporaryDirectory() as tmpdir:
            result = run_provider_preflight(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                service="k9b-backend",
                port=8080,
                artifact_dir=Path(tmpdir),
            )

    # Should fail, but NOT with INVALID_JSON
    assert result.passed is False
    # Should be unhealthy, not invalid_json
    assert "Invalid JSON" not in result.message


# =============================================================================
# Acceptance Test 7: Regression fixture from live log
# =============================================================================

def test_p0b_live_log_regression_fixture() -> None:
    """Regression: Body prefix starts with health JSON shape, curl metadata appended.
    
    Acceptance test 7: This is the exact failure mode from the live lab:
    - Valid JSON body starting with {"timestamp": "...", "healthy": true, ...}
    - curl metadata (CURL_EXIT, HTTP_CODE) appended after body
    - Old parser failed with "Extra data" because it included metadata in body
    - New parser succeeds because it isolates the JSON body
    """
    from scripts.lab_common.provider_curl_helpers import _curl_service_pod

    # Exact format from live log that caused "Extra data" failure
    raw_output = """RESOLVING_HOST=k9b-backend.k9b.svc.cluster.local
Server: 10.43.0.10
Address: 10.43.0.10#53

---CURL_START---
CURL_EXIT=0
HTTP_CODE=200
{"timestamp": "2026-06-16T10:00:00Z", "healthy": true, "primary_failure_class": "", "provider_enabled": true, "dependencies": [{"dependency_name": "diagnosis_provider", "status": "available", "phase": "models_list_ok"}]}
STDERR_BLOCK
"""

    with _mock_pod_execution(raw_output):
        result = _curl_service_pod(
            kubeconfig="/fake/kubeconfig",
            namespace="k9b",
            target_url="http://k9b-backend.k9b.svc.cluster.local:8080/api/health/details",
            timeout_seconds=5,
        )

    # Old parser would include CURL_EXIT=0 HTTP_CODE=200 in body
    # causing json.loads() to fail with "Extra data"
    
    # New parser should extract just the JSON
    assert result.http_code == 200
    assert result.curl_rc == 0
    
    # Body should be clean JSON (no metadata contamination)
    assert "CURL_EXIT" not in result.body
    assert "HTTP_CODE" not in result.body
    
    # Should parse successfully
    parsed = json.loads(result.body)
    assert parsed["healthy"] is True
    assert parsed["timestamp"] == "2026-06-16T10:00:00Z"
    assert "diagnosis_provider" in str(parsed["dependencies"])


# =============================================================================
# Helper
# =============================================================================

def _mock_pod_execution(logs_output: str) -> AbstractContextManager[object]:
    """Create mock context for pod execution."""
    def run_side_effect(*args: tuple, **kwargs: dict) -> MagicMock:
        cmd = args[0] if args else kwargs.get("args", ())
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        if "apply" in cmd_str:
            return MagicMock(returncode=0, stdout="", stderr="")
        elif "get" in cmd_str and "pod" in cmd_str:
            return MagicMock(returncode=0, stdout="Succeeded")
        elif "logs" in cmd_str:
            return MagicMock(returncode=0, stdout=logs_output, stderr="")
        elif "delete" in cmd_str:
            return MagicMock(returncode=0, stdout="", stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")

    return patch("subprocess.run", side_effect=run_side_effect)
