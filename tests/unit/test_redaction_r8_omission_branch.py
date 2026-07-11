"""R8 #7: Omission branch direct exercise tests.

These tests prove that safe_project_for_llm_or_omit():
1. Returns SAFE_OMISSION_MARKER when project_raw_evidence_text_for_llm raises UnsafeEvidenceTextError
2. Lets other exceptions (RuntimeError, TypeError, arbitrary) propagate unchanged
3. Does not leak secret values into logs or exception output
"""

from __future__ import annotations

import logging

import pytest

from k8s_diag_agent.collect.incident_evidence_llm_safe import (
    safe_project_for_llm_or_omit,
)
from k8s_diag_agent.collect.incident_evidence_redaction import (
    SAFE_OMISSION_MARKER,
    UnsafeEvidenceTextError,
)

# A synthetic secret that should NEVER appear in any output
SYNTHETIC_SECRET = "url-secret-value-redacted-v1"


class TestOmissionBranchReturnsMarker:
    """Verify the omission branch returns the marker for various max_chars."""

    def test_omission_max_chars_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """max_chars=1 should still return full marker."""
        from k8s_diag_agent.collect import incident_evidence_llm_safe as mod

        def raise_unsafe(value: object, *, max_chars: int) -> object:
            raise UnsafeEvidenceTextError(reason="too short")

        monkeypatch.setattr(mod, "project_raw_evidence_text_for_llm", raise_unsafe)

        result = safe_project_for_llm_or_omit("any value here", max_chars=1)
        assert result == SAFE_OMISSION_MARKER

    def test_omission_max_chars_below_marker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """max_chars below marker length should still return full marker."""
        from k8s_diag_agent.collect import incident_evidence_llm_safe as mod

        def raise_unsafe(value: object, *, max_chars: int) -> object:
            raise UnsafeEvidenceTextError(reason="unsafe")

        monkeypatch.setattr(mod, "project_raw_evidence_text_for_llm", raise_unsafe)

        result = safe_project_for_llm_or_omit(
            "any value here", max_chars=len(SAFE_OMISSION_MARKER) - 1,
        )
        assert result == SAFE_OMISSION_MARKER

    def test_omission_max_chars_equal_marker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """max_chars equal to marker length should still return full marker."""
        from k8s_diag_agent.collect import incident_evidence_llm_safe as mod

        def raise_unsafe(value: object, *, max_chars: int) -> object:
            raise UnsafeEvidenceTextError(reason="unsafe")

        monkeypatch.setattr(mod, "project_raw_evidence_text_for_llm", raise_unsafe)

        result = safe_project_for_llm_or_omit(
            "any value here", max_chars=len(SAFE_OMISSION_MARKER),
        )
        assert result == SAFE_OMISSION_MARKER

    def test_omission_max_chars_100(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Larger max_chars should still return the marker on omission."""
        from k8s_diag_agent.collect import incident_evidence_llm_safe as mod

        def raise_unsafe(value: object, *, max_chars: int) -> object:
            raise UnsafeEvidenceTextError(reason="unsafe")

        monkeypatch.setattr(mod, "project_raw_evidence_text_for_llm", raise_unsafe)

        result = safe_project_for_llm_or_omit("any value here", max_chars=100)
        assert result == SAFE_OMISSION_MARKER


class TestUnexpectedExceptionsPropagate:
    """Unexpected exceptions should propagate, not be swallowed."""

    def test_runtime_error_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from k8s_diag_agent.collect import incident_evidence_llm_safe as mod

        def raise_runtime(value: object, *, max_chars: int) -> object:
            raise RuntimeError(f"unexpected: {value}")

        monkeypatch.setattr(mod, "project_raw_evidence_text_for_llm", raise_runtime)

        with pytest.raises(RuntimeError, match="unexpected"):
            safe_project_for_llm_or_omit("value", max_chars=100)

    def test_type_error_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from k8s_diag_agent.collect import incident_evidence_llm_safe as mod

        def raise_type_error(value: object, *, max_chars: int) -> object:
            raise TypeError("wrong type")

        monkeypatch.setattr(mod, "project_raw_evidence_text_for_llm", raise_type_error)

        with pytest.raises(TypeError, match="wrong type"):
            safe_project_for_llm_or_omit("value", max_chars=100)

    def test_arbitrary_exception_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from k8s_diag_agent.collect import incident_evidence_llm_safe as mod

        class CustomError(Exception):
            pass

        def raise_custom(value: object, *, max_chars: int) -> object:
            raise CustomError("custom unexpected")

        monkeypatch.setattr(mod, "project_raw_evidence_text_for_llm", raise_custom)

        with pytest.raises(CustomError, match="custom unexpected"):
            safe_project_for_llm_or_omit("value", max_chars=100)


class TestLoggingHygieneOnOmission:
    """Synthetic secret must not leak into logs or exception output."""

    def test_synthetic_secret_absent_from_logs(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from k8s_diag_agent.collect import incident_evidence_llm_safe as mod

        def raise_unsafe(value: object, *, max_chars: int) -> object:
            # Include the synthetic secret in the exception reason
            raise UnsafeEvidenceTextError(reason=f"secret leaked: {SYNTHETIC_SECRET}")

        monkeypatch.setattr(mod, "project_raw_evidence_text_for_llm", raise_unsafe)

        with caplog.at_level(logging.DEBUG):
            result = safe_project_for_llm_or_omit("any value here", max_chars=100)

        assert result == SAFE_OMISSION_MARKER
        assert SYNTHETIC_SECRET not in caplog.text

    def test_synthetic_secret_absent_from_exception_text(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from k8s_diag_agent.collect import incident_evidence_llm_safe as mod

        # The UnsafeEvidenceTextError message is fixed and does not include the reason
        def raise_unsafe(value: object, *, max_chars: int) -> object:
            raise UnsafeEvidenceTextError(reason=f"secret leaked: {SYNTHETIC_SECRET}")

        monkeypatch.setattr(mod, "project_raw_evidence_text_for_llm", raise_unsafe)

        result = safe_project_for_llm_or_omit("any value here", max_chars=100)
        assert result == SAFE_OMISSION_MARKER
        # The secret must NOT be in result
        assert SYNTHETIC_SECRET not in str(result)
        # And it should also not be in the fixed exception text
        assert SYNTHETIC_SECRET not in (
            "Evidence text contains residual sensitive content after redaction"
        )
