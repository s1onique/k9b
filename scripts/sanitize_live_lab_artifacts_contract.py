"""Contracts for sanitize_live_lab_artifacts.

This module contains the shared types, constants, and data structures
used across the sanitization pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Re-export for backward compatibility
REDACTION_PLACEHOLDER = "<REDACTED>"


# ============================================================================
# FINDING CLASSIFICATION
# ============================================================================

class FindingKind:
    """Finding severity levels for structured verification."""
    FATAL = "fatal"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Finding:
    """A finding from sanitization or verification."""
    kind: str  # FATAL, WARNING, INFO
    message: str
    file: str
    context: str | None = None

    def __str__(self) -> str:
        base = f"[{self.kind.upper()}] {self.file}: {self.message}"
        if self.context:
            base += f" ({self.context})"
        return base


@dataclass
class SanitizationResult:
    """Result of sanitizing a single file."""
    input_path: Path
    output_path: Path
    success: bool
    findings: list[Finding]
    error: str | None = None


# ============================================================================
# PATTERN DEFINITIONS
# ============================================================================

# Actual secret values that should be redacted (fatal if found)
# IMPORTANT: These patterns must match actual credential VALUES, not safe field names.
# Safe Kubernetes/CNPG Secret references (superuserSecret.name, clientCASecret, etc.)
# are handled structurally, not via raw text regex.
_FATAL_PATTERNS: list[re.Pattern[str]] = [
    # JWT tokens (actual values, not field names)
    re.compile(r"eyJ[A-Za-z0-9+/=_-]+\.eyJ[A-Za-z0-9+/=_-]+"),
    # Bearer token values (actual values)
    re.compile(r"(?i)bearer\s+[A-Za-z0-9+/=_\-\.]{20,}"),
    # AWS keys
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # OpenAI keys
    re.compile(r"sk-[0-9A-Za-z]{32,}"),
    # GitHub PATs
    re.compile(r"github_pat_[A-Za-z0-9_]{22,82}"),
    # Private key blocks (actual values)
    re.compile(r"-----BEGIN\s+(RSA |EC |DSA |OPENSSH |PRIVATE |ENCRYPTED )?PRIVATE KEY-----"),
    # Certificates (actual values)
    re.compile(r"-----BEGIN\s+CERTIFICATE-----"),
    # Raw password values (actual values, not field names)
    re.compile(r"(?i)(^|\s)password:\s*[^\s]{8,}"),
    # API key values (actual values, not field names)
    re.compile(r"(?i)(^|\s)api_key:\s*[^\s]{8,}"),
    # Authorization header values
    re.compile(r"(?i)authorization:\s*[A-Za-z0-9+/=_\-\.]{20,}"),
    # Client/private key data field values (when the value itself looks like a credential)
    re.compile(r"(?i)(^|\s)(client-key-data|private-key-data):\s*[A-Za-z0-9+/=_\-\.]{20,}"),
    # Token values (sha256~ or similar)
    re.compile(r"(?i)token:\s*sha256~[A-Za-z0-9+/]+"),
]


# Known non-secret configuration paths that should NOT trigger redaction.
# These are auth configuration fields like mode, enabled, provider, etc.
# that contain safe enum/string values, not actual credentials.
# Format: dot-separated path from root, with container names joined.
_NON_SECRET_AUTH_PATHS: frozenset[str] = frozenset({
    # Top-level auth configuration
    "auth.mode",
    "auth.enabled",
    "auth.provider",
    "auth.secureCookie",
    "auth.sessionCookieName",
    "auth.sessionMaxAgeSeconds",
    "auth.sessionIdleTimeoutSeconds",
    # Nested backend auth configuration
    "backend.auth.mode",
    "backend.auth.enabled",
    "backend.auth.provider",
    "backend.auth.secureCookie",
    "backend.auth.sessionCookieName",
    "backend.auth.sessionMaxAgeSeconds",
    "backend.auth.sessionIdleTimeoutSeconds",
    # Additional common auth config fields
    "auth.cookieSecure",
    "backend.auth.cookieSecure",
    "auth.tlsEnabled",
    "backend.auth.tlsEnabled",
    "auth.oidcProviderUrl",
    "backend.auth.oidcProviderUrl",
})


# Suffix patterns for nested auth config paths (e.g., values.auth.mode)
_NON_SECRET_AUTH_PATH_SUFFIXES: frozenset[str] = frozenset({
    ".auth.mode",
    ".auth.enabled",
    ".auth.provider",
    ".backend.auth.mode",
    ".backend.auth.enabled",
})


# Sensitive field names that should trigger redaction of VALUES (not keys)
# These are field names that contain actual credential data
# NOTE: "data", "stringdata", "binarydata" are handled specially for Secrets
# in _sanitize_mapping (Secret special case), so we don't include them here
# to avoid redacting ConfigMap.data values
_SENSITIVE_VALUE_FIELDS: frozenset[str] = frozenset({
    # Kubeconfig user credentials
    "token",
    "client-key-data",
    "client-certificate-data",
    "client-key",
    "client-certificate",
    "password",
    # Auth container (values nested under auth.* may be sensitive)
    "auth",
    # Auth-related credential fields
    "authorization",
    # Generic credentials
    "secret",
    "credential",
    "credentials",
    # Private keys
    "privatekey",
    "private-key",
    "key",
    # Registry
    "registrypassword",
    "registry-credentials",
})


# Field names that are safe (Kubernetes vocabulary) - should NOT trigger redaction
# These are metadata/field names, not actual secret values.
# IMPORTANT: These handle CNPG/Kubernetes Secret reference field names, NOT actual secret data.
# The actual secret data (base64-encoded values in Secret.data/stringData) is handled
# separately by _sanitize_secret_object().
_SAFE_K8S_FIELDS: frozenset[str] = frozenset({
    # Secret resource references (pointing TO a Secret by name)
    "secretname",
    "secretref",
    "secretnames",
    "secrets",
    # CNPG Secret reference fields (pointing to Secret objects by name, NOT actual secret values)
    "superusersecret",     # superuserSecret.name in CNPG Cluster bootstrap
    "clientcasecret",      # clientCASecret in CNPG Cluster
    "casecret",            # caSecret in CNPG Cluster
    "servercasecret",      # serverCASecret in CNPG Cluster
    "replicationslotsecret",  # replicationSlotSecret in CNPG
    "slotprefix",          # slotPrefix in CNPG replicationSlots highAvailability
    # imagePullSecrets references (list of Secret references by name)
    "imagepullsecret",     # singular form
    "imagepullsecrets",    # plural form (CNPG standard field name)
    # Bootstrap initdb secret fields (metadata, not values)
    "bootstrapsecret",
    "initdbsecret",
    "databasesecret",
    "ownername",
    # Service account references
    "serviceaccountname",
    "serviceaccount",
    "serviceaccounttoken",
    # ConfigMaps (often referenced near secrets)
    "configmapname",
    "configmapref",
    # Auto-mount flag
    "automountserviceaccounttoken",
    "automountserviceaccount",
    # RBAC
    "roleref",
    "subjects",
    # Volume projections
    "projected",
    "projectedserviceaccounttoken",
    # Auth mode
    "authmode",
    "authenticationmode",
    "authorizationmode",
    "incluster",
    # Path labels
    "kubecfgpath",
    "kubeconfigpath",
    "kubepath",
    # CNPG cluster fields
    "clustername",
    "namespace",
    "secrettemplate",
})


# Known-safe boolean fields that contain "token" but aren't credentials
_SAFE_BOOLEAN_PATTERNS: frozenset[str] = frozenset({
    "automountserviceaccounttoken",
    "automount_service_account_token",
    "defaulttoken",
    "disableauthtoken",
})


# ============================================================================
# YAML LOADING HELPERS
# ============================================================================

def _yaml_safe_load(content: str) -> list[Any] | None:
    """Load YAML content safely, returning list of documents on parse errors."""
    import yaml
    try:
        # Use safe_load_all to handle multi-document YAML streams
        docs = list(yaml.safe_load_all(content))
        return docs if docs else None
    except yaml.YAMLError:
        return None


def _yaml_safe_dump(data: Any) -> str:
    """Dump data as YAML with string quoting preserved."""
    import yaml
    return yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)  # type: ignore[no-any-return]


def _yaml_safe_dump_all(data: list[Any]) -> str:
    """Dump multiple YAML documents with string quoting preserved."""
    import yaml
    return yaml.safe_dump_all(data, default_flow_style=False, sort_keys=False, allow_unicode=True)  # type: ignore[no-any-return]


def load_yaml_safe(content: str) -> list[Any] | None:
    """Load YAML content safely, returning list of documents on parse errors."""
    import yaml
    try:
        docs = list(yaml.safe_load_all(content))
        return docs if docs else None
    except yaml.YAMLError:
        return None
