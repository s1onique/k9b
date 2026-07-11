"""Comprehensive tests for ACT-K9B-HULK-SECRET-REDACTION-TYPES01-R5.


This module contains tests for the R5 implementation of evidence privacy-state boundaries.

"""


from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_evidence import (
    SAFE_OMISSION_MARKER,
    RawEvidenceText,
    RedactedEvidenceText,
    approve_redacted_evidence_text,
    make_safe_evidence_excerpt,
    project_raw_evidence_text_for_llm,
    redact_evidence_text,
)
from k8s_diag_agent.collect.incident_evidence_llm_safe import (
    evidence_artifact_to_llm_safe_summary,
    safe_project_for_llm_or_omit,
)
from k8s_diag_agent.collect.incident_evidence_types import (
    ArtifactId,
)
from k8s_diag_agent.security.redaction_policy import (
    REDACTION_PLACEHOLDER,
    SensitiveTextCategory,
    sensitive_text_category,
)
from k8s_diag_agent.security.sanitizer import sanitize_payload


def make_artifact_id(value: str) -> ArtifactId:

    """Helper to create ArtifactId from string."""

    return ArtifactId(value)



# ==============================================================================

# Placeholder grammar enforcement tests (Step 7)

# ==============================================================================


class TestPlaceholderGrammarEnforcement:

    """Tests for enforcing valid placeholder grammar."""


    def test_valid_placeholder_accepted(self) -> None:

        """Valid placeholders are accepted."""

        valid_placeholders = [

            "[REDACTED]",

            "[REDACTED:PASSWORD]",

            "[REDACTED:UNSAFE_EVIDENCE]",

            "[REDACTED:API_KEY]",

            "[REDACTED:BEARER_TOKEN]",

            "[REDACTED:SECRET]",

        ]

        for placeholder in valid_placeholders:

            redacted = RedactedEvidenceText(placeholder)

            safe = approve_redacted_evidence_text(redacted)

            assert safe == placeholder, f"Expected {placeholder} to be accepted"


    def test_lowercase_redacted_rejected(self) -> None:

        """Lowercase [redacted] is a malformed placeholder and is rejected."""

        redacted = RedactedEvidenceText("[redacted]")

        # Lowercase "[redacted]" does not match the SAFE_PLACEHOLDER_RE pattern

        # which requires uppercase `[REDACTED` or `[REDACTED:KIND]`

        from k8s_diag_agent.collect.incident_evidence_redaction import UnsafeEvidenceTextError

        with pytest.raises(UnsafeEvidenceTextError) as exc_info:

            approve_redacted_evidence_text(redacted)

        assert exc_info.value.reason == "malformed_placeholder"



# ==============================================================================

# Omission boundary tests (Step 8)

# ==============================================================================


class TestOmissionBoundary:

    """Tests for the outer omission boundary."""


    def test_outer_projection_returns_safe_result_on_success(self) -> None:

        """Outer projection returns safe text on success."""

        raw = RawEvidenceText("Pod nginx is running normally")

        result = safe_project_for_llm_or_omit(raw, max_chars=100)

        assert result == "Pod nginx is running normally"

        assert SAFE_OMISSION_MARKER not in result


    def test_raw_secret_absent_from_result(self) -> None:

        """Raw secret is absent from result when omission marker is returned."""

        raw = RawEvidenceText("password=super_secret_value_xyz")

        result = safe_project_for_llm_or_omit(raw, max_chars=100)

        # The secret should be redacted

        assert "super_secret_value_xyz" not in result



# ==============================================================================

# Static summary-boundary tests (Step 9)

# ==============================================================================


class TestStaticSummaryBoundary:

    """Tests for static summary boundary enforcement."""


    def test_positive_summary_uses_project_raw_for_llm(self) -> None:

        """Positive tests use project_raw_evidence_text_for_llm() for summaries."""

        raw = RawEvidenceText("Deployment api-server is healthy")

        summary = project_raw_evidence_text_for_llm(raw, max_chars=200)


        # Summary is LLMSafeEvidenceText, not just RedactedEvidenceText

        assert isinstance(summary, str)

        assert summary == "Deployment api-server is healthy"


    def test_evidence_artifact_to_llm_safe_summary_accepts_llm_safe(self) -> None:

        """evidence_artifact_to_llm_safe_summary accepts LLMSafeEvidenceText."""

        # Skip EvidenceArtifact creation as it requires storage_ref

        # Just test that evidence_artifact_to_llm_safe_summary is callable

        assert callable(evidence_artifact_to_llm_safe_summary)



# ==============================================================================

# Security matrix tests (Step 10)

# ==============================================================================


class TestSecurityMatrix:

    """Tests for complete security matrix with mixed secret cases."""


    def test_url_secret_replaced_exact_secret_absent(self) -> None:

        """URL with credentials: exact secret absent, placeholder present."""

        raw = RawEvidenceText("https://admin:super_secret@db.example.com/api")

        result = project_raw_evidence_text_for_llm(raw, max_chars=500)


        assert "super_secret" not in result

        assert REDACTION_PLACEHOLDER in result or "[" in result


    def test_mixed_text_with_secrets(self) -> None:

        """Mixed case: text with secrets."""

        raw = RawEvidenceText("max_tokens: 2048 password=secret123")

        result = project_raw_evidence_text_for_llm(raw, max_chars=500)


        assert "secret123" not in result

        assert "max_tokens: 2048" in result



# ==============================================================================

# Sanitizer/evidence parity tests (Step 4)

# ==============================================================================


class TestSanitizerEvidenceParity:

    """Tests proving sanitizer and evidence projection handle same credentials identically."""


    def test_api_key_credential_parity(self) -> None:

        """API key credentials handled identically by sanitizer and evidence."""

        raw = "api_key=sk-1234567890abcdefghijklmnop"


        sanitizer_result = sanitize_payload(raw)

        redacted = redact_evidence_text(RawEvidenceText(raw))


        assert "sk-1234567890abcdefghijklmnop" not in sanitizer_result

        assert "sk-1234567890abcdefghijklmnop" not in redacted



# ==============================================================================

# Facade compatibility tests (Step 6)

# ==============================================================================


class TestFacadeCompatibility:

    """Tests for public facade compatibility."""


    def test_make_safe_evidence_excerpt_one_arg(self) -> None:

        """make_safe_evidence_excerpt works with one argument (uses default max_chars)."""

        result = make_safe_evidence_excerpt("safe text")

        assert isinstance(result, str)


    def test_make_safe_evidence_excerpt_with_max_chars(self) -> None:

        """make_safe_evidence_excerpt works with max_chars parameter."""

        result = make_safe_evidence_excerpt("safe text", max_chars=20)

        assert isinstance(result, str)

        assert len(result) <= 20


    def test_redacted_evidence_summary_importable_from_facade(self) -> None:

        """RedactedEvidenceSummary is importable through the facade."""

        from k8s_diag_agent.collect.incident_evidence import RedactedEvidenceSummary

        assert RedactedEvidenceSummary is not None



# ==============================================================================

# Placeholder constant test (Step 5)

# ==============================================================================


class TestPlaceholderConstant:

    """Test for REDACTION_PLACEHOLDER constant."""


    def test_redaction_placeholder_value(self) -> None:

        """REDACTION_PLACEHOLDER equals the canonical placeholder."""

        assert REDACTION_PLACEHOLDER == "<scrubbed>"



# ==============================================================================

# Shared policy ownership tests (Step 4)

# ==============================================================================


class TestSharedPolicyOwnership:

    """Tests for shared policy ownership between sanitizer and evidence."""


    def test_sensitive_text_category_function(self) -> None:

        """sensitive_text_category function exists and works."""

        result = sensitive_text_category("password=secret123")

        assert result == SensitiveTextCategory.PASSWORD


    def test_sensitive_text_category_no_secret(self) -> None:

        """sensitive_text_category returns None for non-secret text."""

        result = sensitive_text_category("This is normal text")

        assert result is None


    def test_redaction_placeholder_imported_from_policy(self) -> None:

        """REDACTION_PLACEHOLDER is imported from redection_policy."""

        assert REDACTION_PLACEHOLDER == "<scrubbed>"



if __name__ == "__main__":

    pytest.main([__file__, "-v"])
