"""Regression tests for P0b provider health - contamination rejection.

These tests verify that unknown/unrecognized suffix patterns still fail as contamination
and that the distinction between clean and contaminated payloads is maintained.
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


class TestUnknownSuffixStillFails:
    """Tests that unknown/unrecognized suffix patterns still fail as contamination."""

    def test_unknown_suffix_is_still_contamination(self) -> None:
        """JSON with unknown trailing text should still fail as contamination."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            run_provider_preflight,
        )

        body = '{"healthy":true,"provider_enabled":true}\nNOT_A_CURL_ENVELOPE\n'

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

        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED


class TestCleanVsContaminatedPayloads:
    """Tests that verify the distinction between clean and contaminated payloads."""

    def test_contaminated_disabled_payload_still_fails(self) -> None:
        """Contaminated payload with diagnosis_provider_enabled=false should fail contamination."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            run_provider_preflight,
        )

        body = '{"diagnosis_provider_enabled": false}\nUNKNOWN_SUFFIX\n'

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

        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED

    def test_contaminated_available_payload_still_fails(self) -> None:
        """Contaminated payload with unknown suffix should fail contamination."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            run_provider_preflight,
        )

        body = '{"provider_status": "available", "healthy": true}\nUNKNOWN_SUFFIX\n'

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

        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED

    def test_clean_disabled_payload_still_returns_provider_disabled_required(self) -> None:
        """Clean JSON with diagnosis_provider_enabled=false should return provider_disabled_required."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_DISABLED_REQUIRED,
            run_provider_preflight,
        )

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

        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_DISABLED_REQUIRED
