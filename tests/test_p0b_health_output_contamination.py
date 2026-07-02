"""Tests for P0b provider health output framing contamination detection.

These tests verify that the P0b provider preflight correctly classifies JSON parse
failures into the correct failure categories.

Bug: The old parser would report provider_health_invalid_json even when the
backend returned valid JSON, because curl write-out metadata was appended.

Fix: The new _classify_json_parse_failure() uses raw_decode to probe whether
the failure is due to contamination (valid JSON + trailing bytes) vs genuinely
invalid JSON.

Regression tests: test_p0b_health_output_contamination_regression.py
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def fake_provider_preflight_time(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Mock time functions and shrink deadline for fast tests."""
    import time as time_module

    import scripts.lab_common.provider_preflight as provider_preflight
    import scripts.lab_common.provider_preflight_curl as provider_preflight_curl

    now = 0.0
    sleeps: list[float] = []

    def fake_time() -> float:
        return now

    def fake_sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(float(seconds))
        now += max(float(seconds), 0.0)

    # Patch time module globally for both modules
    monkeypatch.setattr(time_module, "time", fake_time)
    monkeypatch.setattr(time_module, "sleep", fake_sleep)
    monkeypatch.setattr(provider_preflight, "PREFLIGHT_RETRY_DEADLINE_SECONDS", 1, raising=False)
    monkeypatch.setattr(provider_preflight_curl, "PREFLIGHT_RETRY_DEADLINE_SECONDS", 1, raising=False)

    return sleeps


def make_curl_result(
    success: bool = True,
    body: str = '{"healthy":true}',
    http_code: int = 200,
    curl_rc: int | None = 0,
    stderr: str = "",
) -> Any:
    """Create a mock CurlResult."""
    result = MagicMock()
    result.success = success
    result.body = body
    result.http_code = http_code
    result.curl_rc = curl_rc
    result.stderr = stderr
    return result


# =============================================================================
# Valid JSON passes
# =============================================================================

class TestValidJsonPasses:
    """Tests for valid JSON responses."""

    def test_provider_health_valid_json_http_200_passes(self) -> None:
        """Valid /api/health/details JSON over HTTP 200 should pass provider preflight."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        valid_body = json.dumps({
            "healthy": True,
            "timestamp": "2026-06-16T10:00:00Z",
            "primary_failure_class": "",
            "provider_enabled": True,
            "dependencies": [
                {"dependency_name": "diagnosis_provider", "status": "available", "phase": "models_list_ok"}
            ]
        })
        mock_curl_result = make_curl_result(success=True, body=valid_body, http_code=200, curl_rc=0)

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig", namespace="k9b",
                    service="k9b-backend", port=8080, artifact_dir=Path(tmpdir),
                )

        assert result.passed is True, f"Expected pass: {result.failure_class} - {result.message}"
        assert result.failure_class is None
        assert "passed" in result.message.lower()


# =============================================================================
# JSON with trailing curl metadata classified as output contamination
# =============================================================================

class TestOutputContamination:
    """Tests for output framing contamination detection."""

    def test_json_with_trailing_curl_metadata_classified_as_output_contaminated(self) -> None:
        """JSON with trailing curl metadata should be classified as provider_health_output_contaminated."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            run_provider_preflight,
        )

        valid_json = json.dumps({"healthy": True, "timestamp": "2026-06-16T10:00:00Z"})
        contaminated_body = f'{valid_json}\nCURL_EXIT=0\nHTTP_CODE=200'
        mock_curl_result = make_curl_result(success=True, body=contaminated_body, http_code=200, curl_rc=0)

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig", namespace="k9b",
                    service="k9b-backend", port=8080, artifact_dir=Path(tmpdir),
                )

        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED
        assert "trailing" in result.message.lower() or "contamination" in result.message.lower()

    def test_json_with_trailing_curl_exit_classified_as_contaminated(self) -> None:
        """JSON followed by CURL_EXIT=0 should be classified as contaminated."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            run_provider_preflight,
        )

        contaminated_body = '{"healthy": true}\nCURL_EXIT=0'
        mock_curl_result = make_curl_result(success=True, body=contaminated_body, http_code=200, curl_rc=0)

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig", namespace="k9b",
                    service="k9b-backend", port=8080, artifact_dir=Path(tmpdir),
                )

        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED


# =============================================================================
# Genuinely invalid JSON fails as invalid_json
# =============================================================================

class TestGenuinelyInvalidJson:
    """Tests for genuinely invalid JSON responses."""

    def test_provider_health_invalid_json_from_backend_fails_invalid_json(self) -> None:
        """Isolated body with malformed JSON should fail as provider_health_invalid_json."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_INVALID_JSON,
            run_provider_preflight,
        )

        invalid_body = '{"healthy": true, "depend'
        mock_curl_result = make_curl_result(success=True, body=invalid_body, http_code=200, curl_rc=0)

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig", namespace="k9b",
                    service="k9b-backend", port=8080, artifact_dir=Path(tmpdir),
                )

        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_INVALID_JSON
        assert "Invalid JSON" in result.message or "json" in result.message.lower()

    def test_provider_health_invalid_json_not_contaminated(self) -> None:
        """Invalid JSON without valid prefix should NOT be classified as contaminated."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_INVALID_JSON,
            run_provider_preflight,
        )

        invalid_body = 'not valid json at all'
        mock_curl_result = make_curl_result(success=True, body=invalid_body, http_code=200, curl_rc=0)

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig", namespace="k9b",
                    service="k9b-backend", port=8080, artifact_dir=Path(tmpdir),
                )

        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_INVALID_JSON
        assert "contamination" not in result.message.lower()


# =============================================================================
# Empty body fails as empty_body
# =============================================================================

class TestEmptyBody:
    """Tests for empty body responses."""

    def test_provider_health_empty_200_body_fails_empty_body(self) -> None:
        """HTTP 200 with empty body should fail as provider_health_empty_body."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_EMPTY_BODY,
            run_provider_preflight,
        )

        mock_curl_result = make_curl_result(success=True, body="", http_code=200, curl_rc=0)

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig", namespace="k9b",
                    service="k9b-backend", port=8080, artifact_dir=Path(tmpdir),
                )

        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_EMPTY_BODY
        assert "empty" in result.message.lower()

    def test_provider_health_whitespace_only_body_fails_empty_body(self) -> None:
        """HTTP 200 with whitespace-only body should fail as provider_health_empty_body."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_EMPTY_BODY,
            run_provider_preflight,
        )

        mock_curl_result = make_curl_result(success=True, body="   \n\t  ", http_code=200, curl_rc=0)

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig", namespace="k9b",
                    service="k9b-backend", port=8080, artifact_dir=Path(tmpdir),
                )

        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_EMPTY_BODY


# =============================================================================
# Non-2xx HTTP fails as http_error (not json error)
# =============================================================================

class TestHttpErrors:
    """Tests for non-2xx HTTP responses."""

    def test_provider_health_http_500_fails_http_error_before_json_contract(self) -> None:
        """HTTP 500 should fail with transport error, not JSON parse error."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        valid_json_body = json.dumps({"error": "internal server error"})
        mock_curl_result = make_curl_result(success=False, body=valid_json_body, http_code=500, curl_rc=0)

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig", namespace="k9b",
                    service="k9b-backend", port=8080, artifact_dir=Path(tmpdir),
                )

        assert result.passed is False
        assert "Invalid JSON" not in result.message
        assert "json" not in result.message.lower() or "valid JSON" in result.message.lower()


# =============================================================================
# Curl failures fail with transport error
# =============================================================================

class TestCurlFailures:
    """Tests for curl transport failures."""

    def test_provider_health_curl_rc_nonzero_fails_transport(self) -> None:
        """Curl with non-zero return code should fail as transport error."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_CONNECTION_FAILED,
            run_provider_preflight,
        )

        mock_curl_result = make_curl_result(success=False, body="connection failed", http_code=0, curl_rc=7)

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig", namespace="k9b",
                    service="k9b-backend", port=8080, artifact_dir=Path(tmpdir),
                )

        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_CONNECTION_FAILED


# =============================================================================
# Unhealthy provider fails correctly
# =============================================================================

class TestUnhealthyProvider:
    """Tests for unhealthy provider responses."""

    def test_provider_health_unhealthy_json_fails_provider_unavailable(self) -> None:
        """Valid JSON with unhealthy provider should fail with provider_unavailable."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_UNAVAILABLE,
            run_provider_preflight,
        )

        unhealthy_body = json.dumps({
            "healthy": False,
            "primary_failure_class": "provider_connection_failed",
            "provider_enabled": True,
            "dependencies": [
                {"dependency_name": "diagnosis_provider", "status": "unavailable", "phase": "not_initialized"}
            ]
        })
        mock_curl_result = make_curl_result(success=True, body=unhealthy_body, http_code=200, curl_rc=0)

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig", namespace="k9b",
                    service="k9b-backend", port=8080, artifact_dir=Path(tmpdir),
                )

        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_UNAVAILABLE


# =============================================================================
# Parser does not parse metadata as JSON
# =============================================================================

class TestParserIsolation:
    """Tests that the parser only uses isolated body for JSON parsing."""

    def test_provider_health_parser_does_not_parse_metadata_as_json(self) -> None:
        """Parser should use isolated body only, not metadata."""
        from scripts.lab_common.provider_preflight import _classify_json_parse_failure

        metadata = '{"http_code": 200, "curl_exit": 0}'
        invalid_body = f'not valid json{metadata}'

        try:
            json.loads(invalid_body)
            pytest.fail("Should have raised JSONDecodeError")
        except json.JSONDecodeError as exc:
            failure_class, message, _ = _classify_json_parse_failure(invalid_body, exc)

        assert failure_class == "provider_health_invalid_json"
        assert "contamination" not in message.lower()
