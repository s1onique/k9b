"""Unit tests for make_redacted_evidence_text redaction behavior.

ACT-K9B-HULK-LLM-SAFE-EVIDENCE-BOUNDARY01.

Tests for:
- make_redacted_evidence_text redaction behavior
- Various secret patterns are redacted
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_evidence import make_redacted_evidence_text


class TestMakeRedactedEvidenceText:
    """Tests for make_redacted_evidence_text redaction behavior.

    make_redacted_evidence_text is a REDACTION function that replaces secrets
    with placeholders, not a validator that raises errors.
    """

    def test_accepts_valid_text(self) -> None:
        """Accepts valid text without secrets."""
        text = make_redacted_evidence_text("Pod nginx-abc123 is in CrashLoopBackOff state")
        assert text == "Pod nginx-abc123 is in CrashLoopBackOff state"
        assert isinstance(text, str)

    def test_rejects_empty_text(self) -> None:
        """Rejects empty text."""
        with pytest.raises(ValueError, match="cannot be empty"):
            make_redacted_evidence_text("")

    def test_redacts_password_pattern(self) -> None:
        """Redacts password= pattern with placeholder."""
        text = make_redacted_evidence_text("password=secret123")
        assert "<scrubbed>" in text
        assert "secret123" not in text

    def test_redacts_secret_pattern(self) -> None:
        """Redacts secret= pattern with placeholder."""
        text = make_redacted_evidence_text("secret=my-api-key")
        assert "<scrubbed>" in text
        assert "my-api-key" not in text

    def test_redacts_token_pattern(self) -> None:
        """Redacts token= pattern with placeholder."""
        text = make_redacted_evidence_text("token=abc123xyz")
        assert "<scrubbed>" in text
        assert "abc123xyz" not in text

    def test_redacts_api_key_pattern(self) -> None:
        """Redacts api_key= pattern with placeholder."""
        text = make_redacted_evidence_text("api_key=sk-1234567890")
        assert "<scrubbed>" in text
        assert "sk-1234567890" not in text

    def test_redacts_bearer_token(self) -> None:
        """Redacts JWT-like bearer token with placeholder."""
        text = make_redacted_evidence_text("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJodHRwczovL2kuaW8ifQ.sig")
        assert "<scrubbed>" in text
        assert "eyJhbGciOiJIUzI1NiJ9" not in text

    def test_redacts_private_key_header(self) -> None:
        """Redacts private key header with placeholder."""
        text = make_redacted_evidence_text("-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAL\n-----END RSA PRIVATE KEY-----")
        assert "<scrubbed>" in text
        assert "MIIBOgIBAAJBAL" not in text

    def test_redacts_certificate_header(self) -> None:
        """Redacts certificate header with placeholder."""
        text = make_redacted_evidence_text("-----BEGIN CERTIFICATE-----\nMIIBOgIBAAJBAL\n-----END CERTIFICATE-----")
        assert "<scrubbed>" in text
        assert "MIIBOgIBAAJBAL" not in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
