"""Unit tests for evidence privacy-state types and redaction - core behavior.

ACT-K9B-HULK-SECRET-REDACTION-TYPES01.

Tests for:
- Privacy-state type hierarchy
- Raw-to-redacted projection (redact_evidence_text)
- Redacted-to-approved projection (approve_redacted_evidence_text)
- Safe placeholder acceptance
- Non-secret text preservation
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
    redact_evidence_text,
)

# ==============================================================================
# Privacy-state type tests
# ==============================================================================

class TestPrivacyStateTypes:
    """Tests for privacy-state type hierarchy."""

    def test_raw_evidence_text_is_newtype(self) -> None:
        """RawEvidenceText is a NewType based on str."""
        text = RawEvidenceText("raw content")
        assert text == "raw content"
        assert isinstance(text, str)

    def test_redacted_evidence_text_is_newtype(self) -> None:
        """RedactedEvidenceText is a NewType based on str."""
        text = RedactedEvidenceText("redacted content")
        assert text == "redacted content"
        assert isinstance(text, str)

    def test_llm_safe_evidence_text_is_newtype(self) -> None:
        """LLMSafeEvidenceText is a NewType based on RedactedEvidenceText."""
        text = LLMSafeEvidenceText(RedactedEvidenceText("safe content"))
        assert text == "safe content"
        assert isinstance(text, str)

    def test_safe_evidence_excerpt_is_newtype(self) -> None:
        """SafeEvidenceExcerpt is a NewType based on LLMSafeEvidenceText."""
        text = SafeEvidenceExcerpt(
            LLMSafeEvidenceText(RedactedEvidenceText("excerpt content"))
        )
        assert text == "excerpt content"
        assert isinstance(text, str)


# ==============================================================================
# Plain text tests (no secrets)
# ==============================================================================

class TestPlainTextPassthrough:
    """Tests for plain text that should pass through unchanged."""

    def test_plain_text_passes_unchanged(self) -> None:
        """Plain non-sensitive text passes unchanged through the pipeline."""
        raw = RawEvidenceText("Pod nginx-abc123 is in CrashLoopBackOff state")
        redacted = redact_evidence_text(raw)
        assert redacted == "Pod nginx-abc123 is in CrashLoopBackOff state"

    def test_plain_text_is_approved(self) -> None:
        """Plain text is approved for LLM use."""
        redacted = RedactedEvidenceText("Container nginx-xyz789 is running normally")
        safe = approve_redacted_evidence_text(redacted)
        assert safe == "Container nginx-xyz789 is running normally"


# ==============================================================================
# Secret pattern redaction tests
# ==============================================================================

class TestSecretRedaction:
    """Tests for secret pattern detection and redaction."""

    def test_password_assignment_is_redacted(self) -> None:
        """Password assignment is redacted."""
        synthetic_secret = "supersecret123"
        raw = RawEvidenceText(f"The password={synthetic_secret} was used for login")
        redacted = redact_evidence_text(raw)
        assert synthetic_secret not in redacted
        assert "<scrubbed>" in redacted

    def test_quoted_password_json_is_redacted(self) -> None:
        """JSON-style quoted password is redacted."""
        synthetic_secret = "quoted_secret_456"
        raw = RawEvidenceText(f'"password": "{synthetic_secret}"')
        redacted = redact_evidence_text(raw)
        assert synthetic_secret not in redacted
        assert "<scrubbed>" in redacted

    def test_quoted_password_single_is_redacted(self) -> None:
        """Single-quoted password is redacted."""
        synthetic_secret = "single_quoted_pass"
        raw = RawEvidenceText(f"'password': '{synthetic_secret}'")
        redacted = redact_evidence_text(raw)
        assert synthetic_secret not in redacted
        assert "<scrubbed>" in redacted

    def test_url_userinfo_password_is_redacted(self) -> None:
        """URL userinfo password is redacted."""
        synthetic_secret = "url_secret_pass"
        raw = RawEvidenceText(f"https://admin:{synthetic_secret}@example.com/api")
        redacted = redact_evidence_text(raw)
        assert synthetic_secret not in redacted
        assert "<scrubbed>" in redacted

    def test_basic_auth_is_redacted(self) -> None:
        """Basic Authorization header is redacted."""
        synthetic_secret = "Basic dXNlcjpwYXNz"
        raw = RawEvidenceText(f"Authorization: {synthetic_secret}")
        redacted = redact_evidence_text(raw)
        assert "dXNlcjpwYXNz" not in redacted
        assert "<scrubbed>" in redacted

    def test_database_url_is_redacted(self) -> None:
        """Database URL with credentials is redacted."""
        synthetic_secret = "db_super_secret"
        raw = RawEvidenceText(f"postgres://admin:{synthetic_secret}@db.example.com:5432/mydb")
        redacted = redact_evidence_text(raw)
        assert synthetic_secret not in redacted
        assert "<scrubbed>" in redacted

    def test_bearer_credential_is_redacted(self) -> None:
        """Bearer credential is redacted."""
        raw = RawEvidenceText("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doz Sig")
        redacted = redact_evidence_text(raw)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted

    def test_jwt_shaped_credential_is_redacted(self) -> None:
        """JWT-shaped credential is redacted."""
        raw = RawEvidenceText("token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2kuaW8ifQ.sig")
        redacted = redact_evidence_text(raw)
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted

    def test_api_key_assignment_is_redacted(self) -> None:
        """API key assignment is redacted."""
        raw = RawEvidenceText("api_key=sk-1234567890abcdefghijklmnop")
        redacted = redact_evidence_text(raw)
        assert "sk-1234567890abcdefghijklmnop" not in redacted

    def test_private_key_pem_is_redacted(self) -> None:
        """Private key PEM content is redacted."""
        raw = RawEvidenceText(
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIBOgIBAAJBALRiMLAHudeSA2AI3nGLQ4c/mCqH2sS2rW1T2j7QKzR9Q6nF\n"
            "-----END RSA PRIVATE KEY-----"
        )
        redacted = redact_evidence_text(raw)
        assert "-----BEGIN RSA PRIVATE KEY-----" not in redacted

    def test_kubernetes_client_key_data_is_redacted(self) -> None:
        """Kubernetes client-key-data is redacted."""
        raw = RawEvidenceText("client-key-data: LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCg==")
        redacted = redact_evidence_text(raw)
        assert "LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCg==" not in redacted

    def test_kubernetes_client_certificate_data_is_redacted(self) -> None:
        """Kubernetes client-certificate-data is redacted."""
        raw = RawEvidenceText("client-certificate-data: LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCg==")
        redacted = redact_evidence_text(raw)
        assert "LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCg==" not in redacted

    def test_credential_bearing_database_url_is_redacted(self) -> None:
        """Database URL with credentials is redacted."""
        raw = RawEvidenceText("postgres://admin:super_secret_pass@db.example.com:5432/mydb")
        redacted = redact_evidence_text(raw)
        assert "super_secret_pass" not in redacted

    def test_multiline_evidence_is_handled(self) -> None:
        """Multiline evidence with secrets is handled correctly."""
        raw = RawEvidenceText(
            "Log output:\n"
            "  password=admin123\n"
            "  token=abc123xyz\n"
            "  api_key=sk-test123\n"
            "End of log"
        )
        redacted = redact_evidence_text(raw)
        assert "admin123" not in redacted
        assert "abc123xyz" not in redacted
        assert "sk-test123" not in redacted


# ==============================================================================
# Safe placeholder acceptance tests
# ==============================================================================

class TestSafePlaceholderAcceptance:
    """Tests for safe placeholder acceptance."""

    def test_redacted_placeholder_accepted(self) -> None:
        """[REDACTED] placeholder is accepted."""
        redacted = RedactedEvidenceText("[REDACTED]")
        safe = approve_redacted_evidence_text(redacted)
        assert safe == "[REDACTED]"

    def test_redacted_with_kind_placeholder_accepted(self) -> None:
        """[REDACTED:<KIND>] placeholder is accepted."""
        redacted = RedactedEvidenceText("[REDACTED:PASSWORD]")
        safe = approve_redacted_evidence_text(redacted)
        assert safe == "[REDACTED:PASSWORD]"

    def test_redacted_placeholder_does_not_hide_other_secret(self) -> None:
        """A placeholder does not hide another residual secret."""
        redacted = RedactedEvidenceText("[REDACTED] password=real_secret")
        with pytest.raises(UnsafeEvidenceTextError):
            approve_redacted_evidence_text(redacted)

    def test_malformed_placeholder_rejected(self) -> None:
        """Malformed placeholder [REDACTED:PASSWORD)] is rejected."""
        redacted = RedactedEvidenceText("[REDACTED:PASSWORD)]")
        with pytest.raises(UnsafeEvidenceTextError) as exc_info:
            approve_redacted_evidence_text(redacted)
        assert exc_info.value.reason == "malformed_placeholder"

    def test_empty_kind_placeholder_rejected(self) -> None:
        """Empty kind placeholder [REDACTED:] is rejected."""
        redacted = RedactedEvidenceText("[REDACTED:]")
        with pytest.raises(UnsafeEvidenceTextError) as exc_info:
            approve_redacted_evidence_text(redacted)
        assert exc_info.value.reason == "malformed_placeholder"

    def test_space_instead_of_colon_rejected(self) -> None:
        """Placeholder with space instead of colon [REDACTED KIND] is rejected."""
        redacted = RedactedEvidenceText("[REDACTED KIND]")
        with pytest.raises(UnsafeEvidenceTextError) as exc_info:
            approve_redacted_evidence_text(redacted)
        assert exc_info.value.reason == "malformed_placeholder"

    def test_lowercase_kind_rejected(self) -> None:
        """Lowercase kind [REDACTED:password] is rejected."""
        redacted = RedactedEvidenceText("[REDACTED:password]")
        with pytest.raises(UnsafeEvidenceTextError) as exc_info:
            approve_redacted_evidence_text(redacted)
        assert exc_info.value.reason == "malformed_placeholder"

    def test_lowercase_bracket_rejected(self) -> None:
        """Lowercase brackets [redacted] is not accepted as safe placeholder."""
        redacted = RedactedEvidenceText("[redacted]")
        with pytest.raises(UnsafeEvidenceTextError) as exc_info:
            approve_redacted_evidence_text(redacted)
        assert exc_info.value.reason == "malformed_placeholder"


# ==============================================================================
# Non-secret text preservation tests
# ==============================================================================

class TestNonSecretTextPreservation:
    """Tests for non-secret text that should NOT be redacted."""

    def test_generic_diagnostic_token_not_redacted(self) -> None:
        """Generic diagnostic discussion with 'token' is not automatically redacted."""
        raw = RawEvidenceText("Token count: 1500 tokens used in prompt")
        redacted = redact_evidence_text(raw)
        assert "Token count: 1500 tokens used in prompt" == redacted

    def test_max_tokens_not_redacted(self) -> None:
        """max_tokens is not treated as a secret."""
        raw = RawEvidenceText("max_tokens: 2048")
        redacted = redact_evidence_text(raw)
        assert redacted == "max_tokens: 2048"

    def test_total_tokens_not_redacted(self) -> None:
        """total_tokens is not treated as a secret."""
        raw = RawEvidenceText("total_tokens: 4096")
        redacted = redact_evidence_text(raw)
        assert redacted == "total_tokens: 4096"

    def test_kubernetes_secret_discussion_not_redacted(self) -> None:
        """Kubernetes Secret resource discussion is not automatically redacted."""
        raw = RawEvidenceText("Kubernetes Secret 'api-keys' contains sensitive data")
        redacted = redact_evidence_text(raw)
        assert "api-keys" in redacted


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
