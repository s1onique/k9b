"""Canonical redaction policy for evidence text.

This module defines the canonical patterns, classification, and replacement policy
for sensitive text in evidence content. It is the single source of truth for
redaction patterns used by both the sanitizer and evidence projection modules.

Shared API:
    redact_sensitive_text(value: str) -> str:
        Apply all redaction patterns to replace sensitive content with placeholders.

    sensitive_text_category(value: str) -> SensitiveTextCategory | None:
        Classify the category of detected sensitive text pattern.
"""

from __future__ import annotations

import re
from enum import Enum

# Safe placeholder for redacted content
REDACTION_PLACEHOLDER: str = "<scrubbed>"

# Accepted safe placeholder patterns (EXACT match only)
# Valid: [REDACTED], [REDACTED:PASSWORD], [REDACTED:KIND]
# Invalid: [REDACTED:PASSWORD)], [REDACTED:], [REDACTED KIND], [redacted]
SAFE_PLACEHOLDER_RE = re.compile(r"^\[REDACTED(?::[A-Z_]+)?\]$")


class SensitiveTextCategory(Enum):
    """Categories of sensitive text that can be detected."""

    BEARER_TOKEN = "bearer_token"
    AUTHORIZATION = "authorization"
    API_KEY = "api_key"
    CLIENT_SECRET = "client_secret"
    ACCESS_TOKEN = "access_token"
    TOKEN = "token"
    PASSWORD = "password"
    SECRET = "secret"
    CLIENT_KEY_DATA = "client_key_data"
    CLIENT_CERTIFICATE_DATA = "client_certificate_data"
    PRIVATE_KEY = "private_key"
    CERTIFICATE = "certificate"
    DATABASE_URL = "database_url"
    URL_USERINFO = "url_userinfo"
    UNKNOWN = "credential"


# Canonical patterns for evidence redaction
# Order matters: more specific patterns should come before general ones
REDACTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Authorization headers (Bearer token, Basic auth, etc.)
    re.compile(r"(?i)authorization\s*[:=]\s*Bearer\s+[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_=]+"),
    re.compile(r"(?i)authorization\s*[:=]\s*Basic\s+[A-Za-z0-9+/=]+"),
    # Opaque Bearer token (single-segment; not JWT-shaped). Catches
    # ``Authorization: Bearer opaque-token-abc`` without requiring
    # dot-segmentation.
    re.compile(r"(?i)authorization\s*[:=]\s*Bearer\s+[A-Za-z0-9\-_=\.]{8,}"),
    re.compile(r"(?i)authorization\s*[:=]\s*\S+"),
    # JWT/bearer tokens (standalone, not in header)
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_=]+"),
    # Standalone opaque Bearer credentials (non-JWT-shaped).
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_=\.]{12,}"),
    # API key assignments (various forms)
    re.compile(r"(?i)api[_-]?key\s*[=:]\s*['\"]?[A-Za-z0-9\-_]+['\"]?"),
    # JSON-style API key: "apiKey": "<secret>"
    re.compile(r'"apiKey"\s*:\s*"[^"]+"'),
    # Client secrets
    re.compile(r"(?i)client_secret\s*[=:]\s*['\"]?\S+['\"]?"),
    # Access tokens
    re.compile(r"(?i)access_token\s*[=:]\s*['\"]?[A-Za-z0-9\-_]+['\"]?"),
    # Token assignments (credential context with word boundary)
    re.compile(r"(?i)\btoken\s*[=:]\s*['\"]?[A-Za-z0-9\-_.=]+['\"]?"),
    # Kubernetes Secret data key: matches identifiers like
    # `KUBE_SECRET_TOKEN_abc123=...` even when the literal characters
    # surrounding the `token=` pair are underscore or other identifier chars.
    # Preserves established sentinel-form scrubbing from R7.
    # We require `=` (not `:`) so that observability labels like
    # `max_tokens: 2048` are NOT scrubbed.
    re.compile(r"(?i)\b[A-Za-z0-9_]*TOKEN[A-Za-z0-9_]*\s*=\s*['\"]?[^\s'\"]+['\"]?"),
    re.compile(r"(?i)\b[A-Za-z0-9_]*SECRET[A-Za-z0-9_]*\s*=\s*['\"]?[^\s'\"]+['\"]?"),
    # JSON-style token: "token": "<secret>"
    re.compile(r'"token"\s*:\s*"[^"]+"'),
    # Password assignments (various forms)
    # password=<secret>, password: <secret>
    re.compile(r"(?i)\bpassword\s*[=:]\s*['\"]?\S+['\"]?"),
    # JSON-style password: "password": "<secret>"
    re.compile(r'"password"\s*:\s*"[^"]+"'),
    # 'password': '<secret>' (single quotes)
    re.compile(r"'password'\s*:\s*'[^']+'"),
    # All uppercase (env var style): PASSWORD=secret
    re.compile(r"\bPASSWORD\s*[=:]\s*\S+"),
    # Secret assignments
    re.compile(r"(?i)\bsecret\s*[=:]\s*['\"]?\S+['\"]?"),
    # JSON-style secret: "secret": "<secret>"
    re.compile(r'"secret"\s*:\s*"[^"]+"'),
    # Kubernetes client key data (base64-encoded PEM)
    re.compile(r"(?i)client[_-]key[_-]data\s*[=:]\s*['\"]?[A-Za-z0-9+/=]{20,}['\"]?"),
    # Kubernetes client certificate data (base64-encoded cert)
    re.compile(r"(?i)client[_-]certificate[_-]data\s*[=:]\s*['\"]?[A-Za-z0-9+/=]{20,}['\"]?"),
    # Private key PEM blocks
    re.compile(r"-----BEGIN\s+(RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE\s+KEY-----[\s\S]*?-----END\s+(RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE\s+KEY-----"),
    # Certificate PEM blocks
    re.compile(r"-----BEGIN\s+CERTIFICATE-----[\s\S]*?-----END\s+CERTIFICATE-----"),
    # Database URLs with embedded credentials
    re.compile(r"(?i)(postgres|postgresql|mysql|mariadb|mssql|oracle|sqlite|mongodb|redis|amqp)://[^:]+:[^@]+@"),
    # URL userinfo credentials (https://user:password@host/path)
    re.compile(r"://[^:]+:[^@]+@"),
    # Generic credential patterns in query strings
    re.compile(r"[?&](password|passwd|pwd|secret|token|apikey|api_key)\s*[=:]\s*[^&\s'\"]+", re.IGNORECASE),
)


def redact_sensitive_text(value: str) -> str:
    """Apply the canonical redaction policy to replace sensitive content.

    Args:
        value: Text content to redact

    Returns:
        Text with sensitive patterns replaced by REDACTION_PLACEHOLDER
    """
    if not value:
        return value

    result = value
    for pattern in REDACTION_PATTERNS:
        result = pattern.sub(REDACTION_PLACEHOLDER, result)

    return result


def sensitive_text_category(value: str) -> SensitiveTextCategory | None:
    """Classify the category of detected sensitive text pattern.

    Args:
        value: Text to check for sensitive patterns

    Returns:
        The category of the first detected pattern, or None if no pattern found
    """
    for pattern in REDACTION_PATTERNS:
        if pattern.search(value):
            pattern_str = pattern.pattern
            if "bearer" in pattern_str.lower():
                return SensitiveTextCategory.BEARER_TOKEN
            elif "authorization" in pattern_str.lower():
                return SensitiveTextCategory.AUTHORIZATION
            elif "apiKey" in pattern_str:
                return SensitiveTextCategory.API_KEY
            elif "api" in pattern_str.lower():
                return SensitiveTextCategory.API_KEY
            elif "client_secret" in pattern_str.lower():
                return SensitiveTextCategory.CLIENT_SECRET
            elif "access_token" in pattern_str.lower():
                return SensitiveTextCategory.ACCESS_TOKEN
            elif '"token"' in pattern_str:
                return SensitiveTextCategory.TOKEN
            elif "token" in pattern_str.lower():
                return SensitiveTextCategory.TOKEN
            elif '"password"' in pattern_str or "'password'" in pattern_str:
                return SensitiveTextCategory.PASSWORD
            elif "password" in pattern_str.lower():
                return SensitiveTextCategory.PASSWORD
            elif "PASSWORD" in pattern_str:
                return SensitiveTextCategory.PASSWORD
            elif '"secret"' in pattern_str:
                return SensitiveTextCategory.SECRET
            elif "secret" in pattern_str.lower():
                return SensitiveTextCategory.SECRET
            elif "client_key_data" in pattern_str.lower():
                return SensitiveTextCategory.CLIENT_KEY_DATA
            elif "client_certificate_data" in pattern_str.lower():
                return SensitiveTextCategory.CLIENT_CERTIFICATE_DATA
            elif "PRIVATE" in pattern_str:
                return SensitiveTextCategory.PRIVATE_KEY
            elif "CERTIFICATE" in pattern_str:
                return SensitiveTextCategory.CERTIFICATE
            elif "://" in pattern_str and "@" in pattern_str:
                # URL with credentials
                if any(db in pattern_str.lower() for db in ("postgres", "postgresql", "mysql", "mongodb", "redis")):
                    return SensitiveTextCategory.DATABASE_URL
                return SensitiveTextCategory.URL_USERINFO
            else:
                return SensitiveTextCategory.UNKNOWN

    return None
