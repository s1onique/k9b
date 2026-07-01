"""Regression tests for P4c not_run state machine bug.

Bug: The poll function treated loop_summary.status=not_run as completion
because review_available=True. This caused the lab to report success
even though no diagnosis pass was recorded.

The fix classifies not_run as a specific failure:
- NOT terminal success (not_run is never "completed")
- NOT terminal failure (it's a distinct "never started" state)
- Triggers FAILURE_TARGETED_LOOP_NOT_STARTED on timeout

Related issue: OTel live lab P4c failure where HTTP 200 was returned
but loop_summary.status stayed "not_run" with pass_count=0.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_TARGETED_LOOP_NOT_STARTED,
    BackendIncidentDetail,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_poll import (
    poll_backend_diagnosis_state,
)


class TestP4cNotRunNotTreatedAsCompletion:
    """Regression tests for the P4c not_run state machine bug."""

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_poll.fetch_backend_incident_detail")
    @patch("time.sleep")
    def test_poll_returns_not_started_failure_when_loop_never_started(
        self,
        mock_sleep: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Test poll fails with loop_not_started when status remains not_run.

        This is the PRIMARY regression test for the OTel live lab P4c failure.
        The scenario:
        1. Backend targeted endpoint returns HTTP 200
        2. But loop_summary.status stays "not_run" (no pass recorded)
        3. review_available=True (misleading - indicates incident exists)
        4. Old code: treated review_available=True as completion -> FALSE POSITIVE
        5. New code: not_run is classified as failure -> CORRECT
        """
        # Simulate the exact scenario from the OTel live lab:
        # - Incident exists (review_available=True)
        # - But loop never ran (status=not_run, pass_count=0)
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="otel-demo-deployment-shipping-deployment_unavailable",
            status="collecting_evidence",
            evidence_count=0,
            review_packet_status=None,
            loop_summary_status="not_run",  # THE KEY: loop never started
            review_available=True,  # Misleading: incident exists but no diagnosis
            raw={
                "automatic_diagnosis_loop_summary": {
                    "status": "not_run",
                    "pass_run_ids": [],
                    "pass_count": 0,
                }
            },
        )

        # Poll with minimal attempts to speed up test
        result = poll_backend_diagnosis_state(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="otel-demo-deployment-shipping-deployment_unavailable",
            max_attempts=2,  # Short timeout for test
            poll_interval_seconds=0.01,  # Fast polling
        )

        # Assert: poll should FAIL with specific failure reason
        assert result.success is False, (
            "Poll should fail when loop_summary.status=not_run. "
            "Old bug treated HTTP 200 + review_available=True as success."
        )
        assert result.failure_reason == FAILURE_TARGETED_LOOP_NOT_STARTED, (
            f"Expected failure_reason={FAILURE_TARGETED_LOOP_NOT_STARTED}, "
            f"got {result.failure_reason!r}"
        )
        assert result.error_detail is not None and "not_run" in result.error_detail, (
            "Error detail should mention 'not_run' for debugging"
        )
        assert result.loop_summary_status == "not_run"
        assert result.attempts == 2  # Should exhaust all attempts

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_poll.fetch_backend_incident_detail")
    @patch("time.sleep")
    def test_poll_returns_not_started_failure_when_loop_summary_null(
        self,
        mock_sleep: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Test poll fails when loop_summary.status is null/None.

        If the backend returns no loop_summary at all, this is equivalent
        to not_run - the loop was never started.
        """
        # Simulate: loop_summary missing entirely
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-123",
            status="discovered",
            evidence_count=0,
            review_packet_status=None,
            loop_summary_status=None,  # null - loop summary not present
            review_available=False,
            raw={},  # No automatic_diagnosis_loop_summary at all
        )

        result = poll_backend_diagnosis_state(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
            max_attempts=1,
            poll_interval_seconds=0.01,
        )

        # Assert: should fail with not_started
        assert result.success is False
        assert result.failure_reason == FAILURE_TARGETED_LOOP_NOT_STARTED
        assert result.loop_summary_status is None

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_poll.fetch_backend_incident_detail")
    @patch("time.sleep")
    def test_poll_succeeds_when_loop_completed(
        self,
        mock_sleep: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Verify poll still succeeds for legitimate completed diagnosis.

        This is a sanity check to ensure the not_run fix doesn't break
        the normal success path.
        """
        # Simulate: successful diagnosis completion
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-123",
            status="diagnosed",
            evidence_count=5,
            review_packet_status="ready",
            loop_summary_status="completed",  # Terminal success state
            review_available=True,
            raw={
                "automatic_diagnosis_loop_summary": {
                    "status": "completed",
                    "pass_run_ids": ["run-1", "run-2"],
                    "pass_count": 2,
                }
            },
        )

        result = poll_backend_diagnosis_state(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-123",
            max_attempts=12,
            poll_interval_seconds=0.01,
        )

        # Assert: should succeed on first poll
        assert result.success is True
        assert result.loop_summary_status == "completed"
        assert result.review_available is True
        assert result.attempts == 1

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_poll.fetch_backend_incident_detail")
    @patch("time.sleep")
    def test_poll_succeeds_when_review_available_with_completed(
        self,
        mock_sleep: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Verify poll succeeds for review_available=True with completed status.

        This ensures the old success path still works: when review_available=True
        AND loop_summary.status=completed, the poll should succeed.
        """
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-456",
            status="diagnosed",
            evidence_count=3,
            review_packet_status="ready",
            loop_summary_status="completed",
            review_available=True,
            raw={
                "automatic_diagnosis_loop_summary": {
                    "status": "completed",
                    "pass_run_ids": ["run-1"],
                    "pass_count": 1,
                }
            },
        )

        result = poll_backend_diagnosis_state(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-456",
            max_attempts=12,
            poll_interval_seconds=0.01,
        )

        assert result.success is True
        assert result.loop_summary_status == "completed"
        assert result.attempts == 1

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_poll.fetch_backend_incident_detail")
    @patch("time.sleep")
    def test_poll_fails_on_terminal_failure_state(
        self,
        mock_sleep: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Verify poll fails immediately on terminal failure states.

        States like 'failed', 'error', 'budget_exhausted' should fail
        the poll, not continue polling.
        """
        mock_fetch.return_value = BackendIncidentDetail(
            incident_id="inc-789",
            status="failed",
            evidence_count=0,
            review_packet_status=None,
            loop_summary_status="failed",
            review_available=False,
            raw={
                "automatic_diagnosis_loop_summary": {
                    "status": "failed",
                    "pass_run_ids": [],
                    "pass_count": 0,
                }
            },
        )

        result = poll_backend_diagnosis_state(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-789",
            max_attempts=12,
            poll_interval_seconds=0.01,
        )

        assert result.success is False
        assert result.failure_reason == "failed"
        assert result.error_detail is not None and "terminal failure state" in result.error_detail
        assert result.attempts == 1

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_poll.fetch_backend_incident_detail")
    @patch("time.sleep")
    def test_poll_continues_polling_for_running_state(
        self,
        mock_sleep: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Verify poll continues polling for 'running' state.

        The loop status 'running' is non-terminal, so the poll should
        continue until it reaches a terminal state or times out.
        """
        # First call: running
        # Second call: completed (simulating progress)
        mock_fetch.side_effect = [
            BackendIncidentDetail(
                incident_id="inc-running",
                status="diagnosing",
                evidence_count=1,
                review_packet_status=None,
                loop_summary_status="running",
                review_available=False,
                raw={
                    "automatic_diagnosis_loop_summary": {
                        "status": "running",
                    }
                },
            ),
            BackendIncidentDetail(
                incident_id="inc-running",
                status="diagnosed",
                evidence_count=5,
                review_packet_status="ready",
                loop_summary_status="completed",
                review_available=True,
                raw={
                    "automatic_diagnosis_loop_summary": {
                        "status": "completed",
                        "pass_run_ids": ["run-1"],
                        "pass_count": 1,
                    }
                },
            ),
        ]

        result = poll_backend_diagnosis_state(
            kubeconfig="/path/to/kubeconfig",
            namespace="k9b",
            incident_id="inc-running",
            max_attempts=5,
            poll_interval_seconds=0.01,
        )

        assert result.success is True
        assert result.loop_summary_status == "completed"
        assert result.attempts == 2  # Should have polled twice
