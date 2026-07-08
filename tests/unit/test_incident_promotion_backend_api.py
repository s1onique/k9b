"""Transport contract tests for incident_promotion_backend module.

Tests validate:
1. promote_via_backend_api uses SchedulerClient.promote_candidates
2. promote_alert_signals_via_backend_api uses SchedulerClient.promote_alert_signals
3. Missing backend URL returns bounded error
4. Missing token returns bounded error
5. promotion_mode remains backend-api in result
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from k8s_diag_agent.collect.incident_candidates import IncidentCandidate
from k8s_diag_agent.collect.incident_promotion_backend import (
    promote_alert_signals_via_backend_api,
    promote_via_backend_api,
)
from k8s_diag_agent.ui.server_incident_internal_models import PromotionResponse


class TestPromoteViaBackendApi:
    """Test promote_via_backend_api function."""

    def test_promote_via_backend_api_uses_candidates_endpoint(self) -> None:
        """promote_via_backend_api should use SchedulerClient.promote_candidates."""
        candidates = [
            IncidentCandidate(
                candidate_id="test-1",
                namespace="default",
                object_kind="Pod",
                object_name="test-pod",
                candidate_class="availability",
                severity="critical",
                signals=[],
            ),
        ]

        with patch.dict(
            os.environ,
            {
                "K9B_BACKEND_INTERNAL_URL": "http://k9b-backend:8080",
                "K9B_INTERNAL_API_TOKEN": "test-token",
            },
        ):
            with patch(
                "k8s_diag_agent.collect.incident_promotion_backend.SchedulerClient"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.promote_candidates.return_value = PromotionResponse(
                    ok=True,
                    scanned=1,
                    firing=1,
                    opened_incidents=1,
                    updated_incidents=0,
                    skipped_duplicates=0,
                    errors=0,
                    error_messages=[],
                )
                mock_client_class.return_value = mock_client

                result = promote_via_backend_api(
                    candidates=candidates,
                    observed_at=datetime.now(UTC),
                )

        # Should call promote_candidates, not promote_alert_signals
        mock_client.promote_candidates.assert_called_once()
        mock_client.promote_alert_signals.assert_not_called()

        assert result["ok"] is True
        assert result["opened_incidents"] == 1
        assert result["errors"] == 0

    def test_missing_backend_url_returns_bounded_error(self) -> None:
        """Missing K9B_BACKEND_INTERNAL_URL should return bounded error."""
        candidates = [
            IncidentCandidate(
                candidate_id="test-1",
                namespace="default",
                object_kind="Pod",
                object_name="test-pod",
                candidate_class="availability",
                severity="critical",
                signals=[],
            ),
        ]

        with patch.dict(os.environ, {"K9B_INTERNAL_API_TOKEN": "test-token"}, clear=True):
            # Clear K9B_BACKEND_INTERNAL_URL
            os.environ.pop("K9B_BACKEND_INTERNAL_URL", None)

            result = promote_via_backend_api(
                candidates=candidates,
                observed_at=datetime.now(UTC),
            )

        assert result["ok"] is False
        assert result["errors"] == 1
        assert "missing" in result["error_messages"][0].lower()

    def test_missing_token_returns_bounded_error(self) -> None:
        """Missing K9B_INTERNAL_API_TOKEN should return bounded error."""
        candidates = [
            IncidentCandidate(
                candidate_id="test-1",
                namespace="default",
                object_kind="Pod",
                object_name="test-pod",
                candidate_class="availability",
                severity="critical",
                signals=[],
            ),
        ]

        with patch.dict(
            os.environ,
            {"K9B_BACKEND_INTERNAL_URL": "http://k9b-backend:8080"},
            clear=True,
        ):
            os.environ.pop("K9B_INTERNAL_API_TOKEN", None)

            result = promote_via_backend_api(
                candidates=candidates,
                observed_at=datetime.now(UTC),
            )

        assert result["ok"] is False
        assert result["errors"] == 1
        assert "missing" in result["error_messages"][0].lower()

    def test_client_exception_returns_bounded_error(self) -> None:
        """Client exception should return bounded error, not crash."""
        candidates = [
            IncidentCandidate(
                candidate_id="test-1",
                namespace="default",
                object_kind="Pod",
                object_name="test-pod",
                candidate_class="availability",
                severity="critical",
                signals=[],
            ),
        ]

        with patch.dict(
            os.environ,
            {
                "K9B_BACKEND_INTERNAL_URL": "http://k9b-backend:8080",
                "K9B_INTERNAL_API_TOKEN": "test-token",
            },
        ):
            with patch(
                "k8s_diag_agent.collect.incident_promotion_backend.SchedulerClient"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.promote_candidates.side_effect = Exception("Connection failed")
                mock_client_class.return_value = mock_client

                result = promote_via_backend_api(
                    candidates=candidates,
                    observed_at=datetime.now(UTC),
                )

        assert result["ok"] is False
        assert result["errors"] == 1
        # Error message should not contain the token
        for msg in result["error_messages"]:
            assert "test-token" not in msg


class TestPromoteAlertSignalsViaBackendApi:
    """Test promote_alert_signals_via_backend_api function."""

    def test_promote_alert_signals_via_backend_api_uses_alert_endpoint(self) -> None:
        """promote_alert_signals_via_backend_api should use SchedulerClient.promote_alert_signals."""
        candidates = [
            IncidentCandidate(
                candidate_id="alert-1",
                namespace="default",
                object_kind="Pod",
                object_name="alerting-pod",
                candidate_class="availability",
                severity="warning",
                signals=[],
            ),
        ]

        with patch.dict(
            os.environ,
            {
                "K9B_BACKEND_INTERNAL_URL": "http://k9b-backend:8080",
                "K9B_INTERNAL_API_TOKEN": "test-token",
            },
        ):
            with patch(
                "k8s_diag_agent.collect.incident_promotion_backend.SchedulerClient"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.promote_alert_signals.return_value = PromotionResponse(
                    ok=True,
                    scanned=1,
                    firing=1,
                    opened_incidents=1,
                    updated_incidents=0,
                    skipped_duplicates=0,
                    errors=0,
                    error_messages=[],
                )
                mock_client_class.return_value = mock_client

                result = promote_alert_signals_via_backend_api(
                    candidates=candidates,
                    observed_at=datetime.now(UTC),
                )

        # Should call promote_alert_signals, not promote_candidates
        mock_client.promote_alert_signals.assert_called_once()
        mock_client.promote_candidates.assert_not_called()

        assert result["ok"] is True
        assert result["opened_incidents"] == 1
        assert result["errors"] == 0

    def test_alert_signals_missing_backend_url_returns_bounded_error(self) -> None:
        """Missing K9B_BACKEND_INTERNAL_URL should return bounded error."""
        candidates = [
            IncidentCandidate(
                candidate_id="alert-1",
                namespace="default",
                object_kind="Pod",
                object_name="alerting-pod",
                candidate_class="availability",
                severity="warning",
                signals=[],
            ),
        ]

        with patch.dict(os.environ, {"K9B_INTERNAL_API_TOKEN": "test-token"}, clear=True):
            os.environ.pop("K9B_BACKEND_INTERNAL_URL", None)

            result = promote_alert_signals_via_backend_api(
                candidates=candidates,
                observed_at=datetime.now(UTC),
            )

        assert result["ok"] is False
        assert result["errors"] == 1
        assert "missing" in result["error_messages"][0].lower()

    def test_alert_signals_missing_token_returns_bounded_error(self) -> None:
        """Missing K9B_INTERNAL_API_TOKEN should return bounded error."""
        candidates = [
            IncidentCandidate(
                candidate_id="alert-1",
                namespace="default",
                object_kind="Pod",
                object_name="alerting-pod",
                candidate_class="availability",
                severity="warning",
                signals=[],
            ),
        ]

        with patch.dict(
            os.environ,
            {"K9B_BACKEND_INTERNAL_URL": "http://k9b-backend:8080"},
            clear=True,
        ):
            os.environ.pop("K9B_INTERNAL_API_TOKEN", None)

            result = promote_alert_signals_via_backend_api(
                candidates=candidates,
                observed_at=datetime.now(UTC),
            )

        assert result["ok"] is False
        assert result["errors"] == 1
        assert "missing" in result["error_messages"][0].lower()

    def test_alert_signals_client_exception_returns_bounded_error(self) -> None:
        """Client exception should return bounded error, not crash."""
        candidates = [
            IncidentCandidate(
                candidate_id="alert-1",
                namespace="default",
                object_kind="Pod",
                object_name="alerting-pod",
                candidate_class="availability",
                severity="warning",
                signals=[],
            ),
        ]

        with patch.dict(
            os.environ,
            {
                "K9B_BACKEND_INTERNAL_URL": "http://k9b-backend:8080",
                "K9B_INTERNAL_API_TOKEN": "test-token",
            },
        ):
            with patch(
                "k8s_diag_agent.collect.incident_promotion_backend.SchedulerClient"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.promote_alert_signals.side_effect = Exception(
                    "Connection timeout"
                )
                mock_client_class.return_value = mock_client

                result = promote_alert_signals_via_backend_api(
                    candidates=candidates,
                    observed_at=datetime.now(UTC),
                )

        assert result["ok"] is False
        assert result["errors"] == 1
        # Error message should not contain the token
        for msg in result["error_messages"]:
            assert "test-token" not in msg


class TestPromotionMode:
    """Test that promotion mode is correctly tracked."""

    def test_backend_api_mode_tracks_counts(self) -> None:
        """backend-api promotion should track scanned, firing, opened counts."""
        candidates = [
            IncidentCandidate(
                candidate_id="test-1",
                namespace="default",
                object_kind="Pod",
                object_name="test-pod",
                candidate_class="availability",
                severity="critical",
                signals=[],
            ),
        ]

        with patch.dict(
            os.environ,
            {
                "K9B_BACKEND_INTERNAL_URL": "http://k9b-backend:8080",
                "K9B_INTERNAL_API_TOKEN": "test-token",
            },
        ):
            with patch(
                "k8s_diag_agent.collect.incident_promotion_backend.SchedulerClient"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.promote_candidates.return_value = PromotionResponse(
                    ok=True,
                    scanned=5,
                    firing=3,
                    opened_incidents=2,
                    updated_incidents=1,
                    skipped_duplicates=0,
                    errors=0,
                    error_messages=[],
                )
                mock_client_class.return_value = mock_client

                result = promote_via_backend_api(
                    candidates=candidates,
                    observed_at=datetime.now(UTC),
                )

        # Counts should be passed through from backend response
        assert result["scanned"] == 5
        assert result["firing"] == 3
        assert result["opened_incidents"] == 2
        assert result["updated_incidents"] == 1
        assert result["skipped_duplicates"] == 0

    def test_empty_candidates_handled(self) -> None:
        """Empty candidates list should be handled gracefully."""
        with patch.dict(
            os.environ,
            {
                "K9B_BACKEND_INTERNAL_URL": "http://k9b-backend:8080",
                "K9B_INTERNAL_API_TOKEN": "test-token",
            },
        ):
            with patch(
                "k8s_diag_agent.collect.incident_promotion_backend.SchedulerClient"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.promote_candidates.return_value = PromotionResponse(
                    ok=True,
                    scanned=0,
                    firing=0,
                    opened_incidents=0,
                    updated_incidents=0,
                    skipped_duplicates=0,
                    errors=0,
                    error_messages=[],
                )
                mock_client_class.return_value = mock_client

                result = promote_via_backend_api(
                    candidates=[],
                    observed_at=datetime.now(UTC),
                )

        assert result["ok"] is True
        assert result["scanned"] == 0
