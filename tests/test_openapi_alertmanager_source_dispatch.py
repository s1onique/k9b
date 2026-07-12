"""Dispatcher-level tests for AlertManager-source operations.

This module proves the live HTTP-layer code path that the TypeScript client
ultimately calls into, complements the schema-level contract tests in
``test_openapi_alertmanager_source_contract.py``.

Negative slash tests prove that an opaque identifier such as
``crd:monitoring/alertmanager-main`` can be carried end-to-end through the
backend dispatcher without relying on URL-encoded path segments or manual
``unquote`` round trips.
"""

from __future__ import annotations

from typing import Any

import pytest

from k8s_diag_agent.ui.api_dispatch_adapters_nextcheck import (
    _query_first_value,
    handle_alertmanager_source_action_dispatch,
    handle_alertmanager_source_debug_packet_dispatch,
    handle_alertmanager_source_debug_packet_probe_dispatch,
    handle_alertmanager_source_promotion_review_dispatch,
)

# A representative opaque slash-containing source identifier.
SLASH_SOURCE_ID: str = "crd:monitoring/alertmanager-main"


# =============================================================================
# Slash-safe query parsing helper
# =============================================================================


class TestSlashSafeQueryParsing:
    """The query helper used by the dispatchers must round-trip slashes."""

    def test_query_first_value_round_trips_slash(self) -> None:
        query = f"sourceId={SLASH_SOURCE_ID}"
        assert _query_first_value(query, "sourceId") == SLASH_SOURCE_ID

    def test_query_first_value_accepts_percent_encoded(self) -> None:
        """Percent-encoded values are decoded by ``parse_qs`` so callers may
        transparently transport either the canonical form (slash included) or
        a percent-encoded form. Both decode to the same canonical identifier.
        """
        query = "sourceId=crd%3Amonitoring%2Falertmanager-main"
        result = _query_first_value(query, "sourceId")
        # parse_qs transparently decodes percent escapes; downstream sees the
        # canonical form regardless of how the caller transported it.
        assert result == "crd:monitoring/alertmanager-main"

    def test_query_first_value_returns_none_for_missing_key(self) -> None:
        assert _query_first_value("", "sourceId") is None
        assert _query_first_value("foo=bar", "sourceId") is None


# =============================================================================
# Dispatcher stub helpers
# =============================================================================


class _FakeHandler:
    """Minimal HTTP handler stand-in for dispatcher tests."""

    def __init__(self) -> None:
        self.sent: list[tuple[Any, int]] = []
        self.status_code = 0

    # Mimic BaseHTTPRequestHandler._send_json contract
    def _send_json(self, payload: Any, code: int = 200) -> None:
        self.sent.append((payload, code))
        self.status_code = code


# =============================================================================
# Dispatcher tests: query-based sourceId
# =============================================================================


class TestDispatchParsesSourceIdFromQuery:
    """The debug-packet and promotion-review dispatchers must read sourceId from query."""

    def _assert_source_id_passes_to_handler(
        self,
        dispatcher_callable: Any,
        monkeypatch: pytest.MonkeyPatch,
        expected_call_args: tuple[Any, ...],
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_server_handler(handler: Any, *args: Any, **kwargs: Any) -> None:
            captured["args"] = args
            captured["kwargs"] = kwargs
            captured["handler"] = handler

        # The dispatcher imports its server-side handler lazily
        # (``from .server_alertmanager import ...``). We patch the symbol on
        # the target module so the dispatcher's import picks up the fake.
        from k8s_diag_agent.ui import server_alertmanager

        monkeypatch.setattr(
            server_alertmanager,
            expected_call_args[0],
            fake_server_handler,
            raising=False,
        )
        handler = _FakeHandler()
        path_params = {"run_id": "abc12345"}
        dispatcher_callable(handler, f"sourceId={SLASH_SOURCE_ID}", path_params)
        assert captured["args"], "Server handler was not called"
        # ``fake_server_handler`` declares (handler, *args, **kwargs) so
        # ``args`` captures every positional argument *after* the handler.
        # The handler signature is (handler, run_id, source_id), therefore
        # ``args[0]`` is the run_id and ``args[1]`` is the source_id.
        assert captured["args"][0] == "abc12345", captured
        assert captured["args"][1] == SLASH_SOURCE_ID, captured

    def test_debug_packet_dispatcher_reads_source_id_from_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._assert_source_id_passes_to_handler(
            handle_alertmanager_source_debug_packet_dispatch,
            monkeypatch,
            ("handle_alertmanager_source_debug_packet",),
        )

    def test_promotion_review_dispatcher_reads_source_id_from_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._assert_source_id_passes_to_handler(
            handle_alertmanager_source_promotion_review_dispatch,
            monkeypatch,
            ("handle_alertmanager_source_promotion_review",),
        )

    def test_missing_source_id_returns_400_for_debug_packet(self) -> None:
        handler = _FakeHandler()
        handle_alertmanager_source_debug_packet_dispatch(handler, "", {"run_id": "x"})
        assert handler.sent, "Expected _send_json to be called for missing sourceId"
        payload, code = handler.sent[0]
        assert code == 400
        assert "sourceId" in payload.get("error", "")

    def test_missing_source_id_returns_400_for_promotion_review(self) -> None:
        handler = _FakeHandler()
        handle_alertmanager_source_promotion_review_dispatch(
            handler, "other=foo", {"run_id": "x"}
        )
        assert handler.sent, "Expected _send_json to be called for missing sourceId"
        payload, code = handler.sent[0]
        assert code == 400
        assert "sourceId" in payload.get("error", "")


# =============================================================================
# Dispatcher tests: body-based sourceId
# =============================================================================


class TestDispatchParsesSourceIdFromBody:
    """The action and probe dispatchers must read sourceId from the JSON body."""

    def test_action_dispatcher_reads_source_id_from_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from k8s_diag_agent.ui import server_alertmanager

        captured: dict[str, Any] = {}

        def fake_server_handler(
            handler: Any,
            run_id: str,
            source_id: str,
            payload: dict[str, Any],
        ) -> None:
            captured["source_id"] = source_id
            captured["run_id"] = run_id
            captured["payload"] = payload

        monkeypatch.setattr(
            server_alertmanager,
            "handle_alertmanager_source_action",
            fake_server_handler,
            raising=False,
        )
        # The action dispatcher relies on _validate_json_mutation_request to
        # parse the request body. Patch it on server_shared so the dispatcher
        # sees the body we want it to read.
        from k8s_diag_agent.ui import server_shared

        def fake_validate(handler: Any) -> dict[str, Any] | None:
            return {
                "sourceId": SLASH_SOURCE_ID,
                "action": "promote",
                "clusterLabel": "c1",
            }

        monkeypatch.setattr(
            server_shared,
            "_validate_json_mutation_request",
            fake_validate,
            raising=False,
        )
        handler = _FakeHandler()
        handle_alertmanager_source_action_dispatch(handler, "", {"run_id": "run1"})
        assert captured.get("source_id") == SLASH_SOURCE_ID, captured
        assert captured.get("run_id") == "run1", captured

    def test_probe_dispatcher_reads_source_id_from_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from k8s_diag_agent.ui import server_alertmanager

        captured: dict[str, Any] = {}

        def fake_server_handler(
            handler: Any,
            run_id: str,
            source_id: str,
            *,
            probe_now: bool = False,
        ) -> None:
            captured["source_id"] = source_id
            captured["run_id"] = run_id
            captured["probe_now"] = probe_now

        monkeypatch.setattr(
            server_alertmanager,
            "handle_alertmanager_source_debug_packet",
            fake_server_handler,
            raising=False,
        )
        from k8s_diag_agent.ui import server_shared

        def fake_validate(handler: Any) -> dict[str, Any] | None:
            return {"sourceId": SLASH_SOURCE_ID}

        monkeypatch.setattr(
            server_shared,
            "_validate_json_mutation_request",
            fake_validate,
            raising=False,
        )
        handler = _FakeHandler()
        handle_alertmanager_source_debug_packet_probe_dispatch(
            handler, "", {"run_id": "run2"}
        )
        assert captured.get("source_id") == SLASH_SOURCE_ID, captured
        assert captured.get("run_id") == "run2", captured
        assert captured.get("probe_now") is True, captured

    def test_action_dispatcher_rejects_missing_source_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from k8s_diag_agent.ui import server_shared

        def fake_validate(handler: Any) -> dict[str, Any] | None:
            return {"action": "promote", "clusterLabel": "c1"}

        monkeypatch.setattr(
            server_shared,
            "_validate_json_mutation_request",
            fake_validate,
            raising=False,
        )
        handler = _FakeHandler()
        handle_alertmanager_source_action_dispatch(handler, "", {"run_id": "x"})
        assert handler.sent, "Expected 400 for missing sourceId"
        payload, code = handler.sent[0]
        assert code == 400
        assert "sourceId" in payload.get("error", "")
