"""Regression tests for provider health invalid JSON classification.

These tests verify that:
- HTTP 200 with invalid JSON is classified as provider_health_invalid_json
- Concatenated JSON (e.g., {}{}) is correctly classified as invalid
- Valid JSON passes cleanly
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
    """Mock time functions and shrink deadline for fast tests.

    Uses an advancing fake clock that only advances when sleep is called.
    This allows the deadline check (time.time() < deadline) to work correctly
    while avoiding real wall-clock waits.

    Also patches PREFLIGHT_RETRY_DEADLINE_SECONDS to 1s so tests don't wait
    for the full 60s retry window.

    Patches both provider_preflight and provider_preflight_curl since the split
    modules each have their own time imports.
    """
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

    # Patch time module globally for all imports
    monkeypatch.setattr(time_module, "time", fake_time)
    monkeypatch.setattr(time_module, "sleep", fake_sleep)

    # Patch deadline in both modules (split modules each have their own imports)
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


class TestProviderHealthInvalidJsonClassification:
    """Tests for provider_health_invalid_json classification."""

    def test_2xx_invalid_json_classified_as_invalid_json(self) -> None:
        """HTTP 200 with invalid JSON should be classified as provider_health_invalid_json."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_INVALID_JSON,
            run_provider_preflight,
        )

        # Invalid JSON: not a valid JSON document
        invalid_json_body = "not valid json"
        mock_curl_result = make_curl_result(
            success=True,
            body=invalid_json_body,
            http_code=200,
            curl_rc=0,
        )

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig",
                    namespace="k9b",
                    service="k9b-backend",
                    port=8080,
                    artifact_dir=Path(tmpdir),
                )

        # Should fail with invalid_json classification
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_INVALID_JSON
        assert "Invalid JSON" in result.message or "json" in result.message.lower()

    def test_concatenated_json_classified_as_invalid_json(self) -> None:
        """Concatenated JSON (e.g., {}{}) should be classified as provider_health_invalid_json."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_INVALID_JSON,
            run_provider_preflight,
        )

        # Two JSON objects concatenated - this causes "Extra data" error
        concatenated_body = '{"healthy":true}{"extra":"data"}'
        mock_curl_result = make_curl_result(
            success=True,
            body=concatenated_body,
            http_code=200,
            curl_rc=0,
        )

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig",
                    namespace="k9b",
                    service="k9b-backend",
                    port=8080,
                    artifact_dir=Path(tmpdir),
                )

        # Should fail with invalid_json classification
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_INVALID_JSON

    def test_extra_data_after_json_classified_as_contaminated(self) -> None:
        """JSON with trailing non-whitespace data should be classified as output_contaminated."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            run_provider_preflight,
        )

        # Valid JSON followed by trailing text
        trailing_body = '{"healthy":true}trailing text here'
        mock_curl_result = make_curl_result(
            success=True,
            body=trailing_body,
            http_code=200,
            curl_rc=0,
        )

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig",
                    namespace="k9b",
                    service="k9b-backend",
                    port=8080,
                    artifact_dir=Path(tmpdir),
                )

        # Should fail with output_contaminated classification (valid JSON with prefix/suffix)
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED

    def test_prefix_contamination_classified_as_contaminated(self) -> None:
        """JSON with log prefix before valid JSON should be classified as output_contaminated."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            run_provider_preflight,
        )

        # Log prefix followed by valid JSON
        prefix_body = 'INFO starting log\n{"healthy":true}'
        mock_curl_result = make_curl_result(
            success=True,
            body=prefix_body,
            http_code=200,
            curl_rc=0,
        )

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig",
                    namespace="k9b",
                    service="k9b-backend",
                    port=8080,
                    artifact_dir=Path(tmpdir),
                )

        # Should fail with output_contaminated classification
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED

    def test_prefix_and_suffix_contamination_classified_as_contaminated(self) -> None:
        """JSON with both log prefix and suffix should be classified as output_contaminated."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            run_provider_preflight,
        )

        # Log prefix and suffix around valid JSON
        both_body = 'INFO starting\n{"healthy":true}\nINFO done'
        mock_curl_result = make_curl_result(
            success=True,
            body=both_body,
            http_code=200,
            curl_rc=0,
        )

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig",
                    namespace="k9b",
                    service="k9b-backend",
                    port=8080,
                    artifact_dir=Path(tmpdir),
                )

        # Should fail with output_contaminated classification
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED

    def test_valid_json_passes(self) -> None:
        """Valid JSON should allow provider preflight to continue."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        # Valid health details JSON with provider available
        valid_body = json.dumps({
            "healthy": True,
            "primary_failure_class": "",
            "provider_enabled": True,
            "dependencies": [
                {"dependency_name": "diagnosis_provider", "status": "available", "phase": "models_list_ok"}
            ]
        })
        mock_curl_result = make_curl_result(
            success=True,
            body=valid_body,
            http_code=200,
            curl_rc=0,
        )

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig",
                    namespace="k9b",
                    service="k9b-backend",
                    port=8080,
                    artifact_dir=Path(tmpdir),
                )

        # Should pass (valid JSON allows preflight to continue)
        assert result.passed is True, f"Expected pass but got: {result.failure_class} - {result.message}"

    def test_valid_json_with_newlines_passes(self) -> None:
        """Valid JSON with newlines should pass."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        # Multi-line valid JSON
        valid_body = json.dumps({
            "healthy": True,
            "primary_failure_class": "",
            "provider_enabled": True,
            "dependencies": [
                {"dependency_name": "diagnosis_provider", "status": "available", "phase": "models_list_ok"}
            ]
        }, indent=2)
        mock_curl_result = make_curl_result(
            success=True,
            body=valid_body,
            http_code=200,
            curl_rc=0,
        )

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig",
                    namespace="k9b",
                    service="k9b-backend",
                    port=8080,
                    artifact_dir=Path(tmpdir),
                )

        # Should pass
        assert result.passed is True, f"Expected pass but got: {result.failure_class} - {result.message}"

    def test_duplicate_json_serialized_object_classified_invalid(self) -> None:
        """Duplicate serialized objects (JSON array with two objects) should be invalid."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_INVALID_JSON,
            run_provider_preflight,
        )

        # Two JSON arrays concatenated
        duplicate_body = '[{"a":1}][{"b":2}]'
        mock_curl_result = make_curl_result(
            success=True,
            body=duplicate_body,
            http_code=200,
            curl_rc=0,
        )

        with patch(
            "scripts.lab_common.provider_preflight._curl_service_pod_with_retry",
            return_value=mock_curl_result,
        ), patch(
            "scripts.lab_common.provider_preflight._curl_exec_pod_with_retry",
            return_value=mock_curl_result,
        ):
            with TemporaryDirectory() as tmpdir:
                result = run_provider_preflight(
                    kubeconfig="/fake/kubeconfig",
                    namespace="k9b",
                    service="k9b-backend",
                    port=8080,
                    artifact_dir=Path(tmpdir),
                )

        # Should fail with invalid_json classification
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_INVALID_JSON


class TestHealthDetailsJsonValidity:
    """Tests for /api/health/details JSON validity."""

    def test_health_details_returns_single_json_object(self) -> None:
        """Health details response must be exactly one JSON object, no trailing data."""
        from k8s_diag_agent.ui.api_health_details import handle_health_details

        class MockHandler:
            def __init__(self) -> None:
                self.sent_body: str = ""
                self.sent_code: int = 0

            def _send_json(self, data: dict, code: int = 200) -> None:
                self.sent_body = json.dumps(data)
                self.sent_code = code

        with patch(
            "k8s_diag_agent.ui.api_health_details._get_runtime_health_status",
            return_value={"healthy": True, "error": None},
        ), patch(
            "k8s_diag_agent.ui.api_health_details._get_provider_health_status",
            return_value={"available": True, "error": None, "phase": "success", "error_class": "provider_available"},
        ):
            handler = MockHandler()
            handle_health_details(handler)

        # Response must be valid JSON
        parsed = json.loads(handler.sent_body)
        assert isinstance(parsed, dict), "Health details must be a JSON object"

        # Must be exactly one JSON document (no trailing non-whitespace)
        raw_body = handler.sent_body
        # Strip trailing whitespace and check no extra content
        stripped = raw_body.rstrip()
        # Parse should consume entire string
        json.loads(stripped)

    def test_health_details_json_has_required_fields(self) -> None:
        """Health details JSON must have all required fields."""
        from k8s_diag_agent.ui.api_health_details import handle_health_details

        class MockHandler:
            def __init__(self) -> None:
                self.sent_body: str = ""
                self.sent_code: int = 0

            def _send_json(self, data: dict, code: int = 200) -> None:
                self.sent_body = json.dumps(data)
                self.sent_code = code

        with patch(
            "k8s_diag_agent.ui.api_health_details._get_runtime_health_status",
            return_value={"healthy": True, "error": None},
        ), patch(
            "k8s_diag_agent.ui.api_health_details._get_provider_health_status",
            return_value={"available": True, "error": None, "phase": "success", "error_class": "provider_available"},
        ):
            handler = MockHandler()
            handle_health_details(handler)

        parsed = json.loads(handler.sent_body)

        # Required fields for provider preflight
        assert "healthy" in parsed
        assert "primary_failure_class" in parsed
        assert "dependencies" in parsed


class TestLeadingWhitespaceHandling:
    """Regression tests for leading whitespace handling.

    These tests verify that leading whitespace is properly handled:
    - Leading whitespace + clean JSON proceeds to semantic evaluation
    - Leading whitespace + JSON + trailing contamination is still contamination
    """

    def test_leading_whitespace_clean_json_evaluates_semantically(self) -> None:
        """Leading whitespace + clean JSON should proceed to semantic evaluation."""
        from scripts.lab_common.provider_preflight_health import (
            _classify_provider_health_body,
        )

        body = '\n  {"provider_status":"disabled","provider_enabled":false}'
        failure_class, payload, detail = _classify_provider_health_body(body)

        assert failure_class is None
        assert payload == {"provider_status": "disabled", "provider_enabled": False}

    def test_leading_whitespace_then_trailing_curl_metadata_is_contaminated(self) -> None:
        """Leading whitespace + JSON + CURL_EXIT/HTTP_CODE is contamination."""
        from scripts.lab_common.provider_preflight_health import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            _classify_provider_health_body,
        )

        body = '\n  {"provider_status":"available"}\nCURL_EXIT=0\nHTTP_CODE=200\n'
        failure_class, payload, detail = _classify_provider_health_body(body)

        assert failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED
        assert payload is None

    def test_leading_whitespace_with_concatenated_json_is_invalid(self) -> None:
        """Leading whitespace + concatenated JSON should be invalid_json."""
        from scripts.lab_common.provider_preflight_health import (
            FAILURE_PROVIDER_HEALTH_INVALID_JSON,
            _classify_provider_health_body,
        )

        body = '\n  {"a":1}{"b":2}'
        failure_class, payload, detail = _classify_provider_health_body(body)

        assert failure_class == FAILURE_PROVIDER_HEALTH_INVALID_JSON
        assert payload is None

    def test_leading_whitespace_with_prefix_contamination_is_contaminated(self) -> None:
        """Leading non-whitespace text + JSON should be contamination."""
        from scripts.lab_common.provider_preflight_health import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            _classify_provider_health_body,
        )

        body = 'INFO starting\n  {"healthy":true}'
        failure_class, payload, detail = _classify_provider_health_body(body)

        assert failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED
        assert payload is None
