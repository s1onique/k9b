"""Regression tests for P0b provider health - semantic evaluation after envelope extraction.

These tests prove that envelope extraction enables semantic evaluation.
Known curl envelope is stripped, and semantic evaluation proceeds.
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


class TestEnvelopeExtractionThenSemanticEvaluation:
    """Tests for wire-format classification contract.

    Known successful curl metadata (CURL_EXIT=0, HTTP_CODE=200) is accepted as
    transport-envelope metadata. Unknown suffixes, failed curl exits, non-200
    HTTP codes, and concatenated JSON remain wire-format failures.
    """

    def test_known_envelope_with_disabled_provider_returns_semantic_failure(self) -> None:
        """Known curl envelope with disabled provider returns semantic failure.

        Wire-format contract (APF): Known successful curl envelope is accepted as
        transport metadata, not JSON contamination. Semantic evaluation proceeds
        and correctly identifies provider_disabled_required.
        """
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_DISABLED_REQUIRED,
            run_provider_preflight,
        )

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

        # Wire-format passed (envelope accepted), semantic evaluation correctly
        # identifies provider_disabled_required
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_DISABLED_REQUIRED

    def test_known_envelope_with_available_provider_passes(self) -> None:
        """Known curl envelope with available provider passes preflight.

        Wire-format contract (APF): Known successful curl envelope is accepted as
        transport metadata, not JSON contamination. Semantic evaluation proceeds
        and correctly identifies healthy provider - preflight PASSES.
        """
        from scripts.lab_common.provider_preflight import run_provider_preflight

        body = (
            '{"provider_status": "available", "phase": "models_list_ok", '
            '"healthy": true, '
            '"primary_failure_class": "", "provider_enabled": true, '
            '"provider_configured": true, "dependencies": []}'
            '\nCURL_EXIT=0\nHTTP_CODE=200\n'
        )

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

        # Wire-format passed (envelope accepted), semantic evaluation correctly
        # identifies healthy provider - preflight PASSES
        assert result.passed is True
        assert result.failure_class is None

    def test_unknown_suffix_with_disabled_provider_returns_contamination(self) -> None:
        """Unknown suffix with disabled provider should return contamination.

        Unknown suffix means true contamination - semantic evaluation should NOT happen.
        """
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


class TestBadCurlMetadataGuardrail:
    """Guardrail tests for failed curl metadata.

    Known envelope framing is non-fatal for JSON classification,
    but failed curl metadata must not be silently ignored.

    The curl_result fields (success, curl_rc, http_code) are authoritative
    and checked BEFORE the body reaches _evaluate_health_response().
    """

    def test_failed_curl_is_rejected_early(self) -> None:
        """Failed curl (curl_exit != 0) should be rejected before envelope parsing."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        body = (
            '{"healthy":true,"provider_enabled":true,"provider_configured":true,'
            '"provider_status":"available","phase":"models_list_ok",'
            '"primary_failure_class":""}'
            "\nSTDERR_BLOCK\n"
            "curl timeout\n"
            "CURL_EXIT=28\n"
            "HTTP_CODE=000\n"
        )

        mock_curl_result = make_curl_result(
            success=False,
            body=body,
            http_code=0,
            curl_rc=28,
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
        assert result.message is not None
        assert result.failure_class is not None
        assert "timeout" in result.message.lower() or "curl" in result.failure_class.lower()

    def test_non_2xx_http_code_is_rejected_early(self) -> None:
        """Non-2xx HTTP code should be rejected before envelope parsing."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        body = (
            '{"healthy":false,"error":"internal error"}'
            "\nCURL_EXIT=0\n"
            "HTTP_CODE=500\n"
        )

        mock_curl_result = make_curl_result(
            success=True,
            body=body,
            http_code=500,
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
