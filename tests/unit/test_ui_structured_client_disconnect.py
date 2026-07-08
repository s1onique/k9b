"""Tests for structured client disconnect handling in UI HTTP server.

This module tests the client disconnect classification and structured error handling
in the UI HTTP transport edge.

Test coverage:
- A: send_json_response handles BrokenPipeError without raw traceback
- B: send_json_response logs success only after write succeeds
- C: server handle_error suppresses raw stderr for client disconnect
- D: server handle_error emits structured ERROR for unexpected exception
- E: ConnectionResetError and ConnectionAbortedError classify the same way
"""

from __future__ import annotations

import errno
import sys
import unittest
import unittest.mock as mock
from io import StringIO

from k8s_diag_agent.ui.server_client_disconnect import (
    CLIENT_DISCONNECT_EXCEPTIONS,
    get_disconnect_errno,
    is_client_disconnect_error,
)
from k8s_diag_agent.ui.server_http import StructuredErrorHTTPServer
from k8s_diag_agent.ui.server_response import send_json_response


class TestClientDisconnectClassifier(unittest.TestCase):
    """Test the is_client_disconnect_error classifier."""

    def test_none_is_not_disconnect(self) -> None:
        """None exception should not be classified as client disconnect."""
        self.assertFalse(is_client_disconnect_error(None))

    def test_broken_pipe_is_disconnect(self) -> None:
        """BrokenPipeError should be classified as client disconnect."""
        exc = BrokenPipeError(errno.EPIPE, "Broken pipe")
        self.assertTrue(is_client_disconnect_error(exc))

    def test_connection_reset_is_disconnect(self) -> None:
        """ConnectionResetError should be classified as client disconnect."""
        exc = ConnectionResetError(errno.ECONNRESET, "Connection reset by peer")
        self.assertTrue(is_client_disconnect_error(exc))

    def test_connection_aborted_is_disconnect(self) -> None:
        """ConnectionAbortedError should be classified as client disconnect."""
        exc = ConnectionAbortedError(errno.ECONNABORTED, "Connection aborted")
        self.assertTrue(is_client_disconnect_error(exc))

    def test_runtime_error_is_not_disconnect(self) -> None:
        """RuntimeError should NOT be classified as client disconnect."""
        exc = RuntimeError("boom")
        self.assertFalse(is_client_disconnect_error(exc))

    def test_value_error_is_not_disconnect(self) -> None:
        """ValueError should NOT be classified as client disconnect."""
        exc = ValueError("invalid value")
        self.assertFalse(is_client_disconnect_error(exc))

    def test_get_disconnect_errno_returns_errno(self) -> None:
        """get_disconnect_errno should return errno from exception."""
        exc = BrokenPipeError(errno.EPIPE, "Broken pipe")
        result = get_disconnect_errno(exc)
        self.assertEqual(result, errno.EPIPE)

    def test_get_disconnect_errno_returns_none_for_non_socket_error(self) -> None:
        """get_disconnect_errno should return None for exceptions without errno."""
        exc = RuntimeError("boom")
        result = get_disconnect_errno(exc)
        self.assertIsNone(result)

    def test_get_disconnect_errno_returns_none_for_none(self) -> None:
        """get_disconnect_errno should return None for None."""
        result = get_disconnect_errno(None)
        self.assertIsNone(result)

    def test_client_disconnect_exceptions_tuple_contains_three(self) -> None:
        """CLIENT_DISCONNECT_EXCEPTIONS should contain exactly 3 exception types."""
        self.assertEqual(len(CLIENT_DISCONNECT_EXCEPTIONS), 3)
        self.assertIn(BrokenPipeError, CLIENT_DISCONNECT_EXCEPTIONS)
        self.assertIn(ConnectionResetError, CLIENT_DISCONNECT_EXCEPTIONS)
        self.assertIn(ConnectionAbortedError, CLIENT_DISCONNECT_EXCEPTIONS)


class TestSendJsonResponseClientDisconnect(unittest.TestCase):
    """Test send_json_response handles client disconnects gracefully."""

    def test_broken_pipe_handled_without_raising(self) -> None:
        """BrokenPipeError from wfile.write should be caught and not escape."""
        captured_logs: list[dict] = []

        def capture_emit(**kwargs: object) -> None:
            captured_logs.append(dict(kwargs))

        # Create a mock handler
        mock_handler = mock.MagicMock()
        mock_handler._response_bytes = 0
        mock_handler.close_connection = False
        # Make wfile.write raise BrokenPipeError
        mock_handler.wfile.write.side_effect = BrokenPipeError(errno.EPIPE, "Broken pipe")

        with mock.patch(
            "k8s_diag_agent.ui.server_response.emit_structured_log",
            side_effect=capture_emit,
        ):
            # Should not raise
            send_json_response(mock_handler, {"test": "data"}, code=200, request_path="/api/test")

        # Verify handler.close_connection was set to True
        self.assertTrue(mock_handler.close_connection)

        # Verify one INFO log was emitted with client_disconnect outcome
        disconnect_logs = [
            log for log in captured_logs
            if log.get("request_outcome") == "client_disconnected"
        ]
        self.assertEqual(len(disconnect_logs), 1)
        log = disconnect_logs[0]
        self.assertEqual(log["component"], "ui-send")
        self.assertEqual(log["severity"], "INFO")
        self.assertEqual(log["exception_type"], "BrokenPipeError")
        self.assertIn("Client disconnected before HTTP response body", log["message"])

    def test_no_http_response_sent_on_broken_pipe(self) -> None:
        """No 'HTTP response sent' log should be emitted when write fails."""
        captured_logs: list[dict] = []

        def capture_emit(**kwargs: object) -> None:
            captured_logs.append(dict(kwargs))

        mock_handler = mock.MagicMock()
        mock_handler._response_bytes = 0
        mock_handler.close_connection = False
        mock_handler.wfile.write.side_effect = BrokenPipeError(errno.EPIPE, "Broken pipe")

        with mock.patch(
            "k8s_diag_agent.ui.server_response.emit_structured_log",
            side_effect=capture_emit,
        ):
            send_json_response(mock_handler, {"test": "data"}, code=200, request_path="/api/test")

        # Verify no "HTTP response sent" log was emitted
        sent_logs = [
            log for log in captured_logs
            if log.get("message") == "HTTP response sent"
        ]
        self.assertEqual(len(sent_logs), 0)

    def test_connection_reset_handled(self) -> None:
        """ConnectionResetError should be handled the same way as BrokenPipeError."""
        captured_logs: list[dict] = []

        def capture_emit(**kwargs: object) -> None:
            captured_logs.append(dict(kwargs))

        mock_handler = mock.MagicMock()
        mock_handler._response_bytes = 0
        mock_handler.close_connection = False
        mock_handler.wfile.write.side_effect = ConnectionResetError(errno.ECONNRESET, "Reset")

        with mock.patch(
            "k8s_diag_agent.ui.server_response.emit_structured_log",
            side_effect=capture_emit,
        ):
            send_json_response(mock_handler, {"test": "data"}, code=200)

        self.assertTrue(mock_handler.close_connection)
        disconnect_logs = [
            log for log in captured_logs
            if log.get("request_outcome") == "client_disconnected"
        ]
        self.assertEqual(len(disconnect_logs), 1)
        self.assertEqual(disconnect_logs[0]["exception_type"], "ConnectionResetError")

    def test_connection_aborted_handled(self) -> None:
        """ConnectionAbortedError should be handled the same way as BrokenPipeError."""
        captured_logs: list[dict] = []

        def capture_emit(**kwargs: object) -> None:
            captured_logs.append(dict(kwargs))

        mock_handler = mock.MagicMock()
        mock_handler._response_bytes = 0
        mock_handler.close_connection = False
        mock_handler.wfile.write.side_effect = ConnectionAbortedError(errno.ECONNABORTED, "Aborted")

        with mock.patch(
            "k8s_diag_agent.ui.server_response.emit_structured_log",
            side_effect=capture_emit,
        ):
            send_json_response(mock_handler, {"test": "data"}, code=200)

        self.assertTrue(mock_handler.close_connection)
        disconnect_logs = [
            log for log in captured_logs
            if log.get("request_outcome") == "client_disconnected"
        ]
        self.assertEqual(len(disconnect_logs), 1)
        self.assertEqual(disconnect_logs[0]["exception_type"], "ConnectionAbortedError")

    def test_success_emits_http_response_sent(self) -> None:
        """When write succeeds, 'HTTP response sent' should be logged."""
        captured_logs: list[dict] = []

        def capture_emit(**kwargs: object) -> None:
            captured_logs.append(dict(kwargs))

        mock_handler = mock.MagicMock()
        mock_handler._response_bytes = 0
        mock_handler.close_connection = False

        with mock.patch(
            "k8s_diag_agent.ui.server_response.emit_structured_log",
            side_effect=capture_emit,
        ):
            send_json_response(mock_handler, {"test": "data"}, code=200, request_path="/api/test")

        # Verify HTTP response sent log was emitted
        sent_logs = [
            log for log in captured_logs
            if log.get("message") == "HTTP response sent"
        ]
        self.assertEqual(len(sent_logs), 1)
        log = sent_logs[0]
        self.assertEqual(log["component"], "ui-send")
        self.assertEqual(log["severity"], "DEBUG")

        # Verify metadata contains payload_bytes
        metadata = log.get("metadata", {})
        self.assertIn("payload_bytes", metadata)
        self.assertGreater(metadata["payload_bytes"], 0)

    def test_success_sets_close_connection(self) -> None:
        """On success, handler.close_connection should be set to True."""
        mock_handler = mock.MagicMock()
        mock_handler._response_bytes = 0
        mock_handler.close_connection = False

        with mock.patch(
            "k8s_diag_agent.ui.server_response.emit_structured_log",
        ):
            send_json_response(mock_handler, {"test": "data"}, code=200)

        self.assertTrue(mock_handler.close_connection)


class TestServerHandleError(unittest.TestCase):
    """Test StructuredErrorHTTPServer.handle_error() behavior."""

    def _make_server(self) -> StructuredErrorHTTPServer:
        """Create a test server with automatic cleanup."""
        server = StructuredErrorHTTPServer(("127.0.0.1", 0), object)
        self.addCleanup(server.server_close)
        return server

    def test_handle_error_suppresses_stderr_for_broken_pipe(self) -> None:
        """BrokenPipeError should not produce raw traceback on stderr."""
        captured_stderr = StringIO()
        server = self._make_server()

        with mock.patch("sys.exc_info", return_value=(BrokenPipeError, BrokenPipeError(errno.EPIPE, "Broken pipe"), None)):
            with mock.patch("sys.stderr", captured_stderr):
                server.handle_error(request=object(), client_address=("127.0.0.1", 12345))

        stderr_output = captured_stderr.getvalue()
        self.assertNotIn("Traceback (most recent call last)", stderr_output)
        self.assertNotIn("Exception occurred during processing", stderr_output)

    def test_handle_error_emits_structured_info_for_broken_pipe(self) -> None:
        """BrokenPipeError should produce structured INFO log."""
        captured_logs: list[dict] = []

        def capture_emit(**kwargs: object) -> None:
            captured_logs.append(dict(kwargs))

        server = self._make_server()

        with mock.patch("sys.exc_info", return_value=(BrokenPipeError, BrokenPipeError(errno.EPIPE, "Broken pipe"), None)):
            with mock.patch("k8s_diag_agent.ui.server_http.emit_structured_log", side_effect=capture_emit):
                server.handle_error(request=object(), client_address=("127.0.0.1", 12345))

        disconnect_logs = [
            log for log in captured_logs
            if log.get("request_outcome") == "client_disconnected"
        ]
        self.assertEqual(len(disconnect_logs), 1)
        log = disconnect_logs[0]
        self.assertEqual(log["component"], "ui-server")
        self.assertEqual(log["severity"], "INFO")
        self.assertEqual(log["exception_type"], "BrokenPipeError")
        self.assertIn("127.0.0.1", log.get("client_address", ""))

    def test_handle_error_emits_structured_error_for_runtime_error(self) -> None:
        """RuntimeError should produce structured ERROR log."""
        captured_logs: list[dict] = []

        def capture_emit(**kwargs: object) -> None:
            captured_logs.append(dict(kwargs))

        server = self._make_server()

        with mock.patch("sys.exc_info", return_value=(RuntimeError, RuntimeError("boom"), None)):
            with mock.patch("k8s_diag_agent.ui.server_http.emit_structured_log", side_effect=capture_emit):
                server.handle_error(request=object(), client_address=("127.0.0.1", 12345))

        exception_logs = [
            log for log in captured_logs
            if log.get("request_outcome") == "exception"
        ]
        self.assertEqual(len(exception_logs), 1)
        log = exception_logs[0]
        self.assertEqual(log["component"], "ui-server")
        self.assertEqual(log["severity"], "ERROR")
        self.assertEqual(log["exception_type"], "RuntimeError")
        self.assertEqual(log["exception_message"], "boom")

    def test_handle_error_suppresses_stderr_for_runtime_error(self) -> None:
        """RuntimeError should not produce raw traceback on stderr."""
        captured_stderr = StringIO()
        server = self._make_server()

        with mock.patch("sys.exc_info", return_value=(RuntimeError, RuntimeError("boom"), None)):
            with mock.patch("sys.stderr", captured_stderr):
                server.handle_error(request=object(), client_address=("127.0.0.1", 12345))

        stderr_output = captured_stderr.getvalue()
        self.assertNotIn("Traceback (most recent call last)", stderr_output)
        self.assertNotIn("Exception occurred during processing", stderr_output)

    def test_handle_error_handles_connection_reset(self) -> None:
        """ConnectionResetError should be treated as client disconnect."""
        captured_logs: list[dict] = []

        def capture_emit(**kwargs: object) -> None:
            captured_logs.append(dict(kwargs))

        server = self._make_server()

        with mock.patch("sys.exc_info", return_value=(ConnectionResetError, ConnectionResetError(errno.ECONNRESET, "Reset"), None)):
            with mock.patch("k8s_diag_agent.ui.server_http.emit_structured_log", side_effect=capture_emit):
                server.handle_error(request=object(), client_address=("192.168.1.1", 54321))

        disconnect_logs = [
            log for log in captured_logs
            if log.get("request_outcome") == "client_disconnected"
        ]
        self.assertEqual(len(disconnect_logs), 1)
        self.assertEqual(disconnect_logs[0]["exception_type"], "ConnectionResetError")
        self.assertEqual(disconnect_logs[0]["severity"], "INFO")

    def test_handle_error_handles_connection_aborted(self) -> None:
        """ConnectionAbortedError should be treated as client disconnect."""
        captured_logs: list[dict] = []

        def capture_emit(**kwargs: object) -> None:
            captured_logs.append(dict(kwargs))

        server = self._make_server()

        with mock.patch("sys.exc_info", return_value=(ConnectionAbortedError, ConnectionAbortedError(errno.ECONNABORTED, "Aborted"), None)):
            with mock.patch("k8s_diag_agent.ui.server_http.emit_structured_log", side_effect=capture_emit):
                server.handle_error(request=object(), client_address=("10.0.0.1", 9999))

        disconnect_logs = [
            log for log in captured_logs
            if log.get("request_outcome") == "client_disconnected"
        ]
        self.assertEqual(len(disconnect_logs), 1)
        self.assertEqual(disconnect_logs[0]["exception_type"], "ConnectionAbortedError")


if __name__ == "__main__":
    unittest.main()
