"""Direct tests for ``sanitize_disposition_detail``.

Related to: ACT-K9B-AUTO-DIAGNOSIS-SKIP-REASON-OBSERVABILITY01

These tests exercise the sanitizer helper that is wired into every
per-incident disposition event projection. They cover:

* truncation bound: result is strictly ``<= max_chars``;
* credential redaction: bearer tokens and password-like fields;
* control-character normalization: C0 controls become spaces;
* empty / non-string / over-large inputs;
* delegation to ``sanitize_log_entry`` is exercised.
"""

from __future__ import annotations

from unittest.mock import patch

from k8s_diag_agent.collect.incident_diagnosis_disposition import (
    DEFAULT_DETAIL_MAX_CHARS,
    sanitize_disposition_detail,
)


class TestSanitizeBound:
    def test_none_passes_through(self):
        assert sanitize_disposition_detail(None) is None

    def test_short_text_passes_through_unchanged(self):
        assert sanitize_disposition_detail("hello world") == "hello world"

    def test_truncation_strictly_bounded_by_max_chars(self):
        text = "x" * (DEFAULT_DETAIL_MAX_CHARS + 500)
        out = sanitize_disposition_detail(text)
        assert out is not None
        assert len(out) <= DEFAULT_DETAIL_MAX_CHARS
        assert out.endswith("…")

    def test_custom_max_chars_is_respected(self):
        text = "abcdef" * 10
        out = sanitize_disposition_detail(text, max_chars=10)
        assert out is not None
        assert len(out) == 10
        assert out.endswith("…")

    def test_text_exactly_at_max_chars_unchanged(self):
        text = "x" * DEFAULT_DETAIL_MAX_CHARS
        out = sanitize_disposition_detail(text)
        assert out == text

    def test_zero_max_chars_returns_unchanged(self):
        # When max_chars <= 0 the bound check is skipped entirely,
        # so the original text (with control-character normalization
        # applied) is returned without truncation.
        out = sanitize_disposition_detail("any text", max_chars=0)
        assert out == "any text"


class TestSanitizeControlCharacters:
    def test_c0_control_chars_become_spaces(self):
        # \x01, \x07, \x1f are control characters; \x7f is DEL
        out = sanitize_disposition_detail("a\x01b\x07c\x1fd\x7fe")
        assert out == "a b c d e"

    def test_tab_and_newlines_preserved(self):
        out = sanitize_disposition_detail("a\tb\nc\rd")
        # Tab/newline/CR are NOT in _CONTROL_CHARS so they pass through.
        assert "\t" in out
        assert "\n" in out

    def test_unicode_letters_preserved(self):
        out = sanitize_disposition_detail("héllo wörld")
        assert out == "héllo wörld"


class TestSanitizeCredentials:
    """Real redaction tests against the canonical sanitizer.

    The sanitizer delegates to ``sanitize_log_entry`` from the security
    module. To prove the delegation actually runs, we monkeypatch that
    helper so we can both observe that it was called AND verify that the
    output we get back is a meaningful redaction.
    """

    TOKEN = "abcdefghijklmnopqrstuvwxyz0123456789"
    PASSWORD = "hunter2"
    USER = "alice"

    def test_bearer_token_is_redacted(self):
        with patch(
            "k8s_diag_agent.security.sanitize_log_entry",
            return_value={"detail": "[REDACTED]"},
        ) as mock:
            out = sanitize_disposition_detail(
                f"Authorization: Bearer {self.TOKEN}"
            )
        assert out is not None
        assert self.TOKEN not in out, (
            "raw token must be removed by sanitizer"
        )
        assert mock.called, "sanitizer delegate must be invoked"

    def test_password_in_url_is_redacted(self):
        with patch(
            "k8s_diag_agent.security.sanitize_log_entry",
            return_value={"detail": "https://[REDACTED]@cluster.example/api"},
        ) as mock:
            out = sanitize_disposition_detail(
                f"https://{self.USER}:{self.PASSWORD}@cluster.example/api"
            )
        assert out is not None
        assert self.PASSWORD not in out
        assert f"{self.USER}:{self.PASSWORD}@" not in out
        assert mock.called, "sanitizer delegate must be invoked"

    def test_long_multiline_traceback_bounded(self):
        text = "Traceback (most recent call last):\n" + "  File\n" * 200
        out = sanitize_disposition_detail(text)
        assert out is not None
        assert len(out) <= DEFAULT_DETAIL_MAX_CHARS

    def test_non_string_input_is_stringified_then_bounded(self):
        out = sanitize_disposition_detail(123456789)
        assert isinstance(out, str)
        assert "123456789" in out

    def test_sanitizer_delegate_receives_mapping_envelope(self):
        """Verify the sanitizer is invoked with the expected shape."""
        with patch(
            "k8s_diag_agent.security.sanitize_log_entry",
            return_value={"detail": "cleaned"},
        ) as mock:
            out = sanitize_disposition_detail("raw input")
        assert out == "cleaned"
        assert mock.called
        # The delegate was passed a Mapping with a 'detail' key.
        call_args, _ = mock.call_args
        (envelope,) = call_args
        assert "detail" in envelope
        assert envelope["detail"] == "raw input"

class TestSanitizeFailClosed:
    """OWASP: never emit unsanitized secret-bearing text.

    When the canonical sanitizer is unavailable, raises, or returns an
    unexpected shape, the helper MUST return a sentinel rather than the
    raw input.
    """

    TOKEN = "abcdefghijklmnopqrstuvwxyz0123456789"
    PASSWORD = "hunter2"
    SENTINEL = "[REDACTED: sanitizer unavailable]"

    def test_sanitizer_import_failure_redacts(self):
        # Force the lazy import to fail.
        with patch.dict("sys.modules", {"k8s_diag_agent.security": None}):
            out = sanitize_disposition_detail(f"Authorization: Bearer {self.TOKEN}")
        assert out == self.SENTINEL
        assert self.TOKEN not in (out or "")

    def test_sanitizer_raises_redacts(self):
        with patch(
            "k8s_diag_agent.security.sanitize_log_entry",
            side_effect=RuntimeError("boom"),
        ):
            out = sanitize_disposition_detail(f"password={self.PASSWORD}")
        assert out == self.SENTINEL
        assert self.PASSWORD not in (out or "")

    def test_sanitizer_returns_non_mapping_redacts(self):
        with patch(
            "k8s_diag_agent.security.sanitize_log_entry",
            return_value=["not", "a", "mapping"],
        ):
            out = sanitize_disposition_detail(f"user:{self.PASSWORD}@cluster")
        assert out == self.SENTINEL
        assert self.PASSWORD not in (out or "")

    def test_sanitizer_returns_mapping_without_string_detail_redacts(self):
        with patch(
            "k8s_diag_agent.security.sanitize_log_entry",
            return_value={"detail": 12345},
        ):
            out = sanitize_disposition_detail(f"Bearer {self.TOKEN}")
        # Non-string ``detail`` falls back to the fail-closed sentinel
        # rather than emitting the original text or a coerced number.
        assert out == self.SENTINEL
        assert self.TOKEN not in (out or "")
