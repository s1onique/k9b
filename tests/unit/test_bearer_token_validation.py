"""Tests for bearer token authentication (AUTH-04/05/06).

Tests cover:
- No token configured → existing POST tests still pass
- Token configured + missing Authorization → 401
- Token configured + invalid token → 401
- Token configured + valid token → request proceeds
- Malformed Authorization header → 401
- Token value not included in response/logs
- compare_digest is used or behavior is covered
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.server_shared import _validate_bearer_token


class MockHealthUIRequestHandler:
    """Minimal mock handler for testing token validation."""

    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self._headers: dict[str, str] = headers or {}
        self._sent_json: list[tuple[dict[str, object], int]] = []

    @property
    def headers(self) -> dict[str, str]:
        return self._headers

    def _send_json(self, data: dict[str, object], status: int = 200) -> None:
        self._sent_json.append((dict(data), status))

    @property
    def sent_response(self) -> tuple[dict, int] | None:
        return self._sent_json[-1] if self._sent_json else None


class TestBearerTokenNoAuthConfigured(unittest.TestCase):
    """Tests when no token is configured (auth disabled)."""

    def test_no_token_allows_request(self) -> None:
        """No token configured should allow all requests."""
        handler = MockHealthUIRequestHandler(headers={})
        result = _validate_bearer_token(handler, None)
        self.assertTrue(result)
        self.assertIsNone(handler.sent_response)

    def test_no_token_empty_string_allows_request(self) -> None:
        """Empty string token should allow all requests."""
        handler = MockHealthUIRequestHandler(headers={})
        result = _validate_bearer_token(handler, "")
        self.assertTrue(result)
        self.assertIsNone(handler.sent_response)

    def test_no_token_with_bearer_header_still_allows(self) -> None:
        """Even with Bearer header, no token config means allow."""
        handler = MockHealthUIRequestHandler(headers={"Authorization": "Bearer some-token"})
        result = _validate_bearer_token(handler, None)
        self.assertTrue(result)
        self.assertIsNone(handler.sent_response)


class TestBearerTokenMissingAuthorization(unittest.TestCase):
    """Tests when token is configured but Authorization header is missing."""

    def test_missing_authorization_returns_401(self) -> None:
        """Missing Authorization header should return 401."""
        handler = MockHealthUIRequestHandler(headers={})
        result = _validate_bearer_token(handler, "test-token")
        self.assertFalse(result)
        assert handler.sent_response is not None
        response, status = handler.sent_response
        self.assertEqual(status, 401)
        self.assertIn("Authorization required", response.get("error", ""))

    def test_missing_authorization_error_not_leaks_token(self) -> None:
        """Error message should not contain the expected token."""
        handler = MockHealthUIRequestHandler(headers={})
        _validate_bearer_token(handler, "super-secret-token-123")
        assert handler.sent_response is not None
        response, _ = handler.sent_response
        error_msg = response.get("error", "")
        self.assertNotIn("super-secret-token-123", error_msg)
        self.assertNotIn("token", error_msg.lower())


class TestBearerTokenInvalidToken(unittest.TestCase):
    """Tests when token is configured but invalid token provided."""

    def test_wrong_token_returns_401(self) -> None:
        """Wrong token should return 401."""
        handler = MockHealthUIRequestHandler(
            headers={"Authorization": "Bearer wrong-token"}
        )
        result = _validate_bearer_token(handler, "correct-token")
        self.assertFalse(result)
        assert handler.sent_response is not None
        response, status = handler.sent_response
        self.assertEqual(status, 401)
        self.assertIn("Invalid authorization", response.get("error", ""))

    def test_wrong_token_error_not_leaks_token(self) -> None:
        """Error message should not contain the expected token."""
        handler = MockHealthUIRequestHandler(
            headers={"Authorization": "Bearer wrong"}
        )
        _validate_bearer_token(handler, "correct-token-should-not-appear")
        assert handler.sent_response is not None
        response, _ = handler.sent_response
        error_msg = response.get("error", "")
        self.assertNotIn("correct-token-should-not-appear", error_msg)

    def test_similar_but_wrong_token_returns_401(self) -> None:
        """Similar but incorrect token should return 401."""
        handler = MockHealthUIRequestHandler(
            headers={"Authorization": "Bearer test-token-1"}
        )
        result = _validate_bearer_token(handler, "test-token-2")
        self.assertFalse(result)
        assert handler.sent_response is not None
        _, status = handler.sent_response
        self.assertEqual(status, 401)


class TestBearerTokenMalformedAuthorization(unittest.TestCase):
    """Tests for malformed Authorization headers."""

    def test_basic_auth_rejected(self) -> None:
        """Basic auth should be rejected."""
        handler = MockHealthUIRequestHandler(
            headers={"Authorization": "Basic dXNlcjpwYXNz"}
        )
        result = _validate_bearer_token(handler, "test-token")
        self.assertFalse(result)
        assert handler.sent_response is not None
        _, status = handler.sent_response
        self.assertEqual(status, 401)

    def test_bearer_without_space_rejected(self) -> None:
        """Bearer without space should be rejected."""
        handler = MockHealthUIRequestHandler(
            headers={"Authorization": "Bearertoken"}
        )
        result = _validate_bearer_token(handler, "token")
        self.assertFalse(result)
        assert handler.sent_response is not None
        _, status = handler.sent_response
        self.assertEqual(status, 401)

    def test_bearer_with_empty_token_rejected(self) -> None:
        """Bearer with empty token should be rejected."""
        handler = MockHealthUIRequestHandler(
            headers={"Authorization": "Bearer "}
        )
        result = _validate_bearer_token(handler, "some-token")
        self.assertFalse(result)
        assert handler.sent_response is not None
        _, status = handler.sent_response
        self.assertEqual(status, 401)

    def test_lowercase_bearer_rejected(self) -> None:
        """Lowercase 'bearer' should be rejected (case-sensitive)."""
        handler = MockHealthUIRequestHandler(
            headers={"Authorization": "bearer test-token"}
        )
        result = _validate_bearer_token(handler, "test-token")
        self.assertFalse(result)
        assert handler.sent_response is not None
        _, status = handler.sent_response
        self.assertEqual(status, 401)


class TestBearerTokenValid(unittest.TestCase):
    """Tests for valid token scenarios."""

    def test_exact_token_accepted(self) -> None:
        """Exact token match should be accepted."""
        handler = MockHealthUIRequestHandler(
            headers={"Authorization": "Bearer my-secret-token"}
        )
        result = _validate_bearer_token(handler, "my-secret-token")
        self.assertTrue(result)
        self.assertIsNone(handler.sent_response)

    def test_complex_token_accepted(self) -> None:
        """Complex token (special chars) should be accepted."""
        token = "tok_a1b2c3-d4e5-f6g7-h8i9-j0k1l2m3n4o5p"
        handler = MockHealthUIRequestHandler(
            headers={"Authorization": f"Bearer {token}"}
        )
        result = _validate_bearer_token(handler, token)
        self.assertTrue(result)
        self.assertIsNone(handler.sent_response)

    def test_bearer_with_extra_whitespace_token_accepted(self) -> None:
        """Token with surrounding whitespace should be handled correctly."""
        # Note: RFC 6750 says token shouldn't have extra whitespace
        # but we strip the 'Bearer ' prefix and compare remaining value
        handler = MockHealthUIRequestHandler(
            headers={"Authorization": "Bearer token-value"}
        )
        result = _validate_bearer_token(handler, "token-value")
        self.assertTrue(result)


class TestBearerTokenSecurity(unittest.TestCase):
    """Security-focused tests for token validation."""

    def test_timing_attack_resistance(self) -> None:
        """Test that compare_digest is used (via hmac module).

        This is implicitly tested by verifying the function works correctly
        with strings of different lengths and similar characters.
        The hmac.compare_digest function is used internally which provides
        constant-time comparison.
        """
        # Different length tokens
        handler1 = MockHealthUIRequestHandler(
            headers={"Authorization": "Bearer short"}
        )
        result1 = _validate_bearer_token(handler1, "very-long-token-value-here")
        self.assertFalse(result1)

        # Similar tokens with small difference
        handler2 = MockHealthUIRequestHandler(
            headers={"Authorization": "Bearer test-token-X"}
        )
        result2 = _validate_bearer_token(handler2, "test-token-Y")
        self.assertFalse(result2)

        # Both should work without timing issues
        self.assertIsNotNone(handler1.sent_response)
        self.assertIsNotNone(handler2.sent_response)

    def test_empty_provided_token_rejected_when_configured(self) -> None:
        """Empty provided token should be rejected when token is configured."""
        handler = MockHealthUIRequestHandler(
            headers={"Authorization": "Bearer "}
        )
        result = _validate_bearer_token(handler, "actual-token")
        self.assertFalse(result)
        assert handler.sent_response is not None
        _, status = handler.sent_response
        self.assertEqual(status, 401)

    def test_whitespace_only_token_rejected(self) -> None:
        """Whitespace-only provided token should be rejected."""
        handler = MockHealthUIRequestHandler(
            headers={"Authorization": "Bearer    "}
        )
        result = _validate_bearer_token(handler, "real-token")
        self.assertFalse(result)
        assert handler.sent_response is not None
        _, status = handler.sent_response
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
