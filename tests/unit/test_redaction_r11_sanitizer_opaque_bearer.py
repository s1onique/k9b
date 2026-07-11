"""Opaque Bearer token regression coverage across sanitizer entry points."""

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

OPAQUE = "opaque-production-token-123"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvcGFxdWUifQ.signature"
INPUTS = (
    f"Bearer {OPAQUE}",
    f"Authorization: Bearer {OPAQUE}",
    f"Authorization: Bearer {JWT}",
)


def _flatten_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_flatten_strings(item))
        return out
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            out.extend(_flatten_strings(item))
        return out
    return []


def _sanitize(path_name: str, text: str) -> object:
    prefix = "prefix benign-context "
    suffix = " suffix"
    wrapped = f"{prefix}{text}{suffix}"
    if path_name == "sanitize_payload":
        return sanitize_payload(wrapped)
    if path_name == "sanitize_prompt":
        return sanitize_prompt(wrapped)
    if path_name == "sanitize_log_entry":
        return sanitize_log_entry({"message": wrapped, "other": "benign-context"})
    if path_name == "sanitize_execution_output":
        return sanitize_execution_output(wrapped, f"stderr {wrapped}")
    if path_name == "sanitize_exception_message":

        class _OpaqueBearerExc(Exception):
            def __str__(self) -> str:
                return wrapped

        return sanitize_exception_message(_OpaqueBearerExc())
    raise AssertionError(f"unknown path {path_name}")


@pytest.mark.parametrize("raw", INPUTS)
@pytest.mark.parametrize(
    "path_name",
    (
        "sanitize_payload",
        "sanitize_prompt",
        "sanitize_log_entry",
        "sanitize_execution_output",
        "sanitize_exception_message",
    ),
)
def test_opaque_bearer_is_redacted_across_sanitizer_entry_points(
    raw: str,
    path_name: str,
) -> None:
    """Opaque Bearer credentials are redacted without dropping benign context."""
    output = _sanitize(path_name, raw)
    strings = _flatten_strings(output)
    assert strings, f"no string output for {path_name}: {output!r}"
    exact_token = JWT if JWT in raw else OPAQUE
    joined = "\n".join(strings)
    assert exact_token not in joined
    assert REDACTION_PLACEHOLDER in joined
    assert "benign-context" in joined
