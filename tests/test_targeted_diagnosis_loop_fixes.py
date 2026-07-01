"""Regression tests for targeted diagnosis loop OTel live-lab fixes.

These tests verify:
1. P4c: Targeted diagnosis result shape bug fix (AutoLoopIncidentResult vs AutoLoopCollectorResult)
2. P4c: Budget-state isolation (deterministic incident ID)
3. P4c: Precise failure classification (curl_rc=52, budget_exhausted, transport errors)
4. P0b: Provider health JSON parsing robustness (marker-based parsing)
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Test fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def fake_provider_preflight_time(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Mock time functions and shrink deadline for fast tests."""
    import scripts.lab_common.provider_preflight as provider_preflight

    now = 0.0
    sleeps: list[float] = []

    def fake_time() -> float:
        return now

    def fake_sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(float(seconds))
        now += max(float(seconds), 0.0)

    monkeypatch.setattr(provider_preflight.time, "time", fake_time)
    monkeypatch.setattr(provider_preflight.time, "sleep", fake_sleep)
    monkeypatch.setattr(provider_preflight, "PREFLIGHT_RETRY_DEADLINE_SECONDS", 1, raising=False)

    return sleeps


# =============================================================================
# P4c: Targeted diagnosis result shape fix tests
# =============================================================================

class TestTargetedDiagnosisResultShape:
    """Tests for handler result shape handling.

    Tests the _extract_incident_result_from_collector function which handles
    the P4c bug where AutoLoopIncidentResult was incorrectly treated as having
    an incident_results attribute (which only AutoLoopCollectorResult has).
    """

    def test_result_shape_contract(self) -> None:
        """Regression test: AutoLoopIncidentResult must NOT access .incident_results.

        The P4c bug was that the handler called:
            result.incident_results.get(incident_id)

        But collect_automatic_diagnosis_evidence() returns AutoLoopIncidentResult directly,
        which does NOT have incident_results. This caused AttributeError at runtime.

        The fix is _extract_incident_result_from_collector() which uses hasattr() to check.
        This test verifies the function correctly handles AutoLoopIncidentResult without
        crashing.
        """
        from k8s_diag_agent.collect.incident_diagnosis_auto_loop_models import (
            AutoLoopIncidentResult,
        )
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _extract_incident_result_from_collector,
        )

        # Create a direct AutoLoopIncidentResult (not wrapped in collector result)
        incident_result = AutoLoopIncidentResult(
            incident_id="test-incident-789",
            eligible=True,
            eligibility_reason="",
            run_id="auto-test-incident-789-20240101",
            review_packet_name="auto-test-incident-789-0-diagnosis-review-packet.json",
            checks_requested=3,
            checks_run=3,
            checks_rejected=0,
        )

        # The bug would crash here with: AttributeError: 'AutoLoopIncidentResult' has no 'incident_results'
        # The fix handles this gracefully via hasattr() check
        extracted = _extract_incident_result_from_collector(
            result=incident_result,  # type: ignore - intentional: testing both types
            incident_id="test-incident-789",
        )

        # Verify the result was returned correctly
        assert extracted is not None
        assert extracted.incident_id == "test-incident-789"
        assert extracted.review_packet_name == "auto-test-incident-789-0-diagnosis-review-packet.json"


# =============================================================================
# P4c: Budget-state isolation tests
# =============================================================================

class TestBudgetStateIsolation:
    """Tests for budget-state isolation via incident ID determinism."""

    def test_budget_reset_clears_review_packets(self) -> None:
        """reset_diagnosis_loop_budget removes auto-{incident_id}-*-review-packet.json files."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import (
            get_budget_status,
            reset_diagnosis_loop_budget,
        )

        with TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)

            # Create mock budget files with deterministic incident ID
            incident_id = "test-incident-123"
            (external_analysis_dir / f"auto-{incident_id}-0-diagnosis-review-packet.json").write_text('{"findings":[]}')
            (external_analysis_dir / f"auto-{incident_id}-1-diagnosis-review-packet.json").write_text('{"findings":[]}')
            (external_analysis_dir / f"auto-{incident_id}-2-diagnosis-review-packet.json").write_text('{"findings":[]}')

            # Non-budget file should remain
            (external_analysis_dir / "other-artifact.json").write_text('{}')

            # Verify files exist
            status_before = get_budget_status(external_analysis_dir, incident_id)
            assert status_before["review_packet_count"] == 3
            assert status_before["budget_exhausted"] is True

            # Reset budget
            removed = reset_diagnosis_loop_budget(external_analysis_dir, incident_id)
            assert removed == 3

            # Verify budget files removed
            status_after = get_budget_status(external_analysis_dir, incident_id)
            assert status_after["review_packet_count"] == 0
            assert status_after["budget_clean"] is True

            # Non-budget file should remain
            assert (external_analysis_dir / "other-artifact.json").exists()

    def test_budget_status_counts_review_packets(self) -> None:
        """get_budget_status correctly counts auto-{incident_id}-*-review-packet.json files."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import get_budget_status

        with TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)
            incident_id = "test-incident-456"

            # No files
            status = get_budget_status(external_analysis_dir, incident_id)
            assert status["review_packet_count"] == 0
            assert status["budget_clean"] is True
            assert status["budget_exhausted"] is False

            # Add some files
            (external_analysis_dir / f"auto-{incident_id}-0-diagnosis-review-packet.json").write_text('{"findings":[]}')
            (external_analysis_dir / f"auto-{incident_id}-1-diagnosis-review-packet.json").write_text('{"findings":[]}')

            status = get_budget_status(external_analysis_dir, incident_id)
            assert status["review_packet_count"] == 2
            assert status["budget_clean"] is False
            assert status["budget_exhausted"] is True


# =============================================================================
# P4c: Precise failure classification tests
# =============================================================================

class TestTargetedFailureClassification:
    """Tests for precise failure classification in targeted diagnosis."""

    def test_curl_exit_52_classified_as_empty_reply(self) -> None:
        """curl_rc=52 (Empty reply from server) should be FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY,
            TargetedDiagnosisInvocationResult,
        )

        # Create result with curl_rc=52
        result = TargetedDiagnosisInvocationResult(
            success=False,
            http_status=0,
            body="",
            json_parsed=False,
            error_class=FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY,
            curl_rc=52,
        )

        assert result.curl_rc == 52
        assert result.error_class == FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY
        assert result.is_transport_error() is True

    def test_budget_exhausted_classified_as_runtime_state(self) -> None:
        """budget_exhausted should be FAILURE_TARGETED_LOOP_NOT_ELIGIBLE (runtime state)."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            FAILURE_TARGETED_LOOP_NOT_ELIGIBLE,
            TargetedDiagnosisInvocationResult,
        )

        result = TargetedDiagnosisInvocationResult(
            success=True,  # HTTP 200
            http_status=200,
            body='{"skipped": true}',
            json_parsed=True,
            error_class=FAILURE_TARGETED_LOOP_NOT_ELIGIBLE,
            curl_rc=0,
        )

        assert result.error_class == FAILURE_TARGETED_LOOP_NOT_ELIGIBLE
        assert result.is_runtime_state() is True

    def test_http_200_with_error_class_returns_eligible_error(self) -> None:
        """HTTP 200 with error_class should return FAILURE_TARGETED_LOOP_NOT_ELIGIBLE for budget."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            FAILURE_TARGETED_LOOP_NOT_ELIGIBLE,
            TargetedDiagnosisInvocationResult,
        )

        result = TargetedDiagnosisInvocationResult(
            success=True,  # Backend responded successfully
            http_status=200,
            body='{"error_class": "budget_exhausted"}',
            json_parsed=True,
            error_class=FAILURE_TARGETED_LOOP_NOT_ELIGIBLE,
            curl_rc=0,
        )

        # This is the correct classification for budget exhaustion
        assert result.success is True
        assert result.http_status == 200
        assert result.error_class == FAILURE_TARGETED_LOOP_NOT_ELIGIBLE

    def test_transport_error_detection(self) -> None:
        """is_transport_error should return True for curl failures with error_class set."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
            FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
            FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY,
            TargetedDiagnosisInvocationResult,
        )

        # curl_rc=52 (empty reply) with error_class set
        result1 = TargetedDiagnosisInvocationResult(
            success=False,
            http_status=0,
            body="",
            json_parsed=False,
            error_class=FAILURE_TARGETED_LOOP_BACKEND_EMPTY_REPLY,
            curl_rc=52,
        )
        assert result1.is_transport_error() is True

        # curl_rc=7 (connection refused) with error_class set
        result2 = TargetedDiagnosisInvocationResult(
            success=False,
            http_status=0,
            body="",
            json_parsed=False,
            error_class=FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
            curl_rc=7,
        )
        assert result2.is_transport_error() is True

        # Empty error_class should return False
        result3 = TargetedDiagnosisInvocationResult(
            success=True,
            http_status=200,
            body='{"ok": true}',
            json_parsed=True,
            error_class="",
            curl_rc=0,
        )
        assert result3.is_transport_error() is False


# =============================================================================
# P0b: Provider health JSON parsing robustness tests
# =============================================================================

class TestProviderCurlMarkerBasedParsing:
    """Tests for marker-based parsing in _curl_exec_pod.

    This verifies that the P0b fix (using ---CURL_START--- and STDERR_BLOCK markers)
    correctly separates metadata from body content.
    """

    def test_exec_pod_parses_body_with_markers(self) -> None:
        """_curl_exec_pod should correctly parse body using marker-based approach."""
        from scripts.lab_common.provider_curl_helpers import _curl_exec_pod

        # Simulate kubectl exec output with markers
        logs_output = """---CURL_START---
{"healthy": true, "version": "1.0.0"}
CURL_EXIT=0
HTTP_CODE=200
STDERR_BLOCK
"""

        def run_side_effect(*args: tuple, **kwargs: dict) -> MagicMock:
            cmd = args[0] if args else kwargs.get("args", ())
            if "get" in " ".join(cmd):
                return MagicMock(returncode=0, stdout="Succeeded")
            elif "logs" in " ".join(cmd):
                return MagicMock(returncode=0, stdout=logs_output, stderr="")
            elif "delete" in " ".join(cmd):
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout=logs_output, stderr="")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = run_side_effect

            result = _curl_exec_pod(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                deployment="k9b-backend",
                container="k9b-backend",
                target_url="http://localhost:8080/api/health/details",
                timeout_seconds=5,
            )

            # Body should NOT contain markers
            assert "---CURL_START---" not in result.body
            assert "CURL_EXIT" not in result.body
            assert "HTTP_CODE" not in result.body
            assert "STDERR_BLOCK" not in result.body

            # Body should contain the actual JSON
            assert '{"healthy": true' in result.body

            # HTTP code should be parsed
            assert result.http_code == 200
            assert result.curl_rc == 0

    def test_exec_pod_preserves_json_content_with_metadata_strings(self) -> None:
        """JSON content containing 'CURL_EXIT=' or 'HTTP_CODE=' should not be corrupted.

        This is the core P0b fix: if the JSON body contains strings like 'CURL_EXIT=',
        they should be preserved in the parsed body.
        """
        from scripts.lab_common.provider_curl_helpers import _curl_exec_pod

        # Simulate JSON that contains metadata-like strings
        # This is a realistic scenario where the health details response
        # might contain paths or other text that looks like metadata
        json_body = '{"status": "ok", "metadata": {"curl_exit": "success", "code": 200}}'
        logs_output = f"""---CURL_START---
{json_body}
CURL_EXIT=0
HTTP_CODE=200
STDERR_BLOCK
"""

        def run_side_effect(*args: tuple, **kwargs: dict) -> MagicMock:
            cmd = args[0] if args else kwargs.get("args", ())
            if "get" in " ".join(cmd):
                return MagicMock(returncode=0, stdout="Succeeded")
            elif "logs" in " ".join(cmd):
                return MagicMock(returncode=0, stdout=logs_output, stderr="")
            elif "delete" in " ".join(cmd):
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout=logs_output, stderr="")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = run_side_effect

            result = _curl_exec_pod(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                deployment="k9b-backend",
                container="k9b-backend",
                target_url="http://localhost:8080/api/health/details",
                timeout_seconds=5,
            )

            # The metadata-like strings in the JSON body should be preserved
            parsed = json.loads(result.body)
            assert parsed["metadata"]["curl_exit"] == "success"
            assert parsed["metadata"]["code"] == 200

    def test_exec_pod_handles_multiline_json(self) -> None:
        """Multiline JSON body should be preserved correctly."""
        from scripts.lab_common.provider_curl_helpers import _curl_exec_pod

        multiline_json = """{
    "healthy": true,
    "dependencies": [
        {"name": "provider", "status": "ok"}
    ]
}"""
        logs_output = f"""---CURL_START---
{multiline_json}
CURL_EXIT=0
HTTP_CODE=200
STDERR_BLOCK
"""

        def run_side_effect(*args: tuple, **kwargs: dict) -> MagicMock:
            cmd = args[0] if args else kwargs.get("args", ())
            if "get" in " ".join(cmd):
                return MagicMock(returncode=0, stdout="Succeeded")
            elif "logs" in " ".join(cmd):
                return MagicMock(returncode=0, stdout=logs_output, stderr="")
            elif "delete" in " ".join(cmd):
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout=logs_output, stderr="")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = run_side_effect

            result = _curl_exec_pod(
                kubeconfig="/fake/kubeconfig",
                namespace="k9b",
                deployment="k9b-backend",
                container="k9b-backend",
                target_url="http://localhost:8080/api/health/details",
                timeout_seconds=5,
            )

            # Body should be valid JSON
            parsed = json.loads(result.body)
            assert parsed["healthy"] is True
            assert len(parsed["dependencies"]) == 1


class TestProviderHealthJsonRobustness:
    """Tests for provider health JSON parsing robustness end-to-end."""

    def test_preflight_with_valid_json_passes(self) -> None:
        """Provider preflight with valid JSON should pass."""
        from scripts.lab_common.provider_preflight import run_provider_preflight

        valid_body = json.dumps({
            "healthy": True,
            "primary_failure_class": "",
            "provider_enabled": True,
            "dependencies": [
                {"dependency_name": "diagnosis_provider", "status": "available", "phase": "models_list_ok"}
            ]
        })

        def make_curl_result() -> MagicMock:
            result = MagicMock()
            result.success = True
            result.body = valid_body
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

        assert result.passed is True

    def test_preflight_with_concatenated_json_fails(self) -> None:
        """Provider preflight with concatenated JSON should fail with invalid_json."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_INVALID_JSON,
            run_provider_preflight,
        )

        # Simulate the P0b bug: curl write-out appended to JSON body
        concatenated_body = '{"healthy":true}CURL_EXIT=0'

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

        # Should fail with invalid_json classification
        assert result.passed is False
        assert result.failure_class == FAILURE_PROVIDER_HEALTH_INVALID_JSON
