"""Tests for P0b provider health extra data fix (not output contamination).

These tests verify that:
- JSON with trailing arbitrary bytes is classified as provider_health_invalid_json
- JSON with trailing curl/framing metadata is classified as provider_health_output_contaminated
- Concatenated JSON is classified as provider_health_invalid_json

This addresses the over-classification bug where arbitrary trailing bytes
were mislabeled as curl output contamination.
"""

from __future__ import annotations

import json

import pytest


class TestCurlFramingSuffixDetection:
    """Tests for _looks_like_curl_framing_suffix helper."""

    def test_curl_exit_pattern_detected(self) -> None:
        """CURL_EXIT=0 should be detected as curl framing."""
        from scripts.lab_common.provider_preflight import _looks_like_curl_framing_suffix

        assert _looks_like_curl_framing_suffix("CURL_EXIT=0") is True
        assert _looks_like_curl_framing_suffix("CURL_EXIT=7") is True
        assert _looks_like_curl_framing_suffix("CURL_EXIT=28") is True

    def test_http_code_pattern_detected(self) -> None:
        """HTTP_CODE=200 should be detected as curl framing."""
        from scripts.lab_common.provider_preflight import _looks_like_curl_framing_suffix

        assert _looks_like_curl_framing_suffix("HTTP_CODE=200") is True
        assert _looks_like_curl_framing_suffix("HTTP_CODE=000") is True

    def test_curl_marker_pattern_detected(self) -> None:
        """---CURL_START--- should be detected as curl framing."""
        from scripts.lab_common.provider_preflight import _looks_like_curl_framing_suffix

        assert _looks_like_curl_framing_suffix("---CURL_START---") is True
        assert _looks_like_curl_framing_suffix("---CURL_END---") is True

    def test_stderr_block_pattern_detected(self) -> None:
        """STDERR_BLOCK should be detected as curl framing."""
        from scripts.lab_common.provider_preflight import _looks_like_curl_framing_suffix

        assert _looks_like_curl_framing_suffix("STDERR_BLOCK") is True

    def test_whitespace_before_curl_metadata(self) -> None:
        """Whitespace before curl metadata should be stripped."""
        from scripts.lab_common.provider_preflight import _looks_like_curl_framing_suffix

        assert _looks_like_curl_framing_suffix("\nCURL_EXIT=0") is True
        assert _looks_like_curl_framing_suffix("  \nHTTP_CODE=200") is True

    def test_arbitrary_text_not_detected(self) -> None:
        """Arbitrary text should NOT be detected as curl framing."""
        from scripts.lab_common.provider_preflight import _looks_like_curl_framing_suffix

        assert _looks_like_curl_framing_suffix("trailing text here") is False
        assert _looks_like_curl_framing_suffix("some random content") is False
        assert _looks_like_curl_framing_suffix("garbage data") is False

    def test_concatenated_json_not_detected(self) -> None:
        """Concatenated JSON should NOT be detected as curl framing."""
        from scripts.lab_common.provider_preflight import _looks_like_curl_framing_suffix

        assert _looks_like_curl_framing_suffix('{"extra": true}') is False
        assert _looks_like_curl_framing_suffix('{"a":1}{"b":2}') is False


class TestJsonParseFailureClassification:
    """Tests for _classify_json_parse_failure with extra data handling."""

    def test_concatenated_json_without_markers_fails_invalid_json(self) -> None:
        """Concatenated JSON without curl markers should be classified as invalid_json."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_INVALID_JSON,
            _classify_json_parse_failure,
        )

        # This is the exact case from the bug report
        body = '{"healthy": true}{"extra": true}'
        try:
            json.loads(body)
            pytest.fail("Should have raised JSONDecodeError")
        except json.JSONDecodeError as exc:
            failure_class, message, _ = _classify_json_parse_failure(body, exc)

        assert failure_class == FAILURE_PROVIDER_HEALTH_INVALID_JSON
        assert "contamination" not in message.lower()

    def test_json_with_unknown_trailing_text_fails_contaminated(self) -> None:
        """JSON with unknown trailing text should be classified as output_contaminated."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            _classify_json_parse_failure,
        )

        body = '{"healthy":true}trailing text here'
        try:
            json.loads(body)
            pytest.fail("Should have raised JSONDecodeError")
        except json.JSONDecodeError as exc:
            failure_class, message, _ = _classify_json_parse_failure(body, exc)

        assert failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED
        assert "contamination" in message.lower()

    def test_json_with_curl_metadata_fails_contaminated(self) -> None:
        """JSON with curl metadata should be classified as output_contaminated."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            _classify_json_parse_failure,
        )

        body = '{"healthy":true}\nCURL_EXIT=0\nHTTP_CODE=200'
        try:
            json.loads(body)
            pytest.fail("Should have raised JSONDecodeError")
        except json.JSONDecodeError as exc:
            failure_class, message, _ = _classify_json_parse_failure(body, exc)

        assert failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED
        assert "contamination" in message.lower()

    def test_json_with_only_curl_exit_fails_contaminated(self) -> None:
        """JSON with CURL_EXIT= only should be classified as output_contaminated."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            _classify_json_parse_failure,
        )

        body = '{"healthy": true}\nCURL_EXIT=0'
        try:
            json.loads(body)
            pytest.fail("Should have raised JSONDecodeError")
        except json.JSONDecodeError as exc:
            failure_class, message, _ = _classify_json_parse_failure(body, exc)

        assert failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED

    def test_duplicate_json_objects_fails_invalid_json(self) -> None:
        """Duplicate JSON objects without markers should be classified as invalid_json."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_INVALID_JSON,
            _classify_json_parse_failure,
        )

        body = '[{"a":1}][{"b":2}]'
        try:
            json.loads(body)
            pytest.fail("Should have raised JSONDecodeError")
        except json.JSONDecodeError as exc:
            failure_class, message, _ = _classify_json_parse_failure(body, exc)

        assert failure_class == FAILURE_PROVIDER_HEALTH_INVALID_JSON

    def test_json_with_stderr_block_fails_contaminated(self) -> None:
        """JSON with STDERR_BLOCK marker should be classified as output_contaminated."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            _classify_json_parse_failure,
        )

        body = '{"healthy":true}\nSTDERR_BLOCK\nsome stderr'
        try:
            json.loads(body)
            pytest.fail("Should have raised JSONDecodeError")
        except json.JSONDecodeError as exc:
            failure_class, message, _ = _classify_json_parse_failure(body, exc)

        assert failure_class == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED


class TestExtractCleanOrContaminatedJson:
    """Tests for _extract_clean_or_contaminated_json helper."""

    def test_clean_json_returns_parsed(self) -> None:
        """Clean valid JSON should return parsed dict."""
        from scripts.lab_common.provider_preflight import (
            _extract_clean_or_contaminated_json,
        )

        parsed, failure = _extract_clean_or_contaminated_json('{"ok": true}')
        assert parsed == {"ok": True}
        assert failure is None

    def test_suffix_contamination_returns_contaminated(self) -> None:
        """JSON with trailing log text should return contaminated."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            _extract_clean_or_contaminated_json,
        )

        _, failure = _extract_clean_or_contaminated_json('{"ok": true}\nINFO trailing log')
        assert failure == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED

    def test_prefix_contamination_returns_contaminated(self) -> None:
        """JSON with leading log text should return contaminated."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            _extract_clean_or_contaminated_json,
        )

        _, failure = _extract_clean_or_contaminated_json('INFO starting\n{"ok": true}')
        assert failure == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED

    def test_prefix_and_suffix_contamination_returns_contaminated(self) -> None:
        """JSON with both log prefix and suffix should return contaminated."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED,
            _extract_clean_or_contaminated_json,
        )

        _, failure = _extract_clean_or_contaminated_json('INFO starting\n{"ok": true}\nINFO done')
        assert failure == FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED

    def test_truly_invalid_json_returns_invalid_json(self) -> None:
        """Truly malformed JSON should return invalid_json."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_INVALID_JSON,
            _extract_clean_or_contaminated_json,
        )

        _, failure = _extract_clean_or_contaminated_json('INFO only, no json')
        assert failure == FAILURE_PROVIDER_HEALTH_INVALID_JSON

        _, failure = _extract_clean_or_contaminated_json('{"ok": ')
        assert failure == FAILURE_PROVIDER_HEALTH_INVALID_JSON

    def test_concatenated_json_returns_invalid_json(self) -> None:
        """Concatenated JSON should return invalid_json."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_INVALID_JSON,
            _extract_clean_or_contaminated_json,
        )

        _, failure = _extract_clean_or_contaminated_json('{"ok": true}{"extra": true}')
        assert failure == FAILURE_PROVIDER_HEALTH_INVALID_JSON

    def test_empty_body_returns_invalid_json(self) -> None:
        """Empty body should return invalid_json."""
        from scripts.lab_common.provider_preflight import (
            FAILURE_PROVIDER_HEALTH_INVALID_JSON,
            _extract_clean_or_contaminated_json,
        )

        _, failure = _extract_clean_or_contaminated_json('')
        assert failure == FAILURE_PROVIDER_HEALTH_INVALID_JSON

        _, failure = _extract_clean_or_contaminated_json('   \n\t  ')
        assert failure == FAILURE_PROVIDER_HEALTH_INVALID_JSON


class TestFacadeExports:
    """Tests that facade exports all expected public interfaces."""

    def test_facade_exports_run_provider_preflight(self) -> None:
        """Facade should export run_provider_preflight."""
        from scripts.lab_common import provider_preflight

        assert hasattr(provider_preflight, "run_provider_preflight")
        assert callable(provider_preflight.run_provider_preflight)

    def test_facade_exports_provider_preflight_result(self) -> None:
        """Facade should export ProviderPreflightResult."""
        from scripts.lab_common import provider_preflight

        assert hasattr(provider_preflight, "ProviderPreflightResult")

    def test_facade_exports_failure_constants(self) -> None:
        """Facade should export all failure constants."""
        from scripts.lab_common import provider_preflight

        assert hasattr(provider_preflight, "FAILURE_PROVIDER_HEALTH_OUTPUT_CONTAMINATED")
        assert hasattr(provider_preflight, "FAILURE_PROVIDER_HEALTH_INVALID_JSON")
        assert hasattr(provider_preflight, "FAILURE_PROVIDER_HEALTH_EMPTY_BODY")

    def test_facade_exports_classify_function_for_tests(self) -> None:
        """Facade should export _classify_json_parse_failure for test use."""
        from scripts.lab_common import provider_preflight

        assert hasattr(provider_preflight, "_classify_json_parse_failure")
        assert callable(provider_preflight._classify_json_parse_failure)

    def test_facade_exports_curl_framing_helper(self) -> None:
        """Facade should export _looks_like_curl_framing_suffix for test use."""
        from scripts.lab_common import provider_preflight

        assert hasattr(provider_preflight, "_looks_like_curl_framing_suffix")
        assert callable(provider_preflight._looks_like_curl_framing_suffix)

    def test_facade_exports_extract_clean_or_contaminated_json(self) -> None:
        """Facade should export _extract_clean_or_contaminated_json for test use."""
        from scripts.lab_common import provider_preflight

        assert hasattr(provider_preflight, "_extract_clean_or_contaminated_json")
        assert callable(provider_preflight._extract_clean_or_contaminated_json)
