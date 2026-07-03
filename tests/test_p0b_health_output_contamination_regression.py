"""Regression tests for P0b provider health output framing contamination.

These tests cover the regression cases and failure message precision.
"""

from __future__ import annotations

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


class TestLiveLogRegression:
    """Regression tests from actual live lab failures."""

    def test_live_log_fixture_json_with_trailing_metadata(self) -> None:
        """Exact fixture from live lab: valid JSON + curl metadata."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            run_provider_preflight,
        )

        # Exact format from live lab that caused "Extra data" failure
        live_fixture = (
            '{"timestamp": "2026-06-16T10:00:00Z", "healthy": true, '
            '"primary_failure_class": "", "provider_enabled": true, '
            '"dependencies": [{"dependency_name": "diagnosis_provider", '
            '"status": "available", "phase": "models_list_ok"}]}'
            '\nCURL_EXIT=0\nHTTP_CODE=200'
        )

        mock_curl_result = make_curl_result(
            success=True,
            body=live_fixture,
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

        # Should be classified as output contamination, not invalid_json
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED
        # Message should include trailing preview
        assert "CURL_EXIT" in result.message or "HTTP_CODE" in result.message


class TestFailureMessages:
    """Tests for precise failure messages."""

    def test_p0b_failure_message_includes_precise_failure_class(self) -> None:
        """Failure message should include the precise failure class name."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            run_provider_preflight,
        )

        valid_json = '{"healthy": true}'
        contaminated_body = f'{valid_json}\nCURL_EXIT=0\nHTTP_CODE=200'

        mock_curl_result = make_curl_result(
            success=True,
            body=contaminated_body,
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

        # Failure class should be precise
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED
        # Message should include diagnostic info
        assert "trailing" in result.message.lower() or "contamination" in result.message.lower()
        # Should NOT be generic invalid_json
        assert "invalid_json" not in result.failure_class or "contamination" in result.failure_class


class TestProviderDisabledRegression:
    """Regression tests for provider_disabled_required classification.

    These tests ensure that contaminated payloads containing provider_disabled
    fields are classified as provider_health_output_contaminated, NOT as
    provider_disabled_required.
    """

    def test_contaminated_disabled_payload_never_returns_provider_disabled_required(self) -> None:
        """Contaminated payload with diagnosis_provider_enabled=false should return contamination."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            run_provider_preflight,
        )

        # This body contains valid JSON followed by curl metadata
        body = '{"diagnosis_provider_enabled": false}\nCURL_EXIT=0\nHTTP_CODE=200\n'

        mock_curl_result = make_curl_result(
            success=True,
            body=body,
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

        # Must be contamination, NOT provider_disabled_required
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED

    def test_contaminated_available_payload_never_passes(self) -> None:
        """Contaminated payload with provider_status=available should return contamination."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            run_provider_preflight,
        )

        # This body contains valid JSON followed by curl metadata
        body = '{"provider_status": "available", "healthy": true}\nCURL_EXIT=0\nHTTP_CODE=200\n'

        mock_curl_result = make_curl_result(
            success=True,
            body=body,
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

        # Must be contamination, NOT passed
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED

    def test_clean_disabled_payload_still_returns_provider_disabled_required(self) -> None:
        """Clean JSON with diagnosis_provider_enabled=false should return provider_disabled_required."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_DISABLED_REQUIRED,
            run_provider_preflight,
        )

        # This body is exactly one clean JSON document (no trailing metadata)
        body = '{"diagnosis_provider_enabled": false}'

        mock_curl_result = make_curl_result(
            success=True,
            body=body,
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

        # Clean JSON with disabled provider should fail with provider_disabled_required
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_DISABLED_REQUIRED
        # Must NOT be contamination (proves semantic evaluation happened)
        assert "contamination" not in result.failure_class
