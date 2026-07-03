"""Regression tests for provider health output contamination classification.

These tests verify that contaminated provider-health output is classified correctly:
- Valid JSON with trailing non-whitespace data is output_contaminated
- Valid JSON with leading non-whitespace prefix is output_contaminated
- Leading whitespace + JSON + curl metadata is output_contaminated
"""

from __future__ import annotations

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


class TestProviderHealthOutputContamination:
    """Tests for provider_health_output_contaminated classification."""

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


class TestLeadingWhitespaceContamination:
    """Regression tests for leading whitespace + contamination scenarios.

    These tests verify that leading whitespace + JSON + contamination markers
    are properly classified as output_contaminated.
    """

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
