"""Tests for mutation request validation (Content-Type and request size limits).

Tests cover:
- Valid application/json Content-Type accepted
- application/json; charset=utf-8 accepted
- Missing Content-Type rejected for POST
- text/plain rejected
- Oversized Content-Length rejected
- Invalid Content-Length header handled safely
- Existing happy-path mutation tests still pass
"""

import unittest
from io import BytesIO

from k8s_diag_agent.ui.server_shared import (
    DEFAULT_MAX_CONTENT_LENGTH,
    _validate_json_mutation_request,
)


class MockHealthUIRequestHandler:
    """Minimal mock handler for testing validation."""

    def __init__(self, headers: dict[str, str] | None = None, body: bytes = b"") -> None:
        self._headers = headers or {}
        self.rfile = BytesIO(body)
        self._sent_json: list[tuple[dict, int]] = []

    @property
    def headers(self) -> dict[str, str]:
        """Return headers as a dict (mimics BaseHTTPRequestHandler.headers property)."""
        return self._headers

    def _send_json(self, data: dict, status: int = 200) -> None:
        self._sent_json.append((data, status))

    @property
    def sent_response(self) -> tuple[dict, int] | None:
        return self._sent_json[-1] if self._sent_json else None


class TestContentTypeValidation(unittest.TestCase):
    """Tests for Content-Type header validation."""

    def test_application_json_accepted(self) -> None:
        """Valid application/json Content-Type should be accepted."""
        handler = MockHealthUIRequestHandler(
            headers={"Content-Type": "application/json", "Content-Length": "10"},
            body=b'{"test":1}',
        )
        result = _validate_json_mutation_request(handler)
        assert result is not None
        self.assertEqual(result, {"test": 1})

    def test_application_json_with_charset_accepted(self) -> None:
        """application/json; charset=utf-8 should be accepted."""
        handler = MockHealthUIRequestHandler(
            headers={"Content-Type": "application/json; charset=utf-8", "Content-Length": "10"},
            body=b'{"test":1}',
        )
        result = _validate_json_mutation_request(handler)
        assert result is not None
        self.assertEqual(result, {"test": 1})

    def test_application_json_uppercase_charset_accepted(self) -> None:
        """application/json; charset=UTF-8 (uppercase) should be accepted."""
        handler = MockHealthUIRequestHandler(
            headers={"Content-Type": "application/json; charset=UTF-8", "Content-Length": "10"},
            body=b'{"test":1}',
        )
        result = _validate_json_mutation_request(handler)
        assert result is not None
        self.assertEqual(result, {"test": 1})

    def test_text_plain_rejected_with_415(self) -> None:
        """text/plain Content-Type should be rejected with 415."""
        handler = MockHealthUIRequestHandler(
            headers={"Content-Type": "text/plain", "Content-Length": "10"},
            body=b'{"test":1}',
        )
        result = _validate_json_mutation_request(handler)
        self.assertIsNone(result)
        assert handler.sent_response is not None
        response, status = handler.sent_response
        self.assertEqual(status, 415)
        self.assertIn("Content-Type", response.get("error", ""))

    def test_form_urlencoded_rejected_with_415(self) -> None:
        """application/x-www-form-urlencoded should be rejected with 415."""
        handler = MockHealthUIRequestHandler(
            headers={"Content-Type": "application/x-www-form-urlencoded", "Content-Length": "10"},
            body=b"test=1",
        )
        result = _validate_json_mutation_request(handler)
        self.assertIsNone(result)
        assert handler.sent_response is not None
        response, status = handler.sent_response
        self.assertEqual(status, 415)

    def test_multipart_form_data_rejected_with_415(self) -> None:
        """multipart/form-data should be rejected with 415."""
        handler = MockHealthUIRequestHandler(
            headers={"Content-Type": "multipart/form-data; boundary=----", "Content-Length": "10"},
            body=b"------",
        )
        result = _validate_json_mutation_request(handler)
        self.assertIsNone(result)
        assert handler.sent_response is not None
        response, status = handler.sent_response
        self.assertEqual(status, 415)

    def test_missing_content_type_rejected_with_415(self) -> None:
        """Missing Content-Type should be rejected with 415."""
        handler = MockHealthUIRequestHandler(
            headers={"Content-Length": "10"},
            body=b'{"test":1}',
        )
        result = _validate_json_mutation_request(handler)
        self.assertIsNone(result)
        assert handler.sent_response is not None
        response, status = handler.sent_response
        self.assertEqual(status, 415)
        self.assertIn("Content-Type", response.get("error", ""))

    def test_empty_content_type_rejected_with_415(self) -> None:
        """Empty Content-Type should be rejected with 415."""
        handler = MockHealthUIRequestHandler(
            headers={"Content-Type": "", "Content-Length": "10"},
            body=b'{"test":1}',
        )
        result = _validate_json_mutation_request(handler)
        self.assertIsNone(result)
        assert handler.sent_response is not None
        response, status = handler.sent_response
        self.assertEqual(status, 415)
        self.assertIn("Content-Type", response.get("error", ""))


class TestContentLengthValidation(unittest.TestCase):
    """Tests for Content-Length validation."""

    def test_oversized_content_rejected_with_413(self) -> None:
        """Content-Length exceeding max should be rejected with 413."""
        # Use a very small max for this test
        handler = MockHealthUIRequestHandler(
            headers={"Content-Type": "application/json", "Content-Length": "1000000"},
            body=b'{"test":1}',
        )
        result = _validate_json_mutation_request(handler, max_content_length=100)
        self.assertIsNone(result)
        assert handler.sent_response is not None
        response, status = handler.sent_response
        self.assertEqual(status, 413)
        self.assertIn("too large", response.get("error", "").lower())

    def test_zero_content_length_rejected_with_400(self) -> None:
        """Zero Content-Length should be rejected with 400."""
        handler = MockHealthUIRequestHandler(
            headers={"Content-Type": "application/json", "Content-Length": "0"},
            body=b"",
        )
        result = _validate_json_mutation_request(handler)
        self.assertIsNone(result)
        assert handler.sent_response is not None
        response, status = handler.sent_response
        self.assertEqual(status, 400)
        self.assertIn("Request body required", response.get("error", ""))

    def test_missing_content_length_rejected_with_400(self) -> None:
        """Missing Content-Length should be rejected with 400."""
        handler = MockHealthUIRequestHandler(
            headers={"Content-Type": "application/json"},
            body=b'{"test":1}',
        )
        result = _validate_json_mutation_request(handler)
        self.assertIsNone(result)
        assert handler.sent_response is not None
        response, status = handler.sent_response
        self.assertEqual(status, 400)

    def test_invalid_content_length_handled_safely(self) -> None:
        """Invalid Content-Length header (non-numeric) should be handled safely."""
        handler = MockHealthUIRequestHandler(
            headers={"Content-Type": "application/json", "Content-Length": "not-a-number"},
            body=b'{"test":1}',
        )
        result = _validate_json_mutation_request(handler)
        self.assertIsNone(result)
        assert handler.sent_response is not None
        response, status = handler.sent_response
        self.assertEqual(status, 400)

    def test_negative_content_length_handled_safely(self) -> None:
        """Negative Content-Length should be handled safely."""
        handler = MockHealthUIRequestHandler(
            headers={"Content-Type": "application/json", "Content-Length": "-10"},
            body=b'{"test":1}',
        )
        result = _validate_json_mutation_request(handler)
        self.assertIsNone(result)
        assert handler.sent_response is not None
        response, status = handler.sent_response
        self.assertEqual(status, 400)


class TestJSONParsingValidation(unittest.TestCase):
    """Tests for JSON parsing validation."""

    def test_malformed_json_rejected_with_400(self) -> None:
        """Malformed JSON should be rejected with 400."""
        handler = MockHealthUIRequestHandler(
            headers={"Content-Type": "application/json", "Content-Length": "15"},
            body=b"not valid json",
        )
        result = _validate_json_mutation_request(handler)
        self.assertIsNone(result)
        assert handler.sent_response is not None
        response, status = handler.sent_response
        self.assertEqual(status, 400)
        self.assertIn("Invalid JSON", response.get("error", ""))

    def test_non_utf8_rejected_with_400(self) -> None:
        """Non-UTF8 bytes should be rejected with 400."""
        handler = MockHealthUIRequestHandler(
            headers={"Content-Type": "application/json", "Content-Length": "10"},
            body=b"\xff\xfe\xfd",
        )
        result = _validate_json_mutation_request(handler)
        self.assertIsNone(result)
        assert handler.sent_response is not None
        response, status = handler.sent_response
        self.assertEqual(status, 400)

    def test_non_dict_json_rejected_with_400(self) -> None:
        """Non-dict JSON (array, string, number) should be rejected with 400."""
        handler = MockHealthUIRequestHandler(
            headers={"Content-Type": "application/json", "Content-Length": "5"},
            body=b'"str"',
        )
        result = _validate_json_mutation_request(handler)
        self.assertIsNone(result)
        assert handler.sent_response is not None
        response, status = handler.sent_response
        self.assertEqual(status, 400)

    def test_json_array_rejected_with_400(self) -> None:
        """JSON array should be rejected with 400."""
        handler = MockHealthUIRequestHandler(
            headers={"Content-Type": "application/json", "Content-Length": "5"},
            body=b"[1,2]",
        )
        result = _validate_json_mutation_request(handler)
        self.assertIsNone(result)
        assert handler.sent_response is not None
        response, status = handler.sent_response
        self.assertEqual(status, 400)


class TestDefaultContentLengthLimit(unittest.TestCase):
    """Tests for the default content length limit."""

    def test_default_limit_is_1_mib(self) -> None:
        """DEFAULT_MAX_CONTENT_LENGTH should be 1 MiB (1048576 bytes)."""
        self.assertEqual(DEFAULT_MAX_CONTENT_LENGTH, 1 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
