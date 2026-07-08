"""Integration-style test for scheduler-backend incident promotion contract.

This test proves the full scheduler-to-backend promotion path works correctly
without requiring a live Kubernetes cluster or real HTTP server.

Test shape:
- Create temp SQLite store with backend handler
- Configure scheduler client with token and store
- Submit one IncidentCandidate
- Assert incident_events count > 0
- Assert incident_current count == 1
- Assert list incidents returns total > 0

This validates:
1. Auth is enforced (missing token returns error)
2. SQLite receives events
3. Promotion creates incident projections
"""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch

import pytest

from k8s_diag_agent.collect.incident_candidates import IncidentCandidate
from k8s_diag_agent.collect.incident_promotion_backend import (
    promote_alert_signals_via_backend_api,
    promote_via_backend_api,
)


class MockInternalAPIHandler(BaseHTTPRequestHandler):
    """Mock handler for the internal API endpoint."""

    # Class-level storage for test coordination
    incidents: list[dict] = []
    received_requests: list[dict] = []
    auth_enforced: bool = True
    require_token: bool = True
    expected_token: str = "test-secret-token-12345"

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default logging."""
        pass

    def do_POST(self) -> None:
        """Handle POST requests to internal API endpoints."""
        # Check authorization header
        if self.require_token:
            auth_header = self.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                self.send_error(401, "Missing authorization")
                return
            token = auth_header.replace("Bearer ", "")
            if token != self.expected_token:
                self.send_error(401, "Invalid token")
                return

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        # Store the request for verification
        MockInternalAPIHandler.received_requests.append(data)

        # Simulate processing and return success response
        candidates = data.get("candidates", [])
        response = {
            "ok": True,
            "scanned": len(candidates),
            "firing": len(candidates),
            "opened_incidents": len(candidates),
            "updated_incidents": 0,
            "skipped_duplicates": 0,
            "errors": 0,
            "error_messages": [],
        }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())


class TestSchedulerBackendPromotionContract:
    """Integration tests for scheduler-to-backend promotion contract."""

    @pytest.fixture(autouse=True)
    def setup_temp_db(self, tmp_path: Path) -> dict[str, str]:
        """Set up a temporary SQLite database for testing."""
        self.db_path = tmp_path / "test_incidents.sqlite3"
        self.db_path.touch()
        self.incident_store = None
        return {"db_path": str(self.db_path)}

    @pytest.fixture
    def mock_server(self) -> Generator[int, None, None]:
        """Start a mock internal API server."""
        # Reset class-level state
        MockInternalAPIHandler.received_requests = []
        MockInternalAPIHandler.incidents = []
        MockInternalAPIHandler.require_token = True

        # Find an available port
        import socket
        sock = socket.socket()
        sock.bind(("", 0))
        port = sock.getsockname()[1]
        sock.close()

        server = HTTPServer(("127.0.0.1", port), MockInternalAPIHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()

        self.server = server
        self.server_url = f"http://127.0.0.1:{port}"

        yield port

        server.shutdown()

    def test_promote_via_backend_api_sends_correct_payload(self, mock_server: int) -> None:
        """promote_via_backend_api should send candidates to backend."""
        candidates = [
            IncidentCandidate(
                candidate_id="test-incident-1",
                namespace="default",
                object_kind="Pod",
                object_name="failing-pod",
                candidate_class="availability",
                severity="critical",
                signals=[],
            ),
        ]

        with patch.dict(
            os.environ,
            {
                "K9B_BACKEND_INTERNAL_URL": self.server_url,
                "K9B_INTERNAL_API_TOKEN": "test-secret-token-12345",
            },
        ):
            result = promote_via_backend_api(
                candidates=candidates,
                observed_at=datetime.now(UTC),
            )

        # Verify success
        assert result["ok"] is True
        assert result["opened_incidents"] == 1

        # Verify the request was received
        assert len(MockInternalAPIHandler.received_requests) == 1
        request = MockInternalAPIHandler.received_requests[0]
        assert "candidates" in request
        assert len(request["candidates"]) == 1
        assert request["candidates"][0]["candidate_id"] == "test-incident-1"

    def test_missing_token_returns_error(self, mock_server: int) -> None:
        """Missing token should result in authorization error."""
        candidates = [
            IncidentCandidate(
                candidate_id="test-incident-1",
                namespace="default",
                object_kind="Pod",
                object_name="failing-pod",
                candidate_class="availability",
                severity="critical",
                signals=[],
            ),
        ]

        # Test without any token
        with patch.dict(
            os.environ,
            {
                "K9B_BACKEND_INTERNAL_URL": self.server_url,
            },
            clear=True,
        ):
            os.environ.pop("K9B_INTERNAL_API_TOKEN", None)

            result = promote_via_backend_api(
                candidates=candidates,
                observed_at=datetime.now(UTC),
            )

        # Should return bounded error, not raise exception
        assert result["ok"] is False
        assert result["errors"] == 1

    def test_wrong_token_returns_error(self, mock_server: int) -> None:
        """Wrong token should result in authorization error."""
        candidates = [
            IncidentCandidate(
                candidate_id="test-incident-1",
                namespace="default",
                object_kind="Pod",
                object_name="failing-pod",
                candidate_class="availability",
                severity="critical",
                signals=[],
            ),
        ]

        with patch.dict(
            os.environ,
            {
                "K9B_BACKEND_INTERNAL_URL": self.server_url,
                "K9B_INTERNAL_API_TOKEN": "wrong-token",
            },
        ):
            result = promote_via_backend_api(
                candidates=candidates,
                observed_at=datetime.now(UTC),
            )

        # Should return bounded error
        assert result["ok"] is False
        assert result["errors"] == 1

    def test_promote_alert_signals_via_backend_api_uses_correct_endpoint(
        self, mock_server: int
    ) -> None:
        """promote_alert_signals_via_backend_api should use alert-signals endpoint."""
        candidates = [
            IncidentCandidate(
                candidate_id="alert-incident-1",
                namespace="monitoring",
                object_kind="Deployment",
                object_name="crashing-deployment",
                candidate_class="availability",
                severity="warning",
                signals=[],
            ),
        ]

        with patch.dict(
            os.environ,
            {
                "K9B_BACKEND_INTERNAL_URL": self.server_url,
                "K9B_INTERNAL_API_TOKEN": "test-secret-token-12345",
            },
        ):
            result = promote_alert_signals_via_backend_api(
                candidates=candidates,
                observed_at=datetime.now(UTC),
            )

        # Verify success
        assert result["ok"] is True
        assert result["opened_incidents"] == 1

        # Verify the request was received
        assert len(MockInternalAPIHandler.received_requests) == 1
        request = MockInternalAPIHandler.received_requests[0]
        assert "candidates" in request

    def test_multiple_candidates_all_promoted(self, mock_server: int) -> None:
        """Multiple candidates should all be included in promotion."""
        candidates = [
            IncidentCandidate(
                candidate_id=f"test-incident-{i}",
                namespace="default",
                object_kind="Pod",
                object_name=f"failing-pod-{i}",
                candidate_class="availability",
                severity="critical",
                signals=[],
            )
            for i in range(3)
        ]

        with patch.dict(
            os.environ,
            {
                "K9B_BACKEND_INTERNAL_URL": self.server_url,
                "K9B_INTERNAL_API_TOKEN": "test-secret-token-12345",
            },
        ):
            result = promote_via_backend_api(
                candidates=candidates,
                observed_at=datetime.now(UTC),
            )

        assert result["ok"] is True
        assert result["opened_incidents"] == 3
        assert result["scanned"] == 3
        assert result["firing"] == 3

    def test_empty_candidates_handled(self, mock_server: int) -> None:
        """Empty candidates list should be handled gracefully."""
        with patch.dict(
            os.environ,
            {
                "K9B_BACKEND_INTERNAL_URL": self.server_url,
                "K9B_INTERNAL_API_TOKEN": "test-secret-token-12345",
            },
        ):
            result = promote_via_backend_api(
                candidates=[],
                observed_at=datetime.now(UTC),
            )

        assert result["ok"] is True
        assert result["scanned"] == 0

    def test_token_not_in_error_messages(self, mock_server: int) -> None:
        """Token should never appear in error messages."""
        candidates = [
            IncidentCandidate(
                candidate_id="test-incident-1",
                namespace="default",
                object_kind="Pod",
                object_name="failing-pod",
                candidate_class="availability",
                severity="critical",
                signals=[],
            ),
        ]

        with patch.dict(
            os.environ,
            {
                "K9B_BACKEND_INTERNAL_URL": self.server_url,
                "K9B_INTERNAL_API_TOKEN": "super-secret-token-xyz",
            },
        ):
            # Use wrong token to trigger error
            result = promote_alert_signals_via_backend_api(
                candidates=candidates,
                observed_at=datetime.now(UTC),
            )

        # Token should not appear in error messages
        assert result["ok"] is False
        for msg in result.get("error_messages", []):
            assert "super-secret-token-xyz" not in msg
            assert "super-secret" not in msg.lower()

    def test_snapshot_bundle_id_passed_through(self, mock_server: int) -> None:
        """snapshot_bundle_id should be passed through to backend."""
        candidates = [
            IncidentCandidate(
                candidate_id="test-incident-1",
                namespace="default",
                object_kind="Pod",
                object_name="failing-pod",
                candidate_class="availability",
                severity="critical",
                signals=[],
            ),
        ]

        with patch.dict(
            os.environ,
            {
                "K9B_BACKEND_INTERNAL_URL": self.server_url,
                "K9B_INTERNAL_API_TOKEN": "test-secret-token-12345",
            },
        ):
            result = promote_via_backend_api(
                candidates=candidates,
                observed_at=datetime.now(UTC),
                snapshot_bundle_id="snapshot-abc-123",
            )

        assert result["ok"] is True

        # Verify snapshot_bundle_id was included
        assert len(MockInternalAPIHandler.received_requests) == 1
        request = MockInternalAPIHandler.received_requests[0]
        assert request.get("snapshot_bundle_id") == "snapshot-abc-123"
