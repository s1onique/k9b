"""Tests for server_incident_automatic_diagnosis_loop request parsing.

Focused tests for:
1. Budget propagation through _parse_request_config
2. Invalid config hardening (booleans, strings, zero, negative values)
"""

from typing import Protocol


class MockHandler(Protocol):
    """Minimal protocol for HealthUIRequestHandler used in tests."""

    body: str | None


class TestParseRequestConfigValidation:
    """Tests for _parse_request_config semantic validation.

    These tests verify that _parse_request_config properly validates
    budget fields using _positive_int(), rejecting booleans, strings,
    zero, and negative values in favor of safe defaults.
    """

    def test_parse_returns_none_for_empty_body(self) -> None:
        """Empty body returns None (no config to parse)."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _parse_request_config,
        )

        handler: MockHandler = MockHandlerImpl(None)
        result = _parse_request_config(handler)  # type: ignore[arg-type]
        assert result is None

    def test_parse_returns_none_for_invalid_json(self) -> None:
        """Invalid JSON returns None."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _parse_request_config,
        )

        handler: MockHandler = MockHandlerImpl("not valid json")
        result = _parse_request_config(handler)  # type: ignore[arg-type]
        assert result is None

    def test_parse_returns_none_for_non_dict_json(self) -> None:
        """JSON array/string returns None."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _parse_request_config,
        )

        handler: MockHandler = MockHandlerImpl('["not", "a", "dict"]')
        result = _parse_request_config(handler)  # type: ignore[arg-type]
        assert result is None

        handler2: MockHandler = MockHandlerImpl('"just a string"')
        result2 = _parse_request_config(handler2)  # type: ignore[arg-type]
        assert result2 is None

    def test_parse_returns_none_for_non_config_body(self) -> None:
        """Body without config fields returns None."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _parse_request_config,
        )

        handler: MockHandler = MockHandlerImpl('{"incident_id": "test-123"}')
        result = _parse_request_config(handler)  # type: ignore[arg-type]
        assert result is None

    def test_parse_creates_config_with_valid_values(self) -> None:
        """Valid budget values are passed through correctly."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _parse_request_config,
        )

        handler: MockHandler = MockHandlerImpl('{"max_passes_per_incident": 5}')
        result = _parse_request_config(handler)  # type: ignore[arg-type]
        assert result is not None
        assert result.max_passes_per_incident == 5

    def test_parse_rejects_boolean_true_for_max_passes(self) -> None:
        """Boolean true is rejected for max_passes_per_incident.

        JSON booleans are distinct from integers. True should use default.
        """
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _parse_request_config,
        )

        handler: MockHandler = MockHandlerImpl('{"max_passes_per_incident": true}')
        result = _parse_request_config(handler)  # type: ignore[arg-type]
        assert result is not None
        assert result.max_passes_per_incident == 1  # default

    def test_parse_rejects_boolean_false_for_max_passes(self) -> None:
        """Boolean false is rejected for max_passes_per_incident."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _parse_request_config,
        )

        handler: MockHandler = MockHandlerImpl('{"max_passes_per_incident": false}')
        result = _parse_request_config(handler)  # type: ignore[arg-type]
        assert result is not None
        assert result.max_passes_per_incident == 1  # default

    def test_parse_rejects_zero_for_max_passes(self) -> None:
        """Zero is rejected for max_passes_per_incident (not a valid budget)."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _parse_request_config,
        )

        handler: MockHandler = MockHandlerImpl('{"max_passes_per_incident": 0}')
        result = _parse_request_config(handler)  # type: ignore[arg-type]
        assert result is not None
        assert result.max_passes_per_incident == 1  # default

    def test_parse_rejects_negative_for_max_passes(self) -> None:
        """Negative values are rejected for max_passes_per_incident."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _parse_request_config,
        )

        handler: MockHandler = MockHandlerImpl('{"max_passes_per_incident": -1}')
        result = _parse_request_config(handler)  # type: ignore[arg-type]
        assert result is not None
        assert result.max_passes_per_incident == 1  # default

    def test_parse_rejects_string_for_max_passes(self) -> None:
        """String values are rejected for max_passes_per_incident."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _parse_request_config,
        )

        handler: MockHandler = MockHandlerImpl('{"max_passes_per_incident": "5"}')
        result = _parse_request_config(handler)  # type: ignore[arg-type]
        assert result is not None
        assert result.max_passes_per_incident == 1  # default

    def test_parse_rejects_float_for_max_passes(self) -> None:
        """Float values are rejected for max_passes_per_incident."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _parse_request_config,
        )

        handler: MockHandler = MockHandlerImpl('{"max_passes_per_incident": 5.0}')
        result = _parse_request_config(handler)  # type: ignore[arg-type]
        assert result is not None
        assert result.max_passes_per_incident == 1  # default

    def test_parse_uses_defaults_for_missing_budget_fields(self) -> None:
        """Missing budget fields use defaults."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _parse_request_config,
        )

        handler: MockHandler = MockHandlerImpl('{"max_passes_per_incident": 5}')
        result = _parse_request_config(handler)  # type: ignore[arg-type]
        assert result is not None
        # max_passes_per_incident is set
        assert result.max_passes_per_incident == 5
        # Others use defaults
        assert result.max_checks_per_pass == 5
        assert result.max_incidents_per_run == 10

    def test_p4c_scenario_config_parsing(self) -> None:
        """P4c lab scenario config is parsed correctly.

        P4c requires MIN_REQUIRED_PASSES=2, so budget must be >= 2.
        """
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _parse_request_config,
        )

        handler: MockHandler = MockHandlerImpl('{"max_passes_per_incident": 5}')
        result = _parse_request_config(handler)  # type: ignore[arg-type]
        assert result is not None
        # P4c with MIN_REQUIRED_PASSES=2 requires budget >= 2
        assert result.max_passes_per_incident >= 2


class MockHandlerImpl:
    """Concrete implementation of MockHandler for tests."""

    def __init__(self, body: str | None) -> None:
        self.body = body


class TestReadRequestBody:
    """Tests for _read_request_body function.

    Regression tests for the bug where HealthUIRequestHandler.body was
    accessed directly, causing AttributeError on real HTTP handlers.
    BaseHTTPRequestHandler does not define .body - it exposes request
    payload via rfile + Content-Length header.
    """

    def test_read_body_from_handler_with_body_attribute(self) -> None:
        """Handler with .body attribute returns that attribute."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _read_request_body,
        )

        class HandlerWithBody:
            body = b'{"max_passes_per_incident": 5}'

        result = _read_request_body(HandlerWithBody())
        assert result == b'{"max_passes_per_incident": 5}'

    def test_read_body_from_handler_with_string_body(self) -> None:
        """Handler with string .body returns encoded bytes."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _read_request_body,
        )

        class HandlerWithStringBody:
            body = '{"max_passes_per_incident": 3}'

        result = _read_request_body(HandlerWithStringBody())
        assert result == b'{"max_passes_per_incident": 3}'

    def test_read_body_from_handler_without_body_attribute(self) -> None:
        """Handler without .body attribute reads from rfile + Content-Length."""
        from io import BytesIO

        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _read_request_body,
        )

        body_bytes = b'{"max_passes_per_incident": 5}'

        class HandlerWithoutBody:
            """Simulates real HealthUIRequestHandler without .body attribute."""

            class Headers:
                def get(self, key: str, default: str = "") -> str:
                    return str(len(body_bytes))  # Actual length

            headers = Headers()

            def __init__(self, body: bytes) -> None:
                self.rfile = BytesIO(body)

        handler = HandlerWithoutBody(body_bytes)
        result = _read_request_body(handler)
        assert result == body_bytes

    def test_read_body_empty_when_no_body_no_headers(self) -> None:
        """Handler without .body and no headers returns empty bytes."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _read_request_body,
        )

        class EmptyHandler:
            pass

        result = _read_request_body(EmptyHandler())
        assert result == b""

    def test_read_body_empty_when_content_length_zero(self) -> None:
        """Handler without .body and Content-Length: 0 returns empty bytes."""
        from io import BytesIO

        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _read_request_body,
        )

        class HandlerZeroContentLength:
            class Headers:
                def get(self, key: str, default: str = "") -> str:
                    return "0"

            headers = Headers()
            rfile = BytesIO(b"should not be read")

        result = _read_request_body(HandlerZeroContentLength())
        assert result == b""

    def test_read_body_returns_empty_when_rfile_missing(self) -> None:
        """Handler without .body and no rfile returns empty bytes."""
        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _read_request_body,
        )

        class HandlerNoRfile:
            class Headers:
                def get(self, key: str, default: str = "") -> str:
                    return "10"

            headers = Headers()
            # No rfile attribute

        result = _read_request_body(HandlerNoRfile())
        assert result == b""


class TestParseRequestConfigWithRfile:
    """Tests for _parse_request_config using rfile + Content-Length path.

    These tests verify that the handler works with real HTTP primitives
    instead of assuming .body attribute exists.
    """

    def test_parse_config_from_rfile_content_length(self) -> None:
        """Config parsed from rfile + Content-Length (no .body attribute)."""
        from io import BytesIO

        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _parse_request_config,
        )

        body_bytes = b'{"max_passes_per_incident": 3}'

        class HandlerRfile:
            """Simulates real HealthUIRequestHandler."""

            command = "POST"

            class Headers:
                def get(self, key: str, default: str = "") -> str:
                    return str(len(body_bytes))  # Actual length

            headers = Headers()

            def __init__(self, body: bytes) -> None:
                self.rfile = BytesIO(body)
                # NOTE: No .body attribute - this is the real handler

        handler = HandlerRfile(body_bytes)
        result = _parse_request_config(handler)  # type: ignore[arg-type]

        assert result is not None
        assert result.max_passes_per_incident == 3

    def test_parse_empty_body_returns_none(self) -> None:
        """Empty request (no body) returns None, not AttributeError."""
        from io import BytesIO

        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _parse_request_config,
        )

        class HandlerEmptyBody:
            class Headers:
                def get(self, key: str, default: str = "") -> str:
                    return "0"

            headers = Headers()
            rfile = BytesIO(b"")

        handler = HandlerEmptyBody()
        result = _parse_request_config(handler)  # type: ignore[arg-type]
        assert result is None

    def test_no_attribute_error_when_body_attr_missing(self) -> None:
        """No AttributeError when handler has no .body attribute.

        This is the core regression test for the bug where real
        HealthUIRequestHandler was assumed to have .body.
        """
        from io import BytesIO

        from k8s_diag_agent.ui.server_incident_automatic_diagnosis_loop import (
            _parse_request_config,
        )

        class RealHandlerNoBodyAttr:
            """Real BaseHTTPRequestHandler-like handler."""

            command = "POST"

            class Headers:
                def get(self, key: str, default: str = "") -> str:
                    return "0"

            headers = Headers()
            rfile = BytesIO(b"")

            # Intentionally no .body attribute
            # Real BaseHTTPRequestHandler does not define this

        handler = RealHandlerNoBodyAttr()
        # Should NOT raise AttributeError
        result = _parse_request_config(handler)  # type: ignore[arg-type]
        assert result is None
