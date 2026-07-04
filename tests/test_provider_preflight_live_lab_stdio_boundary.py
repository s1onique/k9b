"""Regression tests for provider preflight live lab stdio boundary.

These tests verify that the provider preflight correctly separates stdout and stderr,
and only passes the provider-health body to the classifier.

The key boundary contract:
1. provider_health body (stdout) -> _classify_provider_health_body()
2. curl metadata (stderr/returncode) -> diagnostics only, NOT passed to classifier

This test file addresses ACT-P0B-LIVE-PREFLIGHT-STDIO-SEPARATION01.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scripts.lab_common.provider_preflight import (
    FAILURE_PROVIDER_HEALTH_EMPTY_BODY,
    FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
    _classify_provider_health_body,
)


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


class TestStdioBoundaryClassifier:
    """Tests for _classify_provider_health_body() boundary enforcement.

    These tests verify the classifier itself is strict and doesn't accept
    contamination that would indicate stream mixing.
    """

    def test_clean_json_only_passes(self) -> None:
        """Clean JSON without any suffix should pass."""
        body = '{"provider_enabled": false}'
        failure_class, payload, detail = _classify_provider_health_body(body)

        assert failure_class is None
        assert payload is not None
        assert isinstance(payload, dict)
        assert payload.get("provider_enabled") is False

    def test_json_with_known_successful_curl_envelope_passes(self) -> None:
        """JSON with CURL_EXIT=0 and HTTP_CODE=200 is accepted envelope."""
        body = '{"provider_enabled": false}\nCURL_EXIT=0\nHTTP_CODE=200'
        failure_class, payload, detail = _classify_provider_health_body(body)

        assert failure_class is None
        assert payload is not None

    def test_json_with_stderr_block_envelope_passes(self) -> None:
        """JSON with STDERR_BLOCK + CURL_EXIT=0 + HTTP_CODE=200 is accepted envelope."""
        body = '{"provider_enabled": false}\nSTDERR_BLOCK\nCURL_EXIT=0\nHTTP_CODE=200'
        failure_class, payload, detail = _classify_provider_health_body(body)

        assert failure_class is None
        assert payload is not None

    def test_json_with_stderr_block_and_debug_noise_passes(self) -> None:
        """JSON with STDERR_BLOCK + debug noise + CURL_EXIT=0 + HTTP_CODE=200 is accepted."""
        body = (
            '{"provider_enabled": false}\n'
            'STDERR_BLOCK\n'
            'debug noise from curl wrapper\n'
            'CURL_EXIT=0\n'
            'HTTP_CODE=200\n'
        )
        failure_class, payload, detail = _classify_provider_health_body(body)

        assert failure_class is None
        assert payload is not None

    def test_json_with_trailing_stderr_block_fails(self) -> None:
        """JSON with trailing STDERR_BLOCK (without valid envelope) fails.

        This is the critical regression test: if stdout contains STDERR_BLOCK
        after the JSON without proper curl envelope, it must be rejected.
        """
        body = '{"provider_enabled": false}\nSTDERR_BLOCK'
        failure_class, payload, detail = _classify_provider_health_body(body)

        assert failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED
        assert payload is None
        assert "contamination" in detail.lower()

    def test_json_with_trailing_stderr_and_extra_fails(self) -> None:
        """JSON with trailing STDERR_BLOCK + extra text fails as contamination."""
        body = '{"provider_enabled": false}\nSTDERR_BLOCK\nsomething'
        failure_class, payload, detail = _classify_provider_health_body(body)

        assert failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED
        assert payload is None

    def test_json_with_trailing_unknown_metadata_fails(self) -> None:
        """JSON with trailing unknown metadata fails as contamination."""
        body = '{"provider_enabled": false}\nUNKNOWN_METADATA=value'
        failure_class, payload, detail = _classify_provider_health_body(body)

        assert failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED
        assert payload is None

    def test_empty_body_fails(self) -> None:
        """Empty body fails as empty_body."""
        body = ""
        failure_class, payload, detail = _classify_provider_health_body(body)

        assert failure_class == FAILURE_PROVIDER_HEALTH_EMPTY_BODY
        assert payload is None


class TestStdioBoundaryOrchestration:
    """Tests for the orchestration layer that passes curl results to classifier.

    These tests verify that the curl wrapper correctly separates stdout and stderr,
    and only passes the body (not stderr/curl metadata) to the classifier.
    """

    def test_clean_stdout_plus_stderr_remains_clean(self) -> None:
        """Clean body on stdout with stderr present should classify normally.

        This is the core regression test: the wrapper must not pass
        stderr content to the classifier as part of the body.
        """
        from scripts.lab_common.provider_preflight import run_provider_preflight

        # Clean provider-health JSON on stdout
        clean_body = '{"provider_enabled": false}'
        mock_curl_result = make_curl_result(
            success=True,
            body=clean_body,
            http_code=200,
            curl_rc=0,
            stderr="some debug noise",  # stderr should NOT contaminate body
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
                    require_provider_configured=False,
                    require_provider_invocation_possible=False,
                )

        # Should pass because body is clean
        assert result.passed is True
        assert result.failure_class is None

    def test_curl_metadata_not_in_body(self) -> None:
        """Curl metadata should be in diagnostics, not in body passed to classifier."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        # Clean body - no curl metadata embedded
        clean_body = '{"provider_enabled": false}'
        mock_curl_result = make_curl_result(
            success=True,
            body=clean_body,
            http_code=200,
            curl_rc=0,
            stderr="",  # curl metadata in separate field
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
                    require_provider_configured=False,
                    require_provider_invocation_possible=False,
                )

        # Should pass - no contamination
        assert result.passed is True
        assert result.failure_class is None

    def test_physically_contaminated_stdout_still_fails(self) -> None:
        """If stdout body physically contains STDERR_BLOCK, it must fail.

        This protects the boundary - we don't want to relax the classifier
        to accept contamination that indicates stream mixing.
        """
        from scripts.lab_common.provider_preflight import run_provider_preflight

        # Physically contaminated: JSON + STDERR_BLOCK without proper envelope
        contaminated_body = '{"provider_enabled": false}\nSTDERR_BLOCK\nsomething'
        mock_curl_result = make_curl_result(
            success=True,
            body=contaminated_body,
            http_code=200,
            curl_rc=0,
            stderr="",
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
                    require_provider_configured=False,
                    require_provider_invocation_possible=False,
                )

        # Must fail as contamination
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED

    def test_curl_failure_preserves_diagnostics(self) -> None:
        """Non-zero curl exit should preserve diagnostics, not synthesize fake JSON."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        # Empty body on curl failure
        mock_curl_result = make_curl_result(
            success=False,
            body="",
            http_code=0,
            curl_rc=7,  # connection refused
            stderr="connection refused",
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
                    require_provider_configured=False,
                    require_provider_invocation_possible=False,
                )

        # Should fail, not synthesize fake JSON
        assert result.passed is False
        # curl_rc=7 should be classified appropriately
        assert result.failure_class is not None
        assert "connection" in result.message.lower() or "curl_rc" in result.message.lower()

    def test_stderr_content_not_appended_to_body(self) -> None:
        """Stderr content must not be appended to body in the wrapper layer."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        # Clean JSON body
        clean_body = '{"provider_enabled": false}'
        # stderr with curl-like content
        stderr_with_metadata = "curl: (7) Failed to connect\nSTDERR_BLOCK"
        mock_curl_result = make_curl_result(
            success=False,
            body=clean_body,  # body is clean, stderr has noise
            http_code=0,
            curl_rc=7,
            stderr=stderr_with_metadata,
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
                    require_provider_configured=False,
                    require_provider_invocation_possible=False,
                )

        # Should fail due to curl failure, not contamination
        assert result.passed is False
        # Must NOT be contamination (which would indicate stderr was mixed into body)
        assert result.failure_class != FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED


class TestEnvelopeContract:
    """Tests for the curl envelope contract.

    These tests document the known envelope patterns that are accepted.
    They serve as regression guards against changing the contract.
    """

    def test_accepted_envelope_patterns(self) -> None:
        """Known successful curl envelope patterns must be accepted."""
        accepted_patterns = [
            '{"healthy": true}',  # clean
            '{"healthy": true}\nCURL_EXIT=0\nHTTP_CODE=200',  # basic envelope
            '{"healthy": true}\nSTDERR_BLOCK\nCURL_EXIT=0\nHTTP_CODE=200',  # with stderr block
            '{"healthy": true}\nSTDERR_BLOCK\ndebug noise\nCURL_EXIT=0\nHTTP_CODE=200',  # with debug noise
            '\n  {"healthy": true}\nCURL_EXIT=0\nHTTP_CODE=200\n  ',  # with whitespace
        ]

        for body in accepted_patterns:
            failure_class, payload, detail = _classify_provider_health_body(body)
            assert failure_class is None, f"Accepted pattern failed: {body!r}"
            assert payload is not None

    def test_rejected_envelope_patterns(self) -> None:
        """Known problematic patterns must be rejected as contamination."""
        rejected_patterns = [
            ('{"healthy": true}\nSTDERR_BLOCK', "trailing STDERR_BLOCK without envelope"),
            ('{"healthy": true}\nSTDERR_BLOCK\nextra', "trailing STDERR_BLOCK with extra"),
            ('{"healthy": true}\nUNKNOWN=value', "unknown metadata"),
            ('{"healthy": true}\nCURL_EXIT=1\nHTTP_CODE=200', "failed curl"),
            ('{"healthy": true}\nCURL_EXIT=0\nHTTP_CODE=500', "failed HTTP"),
        ]

        for body, description in rejected_patterns:
            failure_class, payload, detail = _classify_provider_health_body(body)
            assert failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED, (
                f"Pattern should be rejected: {description} - body: {body!r}"
            )
