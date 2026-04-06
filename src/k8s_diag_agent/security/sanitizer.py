"""Sanitization helpers for logs, prompts, and exported payloads."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Mapping, Sequence

REDACTION_PLACEHOLDER = "<scrubbed>"
_SECRET_MANIFEST_RE = re.compile(r"kind\s*[:=]\s*Secret", re.IGNORECASE)
_PROMPT_SENSITIVE_PATTERNS = [
    re.compile(r"(?i)authorization\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_.=]+"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*\S+"),
    re.compile(r"(?i)client_secret\s*[:=]\s*\S+"),
    re.compile(r"(?i)access_token\s*[:=]\s*\S+"),
    re.compile(r"(?i)kubeconfig\b"),
    re.compile(r"(?i)token\s*[=:]\s*\S+"),
]
_SENSITIVE_KEYWORDS = (
    "token",
    "secret",
    "password",
    "auth",
    "authorization",
    "credential",
    "kubeconfig",
    "api_key",
    "apikey",
    "access_token",
    "client_secret",
)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.replace("-", "_").lower()
    return any(keyword in normalized for keyword in _SENSITIVE_KEYWORDS)


def _sanitize_string(value: str) -> str:
    if not value:
        return value
    sanitized = value
    if _SECRET_MANIFEST_RE.search(sanitized):
        return REDACTION_PLACEHOLDER
    for pattern in _PROMPT_SENSITIVE_PATTERNS:
        if pattern.search(sanitized):
            sanitized = pattern.sub(REDACTION_PLACEHOLDER, sanitized)
    return sanitized


def _is_secret_manifest(value: Mapping[str, Any]) -> bool:
    kind = value.get("kind")
    if not kind:
        return False
    return str(kind).strip().lower() == "secret"


def _sanitize_mapping(value: Mapping[str, Any], *, parent_key: str | None = None) -> Dict[str, Any]:
    if _is_secret_manifest(value):
        metadata = value.get("metadata")
        return {
            "kind": str(value.get("kind") or "Secret"),
            "metadata": sanitize_payload(metadata) if isinstance(metadata, Mapping) else {},
            "redacted": "secret manifest",
        }
    sanitized: Dict[str, Any] = {}
    for key, item in value.items():
        key_str = str(key)
        if _is_sensitive_key(key_str):
            sanitized[key_str] = REDACTION_PLACEHOLDER
            continue
        sanitized[key_str] = sanitize_payload(item, parent_key=key_str)
    return sanitized


def _sanitize_sequence(value: Iterable[Any]) -> Any:
    if isinstance(value, tuple):
        return tuple(sanitize_payload(item) for item in value)
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, set):
        return [sanitize_payload(item) for item in value]
    return [sanitize_payload(item) for item in value]


def sanitize_payload(value: Any, *, parent_key: str | None = None) -> Any:
    if isinstance(value, str):
        return _sanitize_string(value)
    if isinstance(value, Mapping):
        return _sanitize_mapping(value, parent_key=parent_key)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return _sanitize_sequence(value)
    return value


def sanitize_log_entry(entry: Mapping[str, Any]) -> Dict[str, Any]:
    sanitized = sanitize_payload(entry)
    if isinstance(sanitized, Mapping):
        return dict(sanitized)
    return dict(entry)


def sanitize_prompt(prompt: str) -> str:
    sanitized = prompt
    for pattern in _PROMPT_SENSITIVE_PATTERNS:
        sanitized = pattern.sub(REDACTION_PLACEHOLDER, sanitized)
    if _SECRET_MANIFEST_RE.search(sanitized):
        sanitized = re.sub(r"(?is)^.*?kind\s*[:=]\s*Secret.*?(?:\n\s*\n|$)", "<scrubbed secret manifest>\n", sanitized)
    return sanitized
