"""Sanitizer regression coverage and complete credential/mixed-input matrix.

ACT-K9B-HULK-SECRET-REDACTION-TYPES01-R9 sections 6 & 7.

This module consolidates:

* Sanitizer regression: all established sentinel forms through all five
  sanitizer entry points - sanitize_payload, sanitize_prompt,
  sanitize_log_entry, sanitize_execution_output, sanitize_exception_message.
  Each sentinel's synthetic secret must be absent from the result.
* Logging safety: every sanitizer entry point absorbs a known-good
  secret from prompts/logs without leaking it.

* Credential matrix: 4 established credential forms plus the URL
  replacement with the required exact-secret-absent/placeholder-present
  assertions, including the strong URL secret assertion that replaces
  R5's weak `assert "<scrubbed>" in result`.

* Bare-word "kubeconfig" decision: the existing sanitizer behavior is
  preserved (kubeconfig is in _SENSITIVE_KEYWORDS so a key named
  `kubeconfig` is scrubbed to `<scrubbed>`); the rationale is the
  repo doctrine under docs/doctrine/path-security-doctrine.md and
  the existing live-lab tests. No behavior change is implied.
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.security.redaction_policy import REDACTION_PLACEHOLDER
from k8s_diag_agent.security.sanitizer import (
    sanitize_exception_message,
    sanitize_execution_output,
    sanitize_log_entry,
    sanitize_payload,
    sanitize_prompt,
)

# ---------------------------------------------------------------------------
# Section 6: Sentinel regression
# ---------------------------------------------------------------------------
#
# Audit of established sanitizer behavior (R7 / R8 / current):
#
#   Sentinel                              | Pattern that scrubs it
#   --------------------------------------+-------------------------------
#   KUBE_SECRET_TOKEN_abc123=value        | token=value (covers token in
#                                        | KUBE_SECRET_TOKEN_*=value)
#   Authorization: Bearer <jwt-3-part>    | authorization + JWT-shape bearer
#   Bearer <jwt-3-part> (no Authorization) | standalone JWT bearer pattern
#   api_key=<alphanumeric value>          | api_key=alphanumeric pattern
#   client_secret=<non-whitespace>        | client_secret=\S+ pattern
#   access_token=<alphanumeric value>     | access_token=alphanumeric
#   token=<alphanumeric value>           | token=alphanumeric
#   password=<non-whitespace>             | password=\S+ (broadest)
#
# These contexts are the established credential-bearing forms. The
# CANONICAL sentinel strings (KUBE_SECRET_TOKEN_abc123, <synthetic>,
# etc.) are tagged so the assertion "exact sentinel string absent from
# sanitizer output" is observable.
# ---------------------------------------------------------------------------


# Each (label, credential_context_string, sentinel_tag_to_assert_absent)
# Examples:
#   - "KUBE_SECRET_TOKEN_abc123 = KUBE_SECRET_TOKEN_abc123=sensitive"
#     credential_context_string is "KUBE_SECRET_TOKEN_abc123=sensitive"
#     sentinel tag is "KUBE_SECRET_TOKEN_abc123"
SENTINEL_FORMS: list[tuple[str, str, str]] = [
    (
        "KUBE_SECRET_TOKEN",
        "KUBE_SECRET_TOKEN_abc123=sensitive",
        "KUBE_SECRET_TOKEN_abc123",
    ),
    (
        "Authorization: Bearer (JWT-shaped)",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJzdGF0ZS1vbmUifQ.sig",
        "eyJhbGciOiJIUzI1NiJ9",
    ),
    (
        "Bearer only (JWT-shaped)",
        "bearer eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJzdGF0ZS10d28ifQ.sig",
        "eyJhbGciOiJIUzI1NiJ9",
    ),
    (
        "api_key",
        "api_key=sk-abcdefghij1234",
        "sk-abcdefghij1234",
    ),
    (
        "client_secret",
        "client_secret=super_secret_value",
        "super_secret_value",
    ),
    (
        "access_token",
        "access_token=acc-abcdef0123",
        "acc-abcdef0123",
    ),
    (
        "token",
        "token=tok-abcdef0123",
        "tok-abcdef0123",
    ),
    (
        "password",
        "password=pass-abcdef0123",
        "pass-abcdef0123",
    ),
]


def _flatten_strings(value: object) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            out.extend(_flatten_strings(item))
    elif isinstance(value, dict):
        for v in value.values():
            out.extend(_flatten_strings(v))
    return out


SENTINEL_SANITIZER_PATHS = (
    "sanitize_payload",
    "sanitize_prompt",
    "sanitize_log_entry",
    "sanitize_execution_output",
    "sanitize_exception_message",
)


@pytest.mark.parametrize("label,credential_string,sentinel", SENTINEL_FORMS)
@pytest.mark.parametrize("path_name", SENTINEL_SANITIZER_PATHS)
def test_sentinel_secret_is_absent_from_every_sanitizer_path(
    label: str,
    credential_string: str,
    sentinel: str,
    path_name: str,
) -> None:
    """For each sentinel credential form and each sanitizer entry point,
    the unique sentinel tag MUST be absent from the sanitizer output."""

    if path_name == "sanitize_payload":
        output = sanitize_payload(credential_string)
    elif path_name == "sanitize_prompt":
        prompt = f"Diagnostic header\n{credential_string}\nDiagnostic trailer"
        output = sanitize_prompt(prompt)
    elif path_name == "sanitize_log_entry":
        entry = {
            "ts": "2026-01-01T00:00:00Z",
            "msg": f"observed {credential_string}",
            "context": credential_string,
        }
        output = sanitize_log_entry(entry)
    elif path_name == "sanitize_execution_output":
        raw = f"command output {credential_string}"
        err = f"error summary {credential_string}"
        out, err2 = sanitize_execution_output(raw, err)
        output = (out or "") + (err2 or "")
    elif path_name == "sanitize_exception_message":

        class _SyntheticExc(Exception):
            def __str__(self) -> str:
                return f"synthetic leaked: {credential_string}"

        exc = _SyntheticExc()
        output = sanitize_exception_message(exc)
    else:  # pragma: no cover - defensive
        pytest.fail(f"Unknown sanitizer path: {path_name}")

    all_strings = _flatten_strings(output)
    for s in all_strings:
        assert sentinel not in s, f"Sanitizer {path_name} leaked sentinel {label!r} (tag {sentinel!r}) in output: {s!r}"


# ---------------------------------------------------------------------------
# Section 7: Credential matrix
# ---------------------------------------------------------------------------


class TestCredentialMatrix:
    """Complete credential and mixed-input matrix.

    R5's weak URL assertion
        assert "super_secret" not in result
        assert REDACTION_PLACEHOLDER in result or "[" in result
    is replaced by the strong, narrow form:
        synthetic_secret = "url-secret-value"
        assert synthetic_secret not in result
        assert REDACTION_PLACEHOLDER in result

    Note: The matrix exercises the SHARED redaction policy
    (`redact_sensitive_text`) directly. The shared policy is the same
    one consumed by both the LLM-safe projection pipeline and the
    sanitizer; using it here keeps each case focused on the credential-
    scrubbing assertion rather than on placeholder grammar.
    """

    @staticmethod
    def _redact(raw: str) -> str:
        from k8s_diag_agent.security.redaction_policy import (
            redact_sensitive_text,
        )

        return str(redact_sensitive_text(raw))

    def test_max_tokens_with_password_value(self) -> None:
        """max_tokens: 2048 password=<synthetic>: synthetic absent, max_tokens retained."""
        synthetic_secret = "pwd-secret-mt-1234"
        raw_text = f"max_tokens: 2048 password={synthetic_secret}"
        result = self._redact(raw_text)
        assert synthetic_secret not in result
        assert "max_tokens: 2048" in result

    def test_kubernetes_secret_observed_token(self) -> None:
        """Kubernetes Secret observed; token=<synthetic> redacted."""
        synthetic_secret = "tok-secret-ks-1234"
        raw_text = f"Kubernetes Secret observed; token={synthetic_secret}"
        result = self._redact(raw_text)
        assert synthetic_secret not in result

    def test_token_generation_test_api_key(self) -> None:
        """token generation test; api_key=<synthetic> redacted."""
        synthetic_secret = "sk-secret-tg-1234"
        raw_text = f"token generation test; api_key={synthetic_secret}"
        result = self._redact(raw_text)
        assert synthetic_secret not in result

    def test_redacted_placeholder_password_value(self) -> None:
        """[REDACTED] password=<synthetic>: synthetic absent.

        Note: [REDACTED] appears at the start of the line as a
        placeholder token. The credential form `password=...` is
        scrubbed independently.
        """
        synthetic_secret = "pwd-secret-rp-1234"
        raw_text = f"[REDACTED] password={synthetic_secret}"
        result = self._redact(raw_text)
        assert synthetic_secret not in result
        # The [REDACTED] placeholder token at the start is preserved.
        assert "[REDACTED]" in result

    def test_url_userinfo_replaced_exact_secret_absent(self) -> None:
        """URL userinfo: synthetic secret MUST be absent AND REDACTION_PLACEHOLDER
        MUST be present.

        This is the canonical replacement of the prior weak URL assertion:
            synthetic_secret = "url-secret-value"
            assert synthetic_secret not in result
            assert REDACTION_PLACEHOLDER in result
        """
        synthetic_secret = "url-secret-value"
        raw_text = f"https://admin:{synthetic_secret}@db.example.com/api"
        result = self._redact(raw_text)
        assert synthetic_secret not in result
        assert REDACTION_PLACEHOLDER in result

    def test_database_url_redacted(self) -> None:
        """Postgres-style credential URL: synthetic absent, placeholder present."""
        synthetic_secret = "db-secret-cred-1234"
        raw_text = f"postgres://admin:{synthetic_secret}@db.example.com:5432/mydb"
        result = self._redact(raw_text)
        assert synthetic_secret not in result
        assert REDACTION_PLACEHOLDER in result

    def test_bearer_jwt_token_redacted(self) -> None:
        """Authorization: Bearer <jwt>: jwt absent, placeholder present."""
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NSJ9.sigvalue"
        raw_text = f"Authorization: Bearer {jwt}"
        result = self._redact(raw_text)
        # The full Authorization: Bearer <jwt> shape is redacted; the
        # synthetic JWT MUST be absent.
        assert jwt not in result
        assert REDACTION_PLACEHOLDER in result

    def test_pem_private_key_redacted(self) -> None:
        """PEM private key block: synthetic absent."""
        raw_text = "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBALRIMCREDENTIALFOO\n-----END RSA PRIVATE KEY-----"
        result = self._redact(raw_text)
        assert "MIIBOgIBAAJBALRIMCREDENTIALFOO" not in result
        # ... and the surrounding header/footer must also be redacted.
        assert "-----BEGIN RSA PRIVATE KEY-----" not in result


# ---------------------------------------------------------------------------
# Bare-word 'kubeconfig' decision (R9 §6).
# ---------------------------------------------------------------------------


class TestBareWordKubeconfigDecision:
    """Document the bare-word 'kubeconfig' decision.

    The current `_SENSITIVE_KEYWORDS` set in `k8s_diag_agent.security.sanitizer`
    contains `"kubeconfig"`. The behavior is: any JSON/dict key named
    `kubeconfig` is scrubbed to REDACTION_PLACEHOLDER.

    Rationale (preserved from R7/R8 doctrine):

    * `docs/security/threat-model.md` treats kubeconfig as a sensitive
      artifact that contains bearer tokens, CA data, and embedded
      client credentials.
    * `tests/test_extract_kubeconfig_context_secret*.py` exercises the
      parser contract that consumes kubeconfig files; preserving the
      key-based scrub guarantees that ANY emitted JSON containing a
      kubeconfig key is safe to log.
    * R7 invariant: scrub any key whose name matches `_SENSITIVE_KEYWORDS`.

    This test documents and PINS the existing behavior without changing
    it. If the doctrine changes, the test is the single place to update.
    """

    def test_kubeconfig_key_is_scrubbed_in_payload(self) -> None:
        out = sanitize_payload(
            {
                "kubeconfig": "apiVersion: v1\nclusters: [...]",
                "context": "ok",
            }
        )
        assert out["kubeconfig"] == REDACTION_PLACEHOLDER
        assert out["context"] == "ok"

    def test_kubeconfig_in_string_is_not_bare_word_scrubbed(self) -> None:
        # The bare-word scrub applies ONLY to dict keys; a sentence that
        # contains the substring "kubeconfig" is not affected by key-based
        # scrubbing and is not picked up by the per-string patterns.
        text = "We discussed kubeconfig in the post-mortem"
        out = sanitize_payload(text)
        assert "kubeconfig" in out
