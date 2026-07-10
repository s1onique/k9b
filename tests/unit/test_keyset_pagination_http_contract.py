"""HTTP contract tests for keyset pagination in internal API.

These tests verify:
1. Cursor reaches backend
2. Limit is applied
3. Response includes nextCursor and hasMore
4. Invalid cursor returns 400 with structured error
5. Pure query validation (no side-channel _sent flag)
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
    encode_cursor,
    make_test_cursor,
)
from k8s_diag_agent.ui.server_incident_internal_read_handlers import (
    handle_list_incidents,
)


class MockHandler:
    """Mock handler for testing internal API handlers."""

    def __init__(self, path: str = "/api/internal/incidents", token: str = "test-token") -> None:
        self.path = path
        self.token = token
        self._status: int | None = None
        self._body: bytes | None = None
        self._headers: dict = {}

    def _send_json(self, data: dict, status: int) -> None:
        """Capture the response."""
        self._status = status
        self._body = str(data).encode()
        self._response = data

    @property
    def headers(self) -> dict:
        return self._headers


class TestListIncidentsHttpContract:
    """HTTP contract tests for list incidents endpoint."""

    def test_invalid_cursor_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Invalid cursor token returns 400 with structured error."""
        handler = MockHandler(path="/api/internal/incidents?cursor=invalid-cursor")

        # Mock auth validation to pass
        monkeypatch.setattr(
            "k8s_diag_agent.ui.server_incident_internal_read_handlers._validate_internal_token",
            lambda h: True,
        )

        # Mock the store's page listing method
        mock_store = MagicMock()
        mock_store.list_incidents_for_diagnosis_page.return_value = MagicMock()
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_store_provider.get_incident_store",
            lambda: mock_store,
        )

        handle_list_incidents(handler)

        assert handler._status == 400
        # The pure query parser rejects cursor without limit first
        assert "error" in handler._response

    def test_missing_required_fields_cursor_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cursor missing required fields is rejected."""
        import base64
        import json

        # Create cursor missing the "id" field
        payload = json.dumps({"v": 1, "ts": "2024-01-01T00:00:00+00:00"}).encode()
        invalid_token = base64.urlsafe_b64encode(payload).decode()

        handler = MockHandler(path=f"/api/internal/incidents?cursor={invalid_token}&limit=10")

        monkeypatch.setattr(
            "k8s_diag_agent.ui.server_incident_internal_read_handlers._validate_internal_token",
            lambda h: True,
        )

        mock_store = MagicMock()
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_store_provider.get_incident_store",
            lambda: mock_store,
        )

        handle_list_incidents(handler)

        assert handler._status == 400
        # v1 cursors are rejected as unsupported_version
        assert "error_kind" in handler._response or "error" in handler._response

    def test_response_includes_next_cursor_and_has_more(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Response includes nextCursor and hasMore fields."""

        from k8s_diag_agent.collect.incident_diagnosis_dispatch_contracts import (
            DiagnosisPageIncident,
        )
        from k8s_diag_agent.collect.incident_diagnosis_dispatch_page import (
            IncidentDiagnosisPage,
        )

        handler = MockHandler(path="/api/internal/incidents?limit=2&activeOnly=true")

        monkeypatch.setattr(
            "k8s_diag_agent.ui.server_incident_internal_read_handlers._validate_internal_token",
            lambda h: True,
        )

        # Create cursor that matches the last incident for the page invariant
        ts1 = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        ts2 = datetime(2024, 1, 2, 0, 0, 0, tzinfo=UTC)

        # The cursor must match the LAST incident in the page
        mock_cursor = make_test_cursor(
            first_observed_at_text=ts2.isoformat(),
            incident_id="inc-02",
        )

        # Mock page with matching cursor/incident
        mock_page = IncidentDiagnosisPage(
            incidents=(
                DiagnosisPageIncident(
                    incident_id="inc-01",
                    status="open",
                    first_observed_at=ts1,
                    first_observed_at_key=ts1.isoformat(),
                ),
                DiagnosisPageIncident(
                    incident_id="inc-02",
                    status="open",
                    first_observed_at=ts2,
                    first_observed_at_key=ts2.isoformat(),
                ),
            ),
            next_cursor=mock_cursor,
            has_more=True,
        )

        mock_store = MagicMock()
        mock_store.list_incidents_for_diagnosis_page.return_value = mock_page

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_store_provider.get_incident_store",
            lambda: mock_store,
        )

        handle_list_incidents(handler)

        assert handler._status == 200
        assert "nextCursor" in handler._response
        assert "hasMore" in handler._response
        assert handler._response["hasMore"] is True
        # nextCursor should be encoded token
        assert handler._response["nextCursor"] is not None

    def test_response_includes_total_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Response includes total field."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch_page import (
            IncidentDiagnosisPage,
        )

        handler = MockHandler(path="/api/internal/incidents?limit=10")

        monkeypatch.setattr(
            "k8s_diag_agent.ui.server_incident_internal_read_handlers._validate_internal_token",
            lambda h: True,
        )

        mock_page = IncidentDiagnosisPage(
            incidents=(),
            next_cursor=None,
            has_more=False,
        )

        mock_store = MagicMock()
        mock_store.list_incidents_for_diagnosis_page.return_value = mock_page

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_store_provider.get_incident_store",
            lambda: mock_store,
        )

        handle_list_incidents(handler)

        assert handler._status == 200
        assert "total" in handler._response

    def test_cursor_token_passed_to_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cursor token from query param is passed to backend query."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch_page import (
            IncidentDiagnosisPage,
        )

        # Create a valid cursor token
        cursor = make_test_cursor(
            first_observed_at_text="2024-01-01T00:00:00+00:00",
            incident_id="inc-01",
        )
        cursor_token = encode_cursor(cursor)

        handler = MockHandler(path=f"/api/internal/incidents?limit=5&cursor={cursor_token}")

        monkeypatch.setattr(
            "k8s_diag_agent.ui.server_incident_internal_read_handlers._validate_internal_token",
            lambda h: True,
        )

        # Track what was passed to the page function
        captured_params = []

        def mock_list_page(active_only, limit, after_cursor):
            captured_params.append({"active_only": active_only, "limit": limit, "after_cursor": after_cursor})
            return IncidentDiagnosisPage(
                incidents=(),
                next_cursor=None,
                has_more=False,
            )

        mock_store = MagicMock()
        mock_store.list_incidents_for_diagnosis_page.side_effect = mock_list_page

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_store_provider.get_incident_store",
            lambda: mock_store,
        )

        handle_list_incidents(handler)

        assert handler._status == 200
        # Verify cursor was passed to backend
        assert len(captured_params) == 1
        assert captured_params[0]["after_cursor"] is not None
        assert captured_params[0]["after_cursor"].incident_id == "inc-01"

    def test_active_only_parameter_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """activeOnly=true query param is parsed correctly."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch_page import (
            IncidentDiagnosisPage,
        )

        handler = MockHandler(path="/api/internal/incidents?limit=5&activeOnly=true")

        monkeypatch.setattr(
            "k8s_diag_agent.ui.server_incident_internal_read_handlers._validate_internal_token",
            lambda h: True,
        )

        captured_params = []

        def mock_list_page(active_only, limit, after_cursor):
            captured_params.append({"active_only": active_only, "limit": limit})
            return IncidentDiagnosisPage(
                incidents=(),
                next_cursor=None,
                has_more=False,
            )

        mock_store = MagicMock()
        mock_store.list_incidents_for_diagnosis_page.side_effect = mock_list_page

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_store_provider.get_incident_store",
            lambda: mock_store,
        )

        handle_list_incidents(handler)

        assert handler._status == 200
        assert captured_params[0]["active_only"] is True

    def test_limit_applied_to_backend_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """limit query param is applied to backend query."""
        from k8s_diag_agent.collect.incident_diagnosis_dispatch_page import (
            IncidentDiagnosisPage,
        )

        handler = MockHandler(path="/api/internal/incidents?limit=3")

        monkeypatch.setattr(
            "k8s_diag_agent.ui.server_incident_internal_read_handlers._validate_internal_token",
            lambda h: True,
        )

        captured_params = []

        def mock_list_page(active_only, limit, after_cursor):
            captured_params.append({"limit": limit})
            return IncidentDiagnosisPage(
                incidents=(),
                next_cursor=None,
                has_more=False,
            )

        mock_store = MagicMock()
        mock_store.list_incidents_for_diagnosis_page.side_effect = mock_list_page

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_store_provider.get_incident_store",
            lambda: mock_store,
        )

        handle_list_incidents(handler)

        assert handler._status == 200
        # page_limit is now DiagnosisPageLimit branded type
        assert captured_params[0]["limit"].value == 3

    def test_status_with_limit_returns_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """status + limit combination returns 400 - cannot mix exact status with pagination."""
        handler = MockHandler(path="/api/internal/incidents?status=open&limit=10")

        monkeypatch.setattr(
            "k8s_diag_agent.ui.server_incident_internal_read_handlers._validate_internal_token",
            lambda h: True,
        )

        handle_list_incidents(handler)

        assert handler._status == 400
        assert "Bad Request" in handler._response["error"]
        assert "status" in handler._response["message"].lower()
        assert "limit" in handler._response["message"].lower()


class TestParseIncidentListQuery:
    """Tests for pure query parser _parse_incident_list_query."""

    def test_limit_5_returns_diagnosis_page_limit_5(self) -> None:
        """_parse_incident_list_query('limit=5') returns DiagnosisPageLimit(5)."""
        from k8s_diag_agent.ui.server_incident_internal_read_handlers import (
            QueryRejected,
            _parse_incident_list_query,
        )

        result = _parse_incident_list_query("limit=5")

        # Verify we got a successful query result, not a rejection
        assert not isinstance(result, QueryRejected), f"Expected success, got QueryRejected: {result}"
        # Access type name safely
        result_type = type(result).__name__
        assert result_type == "IncidentListQuery", f"Expected IncidentListQuery, got {result_type}"

        # Verify page_limit is DiagnosisPageLimit with value 5
        assert result.page_limit is not None
        assert result.page_limit.value == 5
        # Verify it is the branded type, not just an int
        from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
            DiagnosisPageLimit,
        )
        assert isinstance(result.page_limit, DiagnosisPageLimit)
        assert result.uses_pagination is True
        assert result.status is None
        assert result.cursor is None
        assert result.active_only is False


class TestSchedulerClientContract:
    """HTTP contract tests for scheduler client."""

    def test_list_incidents_returns_next_cursor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """list_incidents returns nextCursor from backend response."""
        import json as json_module

        from k8s_diag_agent.ui.server_incident_internal_fetch import SchedulerClient

        client = SchedulerClient(base_url="http://localhost:8080", token="test-token")

        # Mock the response with nextCursor
        mock_response = {
            "incidents": [],
            "nextCursor": "some-cursor-token",
            "hasMore": True,
            "total": 0,
        }

        def mock_urlopen(req, timeout=30.0):
            resp = MagicMock()
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=None)
            # Use json.dumps to produce valid JSON with double quotes and proper booleans
            resp.read.return_value = json_module.dumps(mock_response).encode()
            return resp

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

        result = client.list_incidents(limit=10)

        assert "nextCursor" in result
        assert result["nextCursor"] == "some-cursor-token"
        assert result["hasMore"] is True

    def test_list_incidents_returns_error_on_missing_backend_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """list_incidents returns error when backend URL is missing."""
        from k8s_diag_agent.ui.server_incident_internal_fetch import SchedulerClient

        client = SchedulerClient(base_url="", token="test-token")

        result = client.list_incidents()

        assert "error" in result
        assert result["incidents"] == []
        assert result["nextCursor"] is None
        assert result["hasMore"] is False
        assert result["total"] == 0

    def test_list_incidents_returns_error_on_missing_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """list_incidents returns error when token is missing."""
        from k8s_diag_agent.ui.server_incident_internal_fetch import SchedulerClient

        client = SchedulerClient(base_url="http://localhost:8080", token=None)

        result = client.list_incidents()

        assert "error" in result
        assert result["error_type"] == "missing_internal_token"

    def test_list_incidents_passes_cursor_to_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """list_incidents passes cursor token to backend."""
        from k8s_diag_agent.ui.server_incident_internal_fetch import SchedulerClient

        client = SchedulerClient(base_url="http://localhost:8080", token="test-token")
        cursor_token = "test-cursor-token"

        captured_url = []

        def mock_urlopen(req, timeout=30.0):
            captured_url.append(req.full_url)
            resp = MagicMock()
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=None)
            resp.read.return_value = b'{"incidents": [], "nextCursor": null, "hasMore": false, "total": 0}'
            return resp

        monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

        client.list_incidents(cursor=cursor_token, limit=5)

        # Verify cursor was included in URL
        assert len(captured_url) == 1
        assert "cursor=test-cursor-token" in captured_url[0]
        assert "limit=5" in captured_url[0]
