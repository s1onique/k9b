"""Tests for P0b provider health envelope handling.

This test module covers the fix for the P0b failure where the curl wrapper
emits a known diagnostic envelope around provider health JSON:
  - STDOUT_BLOCK prefix (optional)
  - Valid provider health JSON
  - STDERR_BLOCK marker
  - CURL_EXIT=<code>
  - HTTP_CODE=<code>

The fix makes known envelope patterns NON-FATAL by extracting the JSON body
and parsing it separately.
"""

from __future__ import annotations

import json

import pytest

from scripts.lab_common.provider_preflight_health import (
    ProviderHealthPayload,
    _extract_provider_health_payload,
)
from scripts.lab_common.provider_preflight_json_classification import (
    _looks_like_curl_framing_suffix,
)


class TestExtractProviderHealthPayload:
    """Tests for _extract_provider_health_payload function."""

    def test_extracts_clean_json_without_envelope(self) -> None:
        """Clean valid JSON without envelope should work normally."""
        raw = '{"available": true, "provider": "test"}'
        payload = _extract_provider_health_payload(raw)

        assert payload.json_body == '{"available": true, "provider": "test"}'
        assert payload.envelope_detected is False
        assert payload.curl_exit is None
        assert payload.http_code is None
        assert payload.stderr_block == ""
        assert payload.raw_suffix == ""

    def test_extracts_json_with_full_envelope_suffix(self) -> None:
        """JSON with full envelope suffix should be parsed correctly."""
        raw = (
            '{"available": true, "provider": "test"}\n'
            "STDERR_BLOCK\n"
            "CURL_EXIT=0\n"
            "HTTP_CODE=200\n"
        )
        payload = _extract_provider_health_payload(raw)

        assert payload.envelope_detected is True
        assert json.loads(payload.json_body)["available"] is True
        assert payload.curl_exit == 0
        assert payload.http_code == 200

    def test_extracts_json_with_known_stderr_envelope_suffix(self) -> None:
        """JSON with known stderr envelope suffix (from live lab failure) should be accepted."""
        raw = (
            '{"available": true, "provider": "test"}\n'
            "STDERR_BLOCK\n"
            "debug noise from curl wrapper\n"
            "CURL_EXIT=0\n"
            "HTTP_CODE=200\n"
        )
        payload = _extract_provider_health_payload(raw)

        assert payload.envelope_detected is True
        assert json.loads(payload.json_body)["available"] is True
        assert payload.curl_exit == 0
        assert payload.http_code == 200
        assert "debug noise" in payload.stderr_block

    def test_extracts_json_with_stdout_block_prefix(self) -> None:
        """JSON with STDOUT_BLOCK prefix should strip the prefix."""
        raw = (
            "STDOUT_BLOCK\n"
            '{"available": true, "provider": "test"}\n'
            "STDERR_BLOCK\n"
            "CURL_EXIT=0\n"
            "HTTP_CODE=200\n"
        )
        payload = _extract_provider_health_payload(raw)

        assert payload.envelope_detected is True
        assert json.loads(payload.json_body)["available"] is True
        assert payload.curl_exit == 0
        assert payload.http_code == 200

    def test_rejects_json_with_only_curl_exit(self) -> None:
        """JSON with only CURL_EXIT suffix (no HTTP_CODE) is rejected as contamination."""
        raw = '{"available": true}\nCURL_EXIT=0\n'
        payload = _extract_provider_health_payload(raw)

        # Both CURL_EXIT=0 AND HTTP_CODE=200 are required
        assert payload.envelope_detected is False
        assert payload.raw_suffix == "CURL_EXIT=0"

    def test_rejects_json_with_only_http_code(self) -> None:
        """JSON with only HTTP_CODE suffix (no CURL_EXIT) is rejected as contamination."""
        raw = '{"available": true}\nHTTP_CODE=200\n'
        payload = _extract_provider_health_payload(raw)

        # Both CURL_EXIT=0 AND HTTP_CODE=200 are required
        assert payload.envelope_detected is False
        assert payload.raw_suffix == "HTTP_CODE=200"

    def test_rejects_unknown_suffix_contamination(self) -> None:
        """JSON with unknown trailing text should be flagged as raw_suffix."""
        raw = '{"available": true}\nUNEXPECTED_TRAILER\n'
        payload = _extract_provider_health_payload(raw)

        assert payload.envelope_detected is False
        assert payload.raw_suffix == "UNEXPECTED_TRAILER"

    def test_rejects_unknown_prefix_contamination(self) -> None:
        """JSON with unknown prefix should return envelope_detected=False."""
        raw = "UNKNOWN_PREFIX\n{'available': true}\n"
        payload = _extract_provider_health_payload(raw)

        # The raw JSON is invalid, so it returns the text as-is
        assert payload.envelope_detected is False

    def test_handles_whitespace_before_envelope(self) -> None:
        """Whitespace between JSON and envelope should be stripped."""
        raw = '{"available": true}  \nSTDERR_BLOCK\nCURL_EXIT=0\nHTTP_CODE=200\n'
        payload = _extract_provider_health_payload(raw)

        assert payload.envelope_detected is True
        assert json.loads(payload.json_body)["available"] is True

    def test_handles_empty_stderr_block(self) -> None:
        """STDERR_BLOCK with no content should not fail."""
        raw = '{"available": true}\nSTDERR_BLOCK\n\nCURL_EXIT=0\nHTTP_CODE=200\n'
        payload = _extract_provider_health_payload(raw)

        assert payload.envelope_detected is True
        assert payload.stderr_block == ""


class TestLooksLikeCurlFramingSuffix:
    """Tests for _looks_like_curl_framing_suffix function."""

    def test_detects_curl_exit(self) -> None:
        """CURL_EXIT=0 should be detected."""
        assert _looks_like_curl_framing_suffix("CURL_EXIT=0") is True

    def test_detects_http_code(self) -> None:
        """HTTP_CODE=200 should be detected."""
        assert _looks_like_curl_framing_suffix("HTTP_CODE=200") is True

    def test_detects_stderr_block(self) -> None:
        """STDERR_BLOCK should be detected."""
        assert _looks_like_curl_framing_suffix("STDERR_BLOCK") is True

    def test_detects_curl_start(self) -> None:
        """---CURL_START--- should be detected."""
        assert _looks_like_curl_framing_suffix("---CURL_START---") is True

    def test_detects_resolving_host(self) -> None:
        """RESOLVING_HOST=... should be detected."""
        assert _looks_like_curl_framing_suffix("RESOLVING_HOST=example.com") is True

    def test_detects_no_response_body(self) -> None:
        """NO_RESPONSE_BODY should be detected."""
        assert _looks_like_curl_framing_suffix("NO_RESPONSE_BODY") is True

    def test_rejects_arbitrary_text(self) -> None:
        """Arbitrary text should NOT be detected as curl framing."""
        assert _looks_like_curl_framing_suffix("some random text") is False
        assert _looks_like_curl_framing_suffix("UNEXPECTED_TRAILER") is False

    def test_rejects_json_suffix(self) -> None:
        """Adjacent JSON should NOT be detected as curl framing."""
        assert _looks_like_curl_framing_suffix('{"key": "value"}') is False

    def test_rejects_json_array_suffix(self) -> None:
        """JSON array suffix should NOT be detected as curl framing."""
        assert _looks_like_curl_framing_suffix("[1, 2, 3]") is False


class TestProviderHealthPayloadDataclass:
    """Tests for ProviderHealthPayload dataclass."""

    def test_dataclass_is_frozen(self) -> None:
        """ProviderHealthPayload should be immutable."""
        payload = ProviderHealthPayload(
            json_body='{"test": true}',
            stderr_block="",
            curl_exit=0,
            http_code=200,
            envelope_detected=True,
            raw_suffix="",
        )
        with pytest.raises(AttributeError):
            payload.json_body = "modified"  # type: ignore

    def test_dataclass_fields(self) -> None:
        """All expected fields should be present."""
        payload = ProviderHealthPayload(
            json_body='{"test": true}',
            stderr_block="debug output",
            curl_exit=0,
            http_code=200,
            envelope_detected=True,
            raw_suffix="",
        )
        assert payload.json_body == '{"test": true}'
        assert payload.stderr_block == "debug output"
        assert payload.curl_exit == 0
        assert payload.http_code == 200
        assert payload.envelope_detected is True
        assert payload.raw_suffix == ""

    def test_dataclass_with_no_envelope(self) -> None:
        """Dataclass should handle no envelope case."""
        payload = ProviderHealthPayload(
            json_body='{"test": true}',
            stderr_block="",
            curl_exit=None,
            http_code=None,
            envelope_detected=False,
            raw_suffix="",
        )
        assert payload.curl_exit is None
        assert payload.http_code is None
        assert payload.envelope_detected is False


class TestStreamSeparationRegression:
    """Regression tests for stream separation (stdout vs stderr metadata).

    These tests verify the invariant that:
    - Provider JSON body is parsed ONLY from stdout
    - STDERR_BLOCK, CURL_EXIT, HTTP_CODE are envelope metadata, not JSON body
    - Contamination detection works correctly when known patterns follow valid JSON
    """

    def test_parser_extracts_stderr_block_content_from_known_envelope(self) -> None:
        """Valid JSON followed by STDERR_BLOCK with CURL_EXIT/HTTP_CODE is parsed as known envelope."""
        raw = '{"available": true, "provider": "test"}\nSTDERR_BLOCK\nboom\nCURL_EXIT=0\nHTTP_CODE=200'
        payload = _extract_provider_health_payload(raw)

        # Full envelope with CURL_EXIT=0 AND HTTP_CODE=200 is accepted
        assert payload.envelope_detected is True
        assert payload.json_body == '{"available": true, "provider": "test"}'
        assert payload.stderr_block == "boom"

    def test_parser_extracts_json_from_clean_output(self) -> None:
        """Clean JSON without envelope should parse correctly."""
        raw = '{"available": true, "provider": "test"}'
        payload = _extract_provider_health_payload(raw)

        assert payload.envelope_detected is False
        assert payload.json_body == '{"available": true, "provider": "test"}'
        assert payload.raw_suffix == ""

    def test_curl_framing_detects_stderr_block(self) -> None:
        """STDERR_BLOCK should be detected as curl framing."""
        from scripts.lab_common.provider_preflight_json_classification import (
            _looks_like_curl_framing_suffix,
        )

        assert _looks_like_curl_framing_suffix("STDERR_BLOCK") is True
        assert _looks_like_curl_framing_suffix("STDERR_BLOCK\nsome error") is True

    def test_curl_framing_rejects_non_curl_trailing_text(self) -> None:
        """Non-curl trailing text should NOT be detected as curl framing."""
        from scripts.lab_common.provider_preflight_json_classification import (
            _looks_like_curl_framing_suffix,
        )

        assert _looks_like_curl_framing_suffix("random error message") is False
        assert _looks_like_curl_framing_suffix("unexpected output") is False

    def test_stderr_block_with_empty_content_is_valid_envelope(self) -> None:
        """STDERR_BLOCK with empty content should be valid envelope."""
        raw = '{"available": true}\nSTDERR_BLOCK\n\nCURL_EXIT=0\nHTTP_CODE=200'
        payload = _extract_provider_health_payload(raw)

        assert payload.envelope_detected is True
        assert payload.json_body == '{"available": true}'
        assert payload.curl_exit == 0
        assert payload.http_code == 200
        assert payload.stderr_block == ""

    def test_rejects_json_with_only_stderr_block_suffix(self) -> None:
        """JSON with only STDERR_BLOCK marker (no CURL_EXIT/HTTP_CODE) is rejected as contamination."""
        raw = '{"available": true}\nSTDERR_BLOCK\n'
        payload = _extract_provider_health_payload(raw)

        # Incomplete envelope (no CURL_EXIT=0 and HTTP_CODE=200) is rejected
        assert payload.envelope_detected is False
        assert payload.raw_suffix == "STDERR_BLOCK"

    def test_rejects_json_with_bare_stderr_block_suffix(self) -> None:
        """JSON followed by bare STDERR_BLOCK marker (no CURL_EXIT/HTTP_CODE) is rejected as contamination."""
        raw = '{"available": true}\nSTDERR_BLOCK'
        payload = _extract_provider_health_payload(raw)

        # Incomplete envelope (no CURL_EXIT=0 and HTTP_CODE=200) is rejected
        assert payload.envelope_detected is False
        assert payload.raw_suffix == "STDERR_BLOCK"

    def test_parser_preserves_unknown_suffix_as_true_contamination(self) -> None:
        """Unknown text after valid JSON should not be treated as curl envelope metadata."""
        raw = '{"available": true}\nNOT_A_CURL_ENVELOPE'
        payload = _extract_provider_health_payload(raw)

        # Unknown suffix is not envelope - the entire text including unknown suffix
        # is returned as json_body, and raw_suffix captures the contamination
        assert payload.envelope_detected is False
        assert payload.json_body == raw
        assert payload.raw_suffix == "NOT_A_CURL_ENVELOPE"
