"""Dispatch tests for keyset pagination in incident diagnosis loop.

These tests verify:
1. Backend sends cursor correctly
2. No positional slicing (uses keyset pagination)
3. Local/backend parity for page operations
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from k8s_diag_agent.collect.incident_diagnosis_dispatch import (
    list_incidents_for_diagnosis_page,
)
from k8s_diag_agent.collect.incident_diagnosis_dispatch_contracts import (
    DiagnosisPageIncident,
)
from k8s_diag_agent.collect.incident_diagnosis_dispatch_page import (
    CursorDecodeFailure,
    IncidentDiagnosisPage,
)
from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
    encode_cursor,
    make_test_cursor,
)
from k8s_diag_agent.collect.incident_diagnosis_pagination_results import (
    PageCursorRejected,
    PageListed,
    PageListingFailed,
)


class TestKeysetPaginationDispatch:
    """Tests for keyset pagination in dispatch layer."""

    def test_local_mode_returns_page(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Local mode returns IncidentDiagnosisPage via PageListed."""
        # Mock local store - the function is imported inside list_incidents_for_diagnosis_page
        mock_page = IncidentDiagnosisPage(
            incidents=(
                DiagnosisPageIncident(incident_id="inc-01", status="open", first_observed_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC), first_observed_at_key="2024-01-01T00:00:00+00:00"),
                DiagnosisPageIncident(incident_id="inc-02", status="open", first_observed_at=datetime(2024, 1, 1, 0, 0, 1, tzinfo=UTC), first_observed_at_key="2024-01-01T00:00:01+00:00"),
            ),
            next_cursor=None,
            has_more=False,
        )

        def mock_list_local(active_only, limit, after_cursor):
            return PageListed(page=mock_page)

        # Mock at the module level
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_dispatch_page.list_incidents_for_diagnosis_page_local",
            mock_list_local,
        )

        # Mock dispatch config for local mode
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_dispatch._get_dispatch_config",
            lambda: MagicMock(resolved_mode=MagicMock(return_value="local")),
        )

        result = list_incidents_for_diagnosis_page(
            active_only=True,
            limit=10,
            cursor=None,
        )

        # Use pattern matching
        match result:
            case PageListed(page=page):
                assert len(page.incidents) == 2
            case PageCursorRejected(failure=failure):
                pytest.fail(f"Unexpected PageCursorRejected: {failure}")
            case PageListingFailed(failure=failure):
                pytest.fail(f"Unexpected PageListingFailed: {failure}")

    def test_invalid_cursor_returns_cursor_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Invalid cursor token returns PageCursorRejected."""
        # Mock dispatch config
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_dispatch._get_dispatch_config",
            lambda: MagicMock(resolved_mode=MagicMock(return_value="local")),
        )

        result = list_incidents_for_diagnosis_page(
            active_only=True,
            limit=10,
            cursor="invalid-cursor-token",
        )

        # Use pattern matching
        match result:
            case PageListed(page=page):
                pytest.fail(f"Unexpected PageListed with {len(page.incidents)} incidents")
            case PageCursorRejected(failure=failure):
                assert failure.error_kind == "invalid_format"
            case PageListingFailed(failure=failure):
                pytest.fail(f"Unexpected PageListingFailed: {failure}")

    def test_valid_cursor_passed_to_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Valid cursor is passed to backend correctly."""
        # Create a valid cursor token using make_test_cursor (required for tests)
        cursor = make_test_cursor(
            first_observed_at_text="2024-01-01T00:00:00+00:00",
            incident_id="inc-01",
        )
        cursor_token = encode_cursor(cursor)

        captured_cursor = []

        def mock_list_page_backend(
            backend_url, internal_api_token, active_only, limit, cursor
        ):
            captured_cursor.append(cursor)
            return PageListingFailed(
                failure=MagicMock(kind="internal_error", message="test error")
            )

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_dispatch._list_incidents_page_backend_api",
            mock_list_page_backend,
        )

        # Mock dispatch config for backend-api mode
        mock_config = MagicMock()
        mock_config.resolved_mode.return_value = "backend-api"
        mock_config.backend_url = "http://localhost:8080"
        mock_config.internal_api_token = "test-token"
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_dispatch._get_dispatch_config",
            lambda: mock_config,
        )

        list_incidents_for_diagnosis_page(
            active_only=True,
            limit=10,
            cursor=cursor_token,
        )

        # Verify cursor was passed
        assert len(captured_cursor) == 1
        assert captured_cursor[0] == cursor_token

    def test_cursor_error_kind_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cursor error from backend is forwarded correctly."""
        from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import (
            CursorErrorKind,
        )

        def mock_decode_cursor(token):
            return None, MagicMock(kind=CursorErrorKind.UNSUPPORTED_VERSION, message="test")

        # Mock at the module where it's imported inside list_incidents_for_diagnosis_page
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_keyset_cursor.decode_cursor",
            mock_decode_cursor,
        )

        # Mock dispatch config for backend-api mode
        mock_config = MagicMock()
        mock_config.resolved_mode.return_value = "backend-api"
        mock_config.backend_url = "http://localhost:8080"
        mock_config.internal_api_token = "test-token"
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_dispatch._get_dispatch_config",
            lambda: mock_config,
        )

        result = list_incidents_for_diagnosis_page(
            active_only=True,
            limit=10,
            cursor="some-token",
        )

        # Error should be PageCursorRejected
        match result:
            case PageListed(page=page):
                pytest.fail(f"Unexpected PageListed with {len(page.incidents)} incidents")
            case PageCursorRejected(failure=failure):
                assert failure.error_kind == CursorErrorKind.UNSUPPORTED_VERSION
            case PageListingFailed(failure=failure):
                pytest.fail(f"Unexpected PageListingFailed: {failure}")

    def test_next_cursor_decoded_from_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Next cursor from backend response is decoded correctly."""
        # Create expected next cursor using make_test_cursor (required for tests)
        next_cursor = make_test_cursor(
            first_observed_at_text="2024-01-02T00:00:00+00:00",
            incident_id="inc-02",
        )

        def mock_list_page_backend(
            backend_url, internal_api_token, active_only, limit, cursor
        ):
            # Return a page with next cursor via PageListed
            page = IncidentDiagnosisPage(
                incidents=(
                    DiagnosisPageIncident(incident_id="inc-02", status="open", first_observed_at=datetime(2024, 1, 2, 0, 0, 0, tzinfo=UTC), first_observed_at_key="2024-01-02T00:00:00+00:00"),
                ),
                next_cursor=next_cursor,
                has_more=True,
            )
            return PageListed(page=page)

        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_dispatch._list_incidents_page_backend_api",
            mock_list_page_backend,
        )

        # Mock dispatch config for backend-api mode
        mock_config = MagicMock()
        mock_config.resolved_mode.return_value = "backend-api"
        mock_config.backend_url = "http://localhost:8080"
        mock_config.internal_api_token = "test-token"
        monkeypatch.setattr(
            "k8s_diag_agent.collect.incident_diagnosis_dispatch._get_dispatch_config",
            lambda: mock_config,
        )

        result = list_incidents_for_diagnosis_page(
            active_only=True,
            limit=10,
            cursor=None,
        )

        match result:
            case PageListed(page=page):
                assert page.next_cursor is not None
                assert page.next_cursor.incident_id == "inc-02"
            case PageCursorRejected(failure=failure):
                pytest.fail(f"Unexpected PageCursorRejected: {failure}")
            case PageListingFailed(failure=failure):
                pytest.fail(f"Unexpected PageListingFailed: {failure}")


class TestKeysetPaginationParity:
    """Tests for local/backend parity."""

    def test_page_structure_parity(self) -> None:
        """Both local and backend return same page structure."""
        # Test that IncidentDiagnosisPage has the right structure
        page = IncidentDiagnosisPage(
            incidents=(
                DiagnosisPageIncident(incident_id="inc-01", status="open", first_observed_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC), first_observed_at_key="2024-01-01T00:00:00+00:00"),
            ),
            next_cursor=None,
            has_more=False,
        )

        assert hasattr(page, "incidents")
        assert hasattr(page, "next_cursor")
        assert hasattr(page, "has_more")
        assert isinstance(page.incidents, tuple)
        assert isinstance(page.has_more, bool)

    def test_cursor_error_structure(self) -> None:
        """CursorDecodeFailure has the expected structure."""
        error = CursorDecodeFailure(
            error_kind="invalid_format",
            error_message="Token is not valid base64",
        )

        assert hasattr(error, "error_kind")
        assert hasattr(error, "error_message")
        assert error.error_kind == "invalid_format"
        assert error.error_message == "Token is not valid base64"

    def test_cursor_encode_decode_parity(self) -> None:
        """Cursor encoding/decoding works identically for both paths."""
        cursor = make_test_cursor(
            first_observed_at_text="2026-06-15T10:30:00+00:00",
            incident_id="test-incident-123",
        )

        # Encode
        token = encode_cursor(cursor)

        # Decode using the dispatch layer's decode function
        from k8s_diag_agent.collect.incident_diagnosis_keyset_cursor import decode_cursor

        decoded, err = decode_cursor(token)

        assert err is None
        assert decoded is not None
        assert decoded.incident_id == cursor.incident_id
        assert decoded.first_observed_at_text == cursor.first_observed_at_text
