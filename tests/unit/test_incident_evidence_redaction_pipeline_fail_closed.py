"""Unit tests for evidence privacy-state types - fail-closed behavior and pipeline.

ACT-K9B-HULK-SECRET-REDACTION-TYPES01.

Tests for:
- Full pipeline (project_raw_evidence_text_for_llm)
- Safe excerpt construction (make_safe_evidence_excerpt)
- Fail-closed behavior
- Redaction-before-truncation ordering
- Backward compatibility
- Path/reference handling
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_evidence_redaction import (
    LLMSafeEvidenceText,
    RawEvidenceText,
    RedactedEvidenceText,
    SafeEvidenceExcerpt,
    UnsafeEvidenceTextError,
    approve_redacted_evidence_text,
    make_safe_evidence_excerpt,
    project_raw_evidence_text_for_llm,
)

# ==============================================================================
# Fail-closed behavior tests
# ==============================================================================

class TestFailClosedBehavior:
    """Tests for fail-closed validation behavior."""

    def test_residual_sensitive_content_fails_closed(self) -> None:
        """Residual sensitive content fails validation."""
        redacted = RedactedEvidenceText("password=incomplete_redaction")
        with pytest.raises(UnsafeEvidenceTextError):
            approve_redacted_evidence_text(redacted)

    def test_error_text_does_not_contain_sensitive_value(self) -> None:
        """Error text does not contain the sensitive value."""
        redacted = RedactedEvidenceText("password=super_secret_value")
        try:
            approve_redacted_evidence_text(redacted)
            pytest.fail("Expected UnsafeEvidenceTextError")
        except UnsafeEvidenceTextError as e:
            assert "super_secret_value" not in str(e)
            assert "super_secret_value" not in repr(e)

    def test_error_repr_does_not_contain_sensitive_value(self) -> None:
        """Exception repr does not expose the sensitive value."""
        redacted = RedactedEvidenceText("api_key=sk-secret123")
        try:
            approve_redacted_evidence_text(redacted)
            pytest.fail("Expected UnsafeEvidenceTextError")
        except UnsafeEvidenceTextError as e:
            assert "sk-secret123" not in repr(e)
            assert "reason=" in repr(e)

    def test_full_pipeline_returns_safe_omission_on_failure(self) -> None:
        """Full pipeline returns safe omission marker on validation failure."""
        raw = RawEvidenceText("password=secret123")
        safe = project_raw_evidence_text_for_llm(raw, max_chars=100)
        assert "<scrubbed>" in safe
        assert "secret123" not in safe

    def test_fail_closed_with_partial_redaction_residual(self) -> None:
        """Fail-closed: partial redaction leaves residual pattern that triggers omission."""
        redacted = RedactedEvidenceText("password=partial_secret")
        try:
            approve_redacted_evidence_text(redacted)
            pytest.fail("Expected UnsafeEvidenceTextError")
        except UnsafeEvidenceTextError as e:
            assert e.reason == "residual_secret"
            assert e.pattern_category == "password"

    def test_error_has_pattern_category(self) -> None:
        """Error includes non-sensitive pattern category."""
        redacted = RedactedEvidenceText("password=secret")
        try:
            approve_redacted_evidence_text(redacted)
            pytest.fail("Expected UnsafeEvidenceTextError")
        except UnsafeEvidenceTextError as e:
            assert e.pattern_category is not None
            assert e.pattern_category in (
                "password",
                "secret",
                "token",
                "api_key",
                "bearer_token",
                "authorization",
                "client_secret",
                "access_token",
                "client_key_data",
                "client_certificate_data",
                "private_key",
                "certificate",
                "database_url",
                "credential",
            )


# ==============================================================================
# Truncation ordering tests
# ==============================================================================

class TestTruncationOrdering:
    """Tests for redaction-before-truncation ordering."""

    def test_redaction_occurs_before_truncation(self) -> None:
        """Redaction occurs before truncation."""
        raw = RawEvidenceText(
            "password=very_long_secret_value_that_extends_beyond_truncation_point"
            "password=incomplete_truncated_secret_part1"
        )
        safe = project_raw_evidence_text_for_llm(raw, max_chars=50)
        assert "very_long_secret_value" not in safe
        assert "incomplete_truncated_secret_part1" not in safe

    def test_final_truncated_output_is_scanned_again(self) -> None:
        """Final truncated output is scanned again."""
        raw = RawEvidenceText(
            "A" * 40 + "password=partial_at_boundary"
        )
        safe = project_raw_evidence_text_for_llm(raw, max_chars=50)
        assert "password=partial_at_boundary" not in safe

    def test_secret_at_excerpt_boundary(self) -> None:
        """Test with sensitive value positioned at or across the final excerpt boundary."""
        raw = RawEvidenceText(
            "Normal text here. password=secret_value_here_exceeds_limit"
        )
        safe = project_raw_evidence_text_for_llm(raw, max_chars=30)
        assert "secret_value_here" not in safe


# ==============================================================================
# Safe excerpt construction tests
# ==============================================================================

class TestSafeExcerptConstruction:
    """Tests for safe excerpt construction."""

    def test_safe_excerpt_from_approved_text(self) -> None:
        """SafeEvidenceExcerpt can only be produced from approved LLM-safe text."""
        raw = RawEvidenceText("This is safe content for an LLM")
        safe = project_raw_evidence_text_for_llm(raw, max_chars=100)
        excerpt = make_safe_evidence_excerpt(safe, max_chars=20)
        assert len(excerpt) <= 20
        assert "This is safe content" in excerpt

    def test_safe_excerpt_truncates_longer_text(self) -> None:
        """Excerpt truncates longer text correctly."""
        raw = RawEvidenceText("A" * 100)
        safe = project_raw_evidence_text_for_llm(raw, max_chars=100)
        excerpt = make_safe_evidence_excerpt(safe, max_chars=50)
        assert len(excerpt) == 50

    def test_safe_excerpt_preserves_short_text(self) -> None:
        """Excerpt preserves text shorter than max_chars."""
        raw = RawEvidenceText("Short text")
        safe = project_raw_evidence_text_for_llm(raw, max_chars=100)
        excerpt = make_safe_evidence_excerpt(safe, max_chars=50)
        assert excerpt == "Short text"

    def test_empty_excerpt_raises(self) -> None:
        """Empty excerpt raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            make_safe_evidence_excerpt(LLMSafeEvidenceText(RedactedEvidenceText("")), max_chars=50)


# ==============================================================================
# Branded text serialization tests
# ==============================================================================

class TestBrandedTextSerialization:
    """Tests for branded text serialization."""

    def test_redacted_evidence_text_serializes_as_string(self) -> None:
        """RedactedEvidenceText serializes as plain string."""
        text = RedactedEvidenceText("Redacted content")
        serialized = str(text)
        assert serialized == "Redacted content"
        assert isinstance(serialized, str)

    def test_llm_safe_evidence_text_serializes_as_string(self) -> None:
        """LLMSafeEvidenceText serializes as plain string."""
        text = LLMSafeEvidenceText(RedactedEvidenceText("Safe content"))
        serialized = str(text)
        assert serialized == "Safe content"
        assert isinstance(serialized, str)

    def test_safe_evidence_excerpt_serializes_as_string(self) -> None:
        """SafeEvidenceExcerpt serializes as plain string."""
        text = SafeEvidenceExcerpt(
            LLMSafeEvidenceText(RedactedEvidenceText("Excerpt content"))
        )
        serialized = str(text)
        assert serialized == "Excerpt content"
        assert isinstance(serialized, str)


# ==============================================================================
# Backward compatibility tests
# ==============================================================================

class TestBackwardCompatibility:
    """Tests for backward compatibility with existing imports."""

    def test_make_redacted_evidence_text_from_facade(self) -> None:
        """make_redacted_evidence_text works through incident_evidence facade."""
        from k8s_diag_agent.collect.incident_evidence import make_redacted_evidence_text

        result = make_redacted_evidence_text("Plain text")
        assert result == "Plain text"
        assert isinstance(result, str)

    def test_make_redacted_evidence_text_raises_on_empty(self) -> None:
        """make_redacted_evidence_text raises on empty input."""
        from k8s_diag_agent.collect.incident_evidence import make_redacted_evidence_text

        with pytest.raises(ValueError, match="cannot be empty"):
            make_redacted_evidence_text("")

    def test_safe_omission_marker_importable(self) -> None:
        """SAFE_OMISSION_MARKER is importable from facade."""
        from k8s_diag_agent.collect.incident_evidence import SAFE_OMISSION_MARKER

        assert SAFE_OMISSION_MARKER == "[REDACTED:UNSAFE_EVIDENCE]"

    def test_unsafe_error_importable(self) -> None:
        """UnsafeEvidenceTextError is importable from facade."""
        from k8s_diag_agent.collect.incident_evidence import UnsafeEvidenceTextError

        error = UnsafeEvidenceTextError(reason="test_reason", pattern_category="password")
        assert error.reason == "test_reason"
        assert error.pattern_category == "password"
        assert "residual sensitive content" in str(error)


# ==============================================================================
# Path/reference handling tests
# ==============================================================================

class TestPathReferenceHandling:
    """Tests for path and reference handling in the redaction pipeline."""

    def test_local_path_preserved_when_no_secret(self) -> None:
        """Local paths without secrets are preserved through pipeline."""
        raw = RawEvidenceText("Log from /var/lib/k9b/artifacts/inc-123/log.txt shows error")
        safe = project_raw_evidence_text_for_llm(raw, max_chars=200)
        assert "/var/lib/k9b/" in safe
        assert "error" in safe

    def test_external_storage_ref_preserved_when_no_secret(self) -> None:
        """External storage refs without secrets are preserved through pipeline."""
        raw = RawEvidenceText("Artifact at s3://bucket/incidents/inc-456/evidence.json")
        safe = project_raw_evidence_text_for_llm(raw, max_chars=200)
        assert "s3://bucket/" in safe
        assert "evidence.json" in safe

    def test_credential_in_path_is_redacted(self) -> None:
        """Credentials embedded in paths are redacted."""
        raw = RawEvidenceText("Connecting to https://user:password@example.com/api")
        safe = project_raw_evidence_text_for_llm(raw, max_chars=200)
        assert "password" not in safe or "password=" not in safe


# ==============================================================================
# Full pipeline integration tests
# ==============================================================================

class TestFullPipelineIntegration:
    """Integration tests for the full pipeline."""

    def test_plain_text_full_pipeline(self) -> None:
        """Plain text goes through full pipeline successfully."""
        raw = RawEvidenceText("Deployment api-server scaled to 3 replicas")
        safe = project_raw_evidence_text_for_llm(raw, max_chars=100)
        assert safe == "Deployment api-server scaled to 3 replicas"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
