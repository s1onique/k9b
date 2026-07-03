"""Regression tests for P0b provider health - known curl envelope acceptance.

The fix (2026-07-03) moved envelope extraction BEFORE strict JSON classification.
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


class TestKnownCurlEnvelopeAccepted:
    """Known curl envelope patterns should be accepted as NON-FATAL."""

    def test_live_log_fixture_json_with_trailing_curl_metadata_passes(self) -> None:
        """Exact fixture from live lab: valid JSON + curl metadata should PASS."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        live_fixture = (
            '{"healthy": true, '
            '"primary_failure_class": "", "provider_enabled": true, '
            '"provider_configured": true, '
            '"dependencies": [{"dependency_name": "diagnosis_provider", '
            '"status": "available", "phase": "models_list_ok"}]}'
            '\nCURL_EXIT=0\nHTTP_CODE=200'
        )

        mock_curl_result = make_curl_result(success=True, body=live_fixture, http_code=200, curl_rc=0)

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

        assert result.passed is True, f"Expected pass but got: {result.message}"
        assert result.failure_class is None

    def test_stderr_block_envelope_is_accepted(self) -> None:
        """JSON with STDERR_BLOCK envelope should be accepted."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        body = (
            '{"healthy": true, "provider_enabled": true, '
            '"provider_configured": true, '
            '"provider_status": "available", "phase": "models_list_ok", '
            '"primary_failure_class": "", "dependencies": []}'
            '\nSTDERR_BLOCK\n'
            'CURL_EXIT=0\n'
            'HTTP_CODE=200\n'
        )

        mock_curl_result = make_curl_result(success=True, body=body, http_code=200, curl_rc=0)

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

        assert result.passed is True
        assert result.failure_class is None

    def test_full_curl_envelope_suffix_is_accepted(self) -> None:
        """JSON with full curl envelope should pass."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        body = (
            '{"healthy":true,"provider_enabled":true,"provider_configured":true,'
            '"provider_status":"available","phase":"models_list_ok",'
            '"primary_failure_class":""}'
            "\nSTDERR_BLOCK\n"
            "CURL_EXIT=0\n"
            "HTTP_CODE=200\n"
        )

        mock_curl_result = make_curl_result(success=True, body=body, http_code=200, curl_rc=0)

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

        assert result.passed is True
        assert result.failure_class is None

    def test_stderr_block_with_debug_noise_is_accepted(self) -> None:
        """JSON with STDERR_BLOCK containing debug noise should be accepted."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        body = (
            '{"healthy":true,"provider_enabled":true,"provider_configured":true,'
            '"provider_status":"available","phase":"models_list_ok",'
            '"primary_failure_class":""}'
            '\nSTDERR_BLOCK\n'
            'debug noise from curl wrapper\n'
            'CURL_EXIT=0\n'
            'HTTP_CODE=200\n'
        )

        mock_curl_result = make_curl_result(success=True, body=body, http_code=200, curl_rc=0)

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

        assert result.passed is True
        assert result.failure_class is None
