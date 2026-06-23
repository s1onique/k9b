#!/usr/bin/env python3
"""
sanitize_live_lab_artifacts.py

Structured sanitizer for live lab artifacts that:
- Parses JSON/YAML when possible and redacts actual sensitive values
- Preserves safe Kubernetes metadata (field names, resource names, RBAC)
- Writes sanitized copies to a separate directory for verification and upload

Usage:
    python scripts/sanitize_live_lab_artifacts.py --input ./lab-artifacts/live --output ./lab-artifacts/live-sanitized

Exit codes:
    0 - All artifacts sanitized successfully
    1 - Sanitization failed
    2 - Invalid arguments
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from re import Pattern
from typing import Any

import yaml

# Re-export for backward compatibility
REDACTION_PLACEHOLDER = "<REDACTED>"


# ============================================================================
# PATTERN DEFINITIONS
# ============================================================================

# Actual secret values that should be redacted (fatal if found)
# IMPORTANT: These patterns must match actual credential VALUES, not safe field names.
# Safe Kubernetes/CNPG Secret references (superuserSecret.name, clientCASecret, etc.)
# are handled structurally, not via raw text regex.
_FATAL_PATTERNS: list[Pattern[str]] = [
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
    # Generic credentials
    "secret",
    "credential",
    "credentials",
    # Auth headers
    "authorization",
    "auth",
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
# YAML LOADING HELPERS
# ============================================================================

def _yaml_safe_load(content: str) -> list[Any] | None:
    """Load YAML content safely, returning list of documents on parse errors."""
    try:
        # Use safe_load_all to handle multi-document YAML streams
        docs = list(yaml.safe_load_all(content))
        return docs if docs else None
    except yaml.YAMLError:
        return None


def _yaml_safe_dump(data: Any) -> str:
    """Dump data as YAML with string quoting preserved."""
    return yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)  # type: ignore[no-any-return]


def _yaml_safe_dump_all(data: list[Any]) -> str:
    """Dump multiple YAML documents with string quoting preserved."""
    return yaml.safe_dump_all(data, default_flow_style=False, sort_keys=False, allow_unicode=True)  # type: ignore[no-any-return]


# ============================================================================
# CORE SANITIZATION LOGIC
# ============================================================================

def _is_safe_k8s_field(key: str) -> bool:
    """Check if a field name is safe Kubernetes vocabulary (not actual secret)."""
    normalized = key.lower().replace("-", "").replace("_", "")
    # Check exact match first
    if normalized in _SAFE_K8S_FIELDS:
        return True
    # Check if it's a boolean flag containing "token" but not a value
    if normalized in _SAFE_BOOLEAN_PATTERNS:
        return True
    return False


def _should_redact_value_for_field(key: str) -> bool:
    """Check if the VALUE for this field should be redacted."""
    normalized = key.lower().replace("-", "").replace("_", "")
    # Fields that contain actual secret data
    return normalized in _SENSITIVE_VALUE_FIELDS


def _check_for_fatal_patterns(value: str) -> list[str]:
    """Check if a string value contains fatal patterns."""
    found = []
    for pattern in _FATAL_PATTERNS:
        if pattern.search(value):
            found.append(pattern.pattern[:50] + "..." if len(pattern.pattern) > 50 else pattern.pattern)
    return found


def _sanitize_string_value(value: str, field_key: str | None = None) -> tuple[str, list[Finding]]:
    """
    Sanitize a string value, returning (sanitized_value, findings).
    """
    if not isinstance(value, str):
        return value, []

    findings = []
    sanitized = value

    # Check for fatal patterns
    fatal_matches = _check_for_fatal_patterns(value)
    for match in fatal_matches:
        findings.append(Finding(
            kind=FindingKind.FATAL,
            message=f"Found credential pattern: {match}",
            file="",
            context=field_key,
        ))
        sanitized = REDACTION_PLACEHOLDER

    return sanitized, findings


def _sanitize_secret_object(data: Mapping[str, Any], file_path: str) -> tuple[dict[str, Any], list[Finding]]:
    """
    Object-level sanitization for Kubernetes Secret manifests.
    
    This is an EARLY RETURN function - it handles Secret objects at the object level
    BEFORE iterating over keys, preventing the original data/stringData/binaryData
    keys from being processed and potentially leaking into output.
    
    Returns (sanitized_data, findings).
    """
    findings: list[Finding] = []
    sanitized: dict[str, Any] = {}

    # Keep metadata as-is (contains safe information like name, namespace, labels)
    if "metadata" in data:
        sanitized["metadata"] = dict(data["metadata"])
    
    # Keep the kind field
    if "kind" in data:
        sanitized["kind"] = data["kind"]
    
    # Keep apiVersion if present
    if "apiVersion" in data:
        sanitized["apiVersion"] = data["apiVersion"]
    
    # Keep type if present (Opaque, kubernetes.io/tls, etc.)
    if "type" in data:
        sanitized["type"] = data["type"]
    
    # Mark that this was a Secret and its data fields were redacted
    sanitized["_sanitized"] = "secret"
    
    # Redact data field (base64-encoded sensitive values)
    if "data" in data:
        sanitized["data"] = {"<redacted>": "contains base64-encoded secret values"}
        findings.append(Finding(
            kind=FindingKind.WARNING,
            message="Secret.data field redacted (contains sensitive values)",
            file=file_path,
            context="Secret.data",
        ))
    
    # Redact stringData field (plaintext input that gets merged into data)
    if "stringData" in data:
        sanitized["stringData"] = {"<redacted>": "contains plaintext secret values"}
        findings.append(Finding(
            kind=FindingKind.WARNING,
            message="Secret.stringData field redacted (contains sensitive values)",
            file=file_path,
            context="Secret.stringData",
        ))
    
    # Redact binaryData field (base64-encoded binary sensitive values)
    if "binaryData" in data:
        sanitized["binaryData"] = {"<redacted>": "contains binary secret values"}
        findings.append(Finding(
            kind=FindingKind.WARNING,
            message="Secret.binaryData field redacted (contains sensitive values)",
            file=file_path,
            context="Secret.binaryData",
        ))
    
    return sanitized, findings


def _sanitize_mapping(
    data: Mapping[str, Any],
    parent_key: str | None = None,
    file_path: str = "",
) -> tuple[Any, list[Finding]]:
    """
    Recursively sanitize a mapping (dict), handling Kubernetes-specific structures.
    
    Returns (sanitized_data, findings).
    """
    findings = []
    sanitized: dict[str, Any] = {}

    # OBJECT-LEVEL CHECK: Detect Secret manifests BEFORE iterating over keys
    # This prevents the original data/stringData/binaryData keys from being
    # processed later in the loop and potentially leaking into output
    if str(data.get("kind", "")).lower() == "secret":
        return _sanitize_secret_object(data, file_path)

    for key, value in data.items():
        key_str = str(key)
        key_normalized = key_str.lower().replace("-", "").replace("_", "")

        # Special case: kubeconfig users
        if key_normalized == "users" and isinstance(value, list):
            sanitized_users = []
            for user in value:
                if isinstance(user, dict) and "user" in user:
                    user_data = dict(user["user"])
                    # Redact actual credential fields
                    for cred_field in ["token", "client-key-data", "client-certificate-data", 
                                       "client-key", "client-certificate", "password"]:
                        if cred_field in user_data:
                            findings.append(Finding(
                                kind=FindingKind.FATAL,
                                message=f"kubeconfig credential field '{cred_field}' redacted",
                                file=file_path,
                                context="kubeconfig.users[].user",
                            ))
                            user_data[cred_field] = REDACTION_PLACEHOLDER
                    sanitized_users.append({"name": user.get("name", "unnamed"), "user": user_data})
                else:
                    sanitized_users.append(user)
            sanitized[key_str] = sanitized_users
            continue

        # Special case: projected service account tokens
        if key_normalized in ("projectedserviceaccounttoken", "projectedserviceaccounttoken"):
            if isinstance(value, Mapping):
                sanitized[key_str], sub_findings = _sanitize_mapping(value, key_str, file_path)
                findings.extend(sub_findings)
                # Mark token projection but keep field names
                if "token" in sanitized[key_str]:
                    findings.append(Finding(
                        kind=FindingKind.WARNING,
                        message="projected serviceAccountToken token value redacted",
                        file=file_path,
                        context="projected serviceAccountToken",
                    ))
                    sanitized[key_str]["token"] = REDACTION_PLACEHOLDER
            else:
                sanitized[key_str] = value
            continue

        # Check if this field's value should be redacted
        if _should_redact_value_for_field(key_str):
            if isinstance(value, str):
                sanitized_value, sub_findings = _sanitize_string_value(value, key_str)
                sanitized[key_str] = sanitized_value
                findings.extend(sub_findings)
            elif isinstance(value, Mapping):
                # Complex structure - redact all string values
                sanitized[key_str] = {}
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, str):
                        findings.append(Finding(
                            kind=FindingKind.FATAL,
                            message=f"Credential data in {key_str}.{sub_key} redacted",
                            file=file_path,
                            context=f"{key_str}.{sub_key}",
                        ))
                        sanitized[key_str][sub_key] = REDACTION_PLACEHOLDER
                    else:
                        sanitized[key_str][sub_key] = sub_value
            else:
                sanitized[key_str] = REDACTION_PLACEHOLDER
                findings.append(Finding(
                    kind=FindingKind.WARNING,
                    message=f"Value for '{key_str}' redacted",
                    file=file_path,
                    context=key_str,
                ))
            continue

        # Safe Kubernetes field - keep value but check for embedded secrets
        if isinstance(value, str):
            sanitized_value, sub_findings = _sanitize_string_value(value, key_str)
            sanitized[key_str] = sanitized_value
            findings.extend(sub_findings)
        elif isinstance(value, Mapping):
            sanitized[key_str], sub_findings = _sanitize_mapping(value, key_str, file_path)
            findings.extend(sub_findings)
        elif isinstance(value, list):
            sanitized_list = []
            for item in value:
                if isinstance(item, str):
                    item_sanitized, sub_findings = _sanitize_string_value(item, key_str)
                    sanitized_list.append(item_sanitized)
                    findings.extend(sub_findings)
                elif isinstance(item, Mapping):
                    item_sanitized, sub_findings = _sanitize_mapping(item, key_str, file_path)
                    sanitized_list.append(item_sanitized)
                    findings.extend(sub_findings)
                else:
                    sanitized_list.append(item)
            sanitized[key_str] = sanitized_list
        else:
            sanitized[key_str] = value

    return sanitized, findings


def _sanitize_raw_text(content: str, file_path: str) -> tuple[str, list[Finding]]:
    """
    Sanitize raw text content (e.g., plain text files, kubectl output).
    Handles embedded JSON/YAML within the text.
    
    Returns (sanitized_content, findings).
    """
    findings = []
    sanitized = content

    # Check for fatal patterns in raw text
    for pattern in _FATAL_PATTERNS:
        if pattern.search(content):
            findings.append(Finding(
                kind=FindingKind.FATAL,
                message=f"Credential pattern found in raw text: {pattern.pattern[:50]}",
                file=file_path,
                context="raw text scan",
            ))
            # Replace the pattern
            sanitized = pattern.sub(REDACTION_PLACEHOLDER, sanitized)

    # Try to extract and sanitize embedded JSON
    json_matches = list(re.finditer(r'\{[^{}]*"[^{}]+\}[^{}]*\}', content))
    if json_matches:
        for match in reversed(json_matches):
            try:
                json_data = json.loads(match.group())
                sanitized_data, sub_findings = _sanitize_mapping(json_data, None, file_path)
                sanitized = sanitized[:match.start()] + json.dumps(sanitized_data) + sanitized[match.end():]
                for f in sub_findings:
                    f.file = file_path
                findings.extend(sub_findings)
            except (json.JSONDecodeError, TypeError):
                pass

    return sanitized, findings


def sanitize_file(input_path: Path, output_path: Path) -> SanitizationResult:
    """
    Sanitize a single file and write to output path.
    
    Returns a SanitizationResult with the sanitization outcome.
    """
    findings: list[Finding] = []
    
    try:
        content = input_path.read_text(errors="replace")
    except Exception as e:
        return SanitizationResult(
            input_path=input_path,
            output_path=output_path,
            success=False,
            findings=[],
            error=f"Could not read file: {e}",
        )

    file_path_str = str(input_path)
    suffix = input_path.suffix.lower()

    try:
        # Parse based on file type
        if suffix in (".json",):
            try:
                data = json.loads(content)
                sanitized_data, findings = _sanitize_mapping(data, None, file_path_str)
                output_content = json.dumps(sanitized_data, indent=2)
            except json.JSONDecodeError:
                # Not valid JSON, treat as raw text
                output_content, findings = _sanitize_raw_text(content, file_path_str)

        elif suffix in (".yaml", ".yml"):
            data = _yaml_safe_load(content)
            if data is not None:
                # _yaml_safe_load returns list of documents (multi-document support)
                if isinstance(data, list):
                    sanitized_items = []
                    for item in data:
                        if isinstance(item, Mapping):
                            item_sanitized, sub_findings = _sanitize_mapping(item, None, file_path_str)
                            sanitized_items.append(item_sanitized)
                            findings.extend(sub_findings)
                        else:
                            sanitized_items.append(item)
                    # Use safe_dump_all to preserve document separators
                    output_content = _yaml_safe_dump_all(sanitized_items)
                elif isinstance(data, Mapping):
                    sanitized_data, findings = _sanitize_mapping(data, None, file_path_str)
                    output_content = _yaml_safe_dump(sanitized_data)
                else:
                    output_content = content
            else:
                # Not valid YAML, treat as raw text
                output_content, findings = _sanitize_raw_text(content, file_path_str)

        else:
            # Plain text or unknown - treat as raw text
            output_content, findings = _sanitize_raw_text(content, file_path_str)

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write sanitized content
        output_path.write_text(output_content)
        
        return SanitizationResult(
            input_path=input_path,
            output_path=output_path,
            success=True,
            findings=findings,
        )

    except Exception as e:
        return SanitizationResult(
            input_path=input_path,
            output_path=output_path,
            success=False,
            findings=findings,
            error=f"Sanitization failed: {e}",
        )


def sanitize_directory(input_dir: Path, output_dir: Path) -> tuple[bool, list[Finding], list[SanitizationResult]]:
    """
    Sanitize all files in a directory tree.
    
    Returns (all_success, all_findings, results).
    """
    all_findings: list[Finding] = []
    results: list[SanitizationResult] = []
    all_success = True

    for input_path in input_dir.rglob("*"):
        if input_path.is_file():
            # Compute relative path
            rel_path = input_path.relative_to(input_dir)
            output_path = output_dir / rel_path

            result = sanitize_file(input_path, output_path)
            results.append(result)

            if not result.success:
                all_success = False

            # Update file paths in findings
            for finding in result.findings:
                if not finding.file:
                    finding.file = str(rel_path)
            all_findings.extend(result.findings)

    # Deduplicate findings
    seen: set[str] = set()
    unique_findings: list[Finding] = []
    for finding in all_findings:
        key = f"{finding.kind}:{finding.file}:{finding.message}:{finding.context}"
        if key not in seen:
            seen.add(key)
            unique_findings.append(finding)

    return all_success, unique_findings, results


def format_findings_summary(findings: list[Finding]) -> str:
    """Format findings into a human-readable summary."""
    if not findings:
        return "No findings."

    fatal = [f for f in findings if f.kind == FindingKind.FATAL]
    warnings = [f for f in findings if f.kind == FindingKind.WARNING]
    info = [f for f in findings if f.kind == FindingKind.INFO]

    lines = []
    if fatal:
        lines.append(f"FATAL ({len(fatal)}):")
        for f in fatal[:5]:  # Limit output
            lines.append(f"  - {f.message} in {f.file}")
        if len(fatal) > 5:
            lines.append(f"  ... and {len(fatal) - 5} more")

    if warnings:
        lines.append(f"Warnings ({len(warnings)}):")
        for f in warnings[:5]:
            lines.append(f"  - {f.message} in {f.file}")
        if len(warnings) > 5:
            lines.append(f"  ... and {len(warnings) - 5} more")

    if info:
        lines.append(f"Info ({len(info)}):")
        for f in info[:3]:
            lines.append(f"  - {f.message} in {f.file}")

    return "\n".join(lines)


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sanitize live lab artifacts for safe verification and upload.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Sanitize a live lab artifact directory
    python scripts/sanitize_live_lab_artifacts.py --input ./lab-artifacts/live --output ./lab-artifacts/live-sanitized

    # With verbose output
    python scripts/sanitize_live_lab_artifacts.py --input ./lab-artifacts/live --output ./lab-artifacts/live-sanitized --verbose

    # Dry run - show what would be sanitized
    python scripts/sanitize_live_lab_artifacts.py --input ./lab-artifacts/live --output ./lab-artifacts/live-sanitized --dry-run
        """,
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input artifact directory to sanitize",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output directory for sanitized artifacts",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be sanitized without writing files",
    )

    args = parser.parse_args()

    # Validate input
    if not args.input.exists():
        print(f"ERROR: Input directory does not exist: {args.input}", file=sys.stderr)
        return 2

    if not args.input.is_dir():
        print(f"ERROR: Input path is not a directory: {args.input}", file=sys.stderr)
        return 2

    # Dry run mode
    if args.dry_run:
        print(f"DRY RUN: Would sanitize {args.input} -> {args.output}")
        for input_path in args.input.rglob("*"):
            if input_path.is_file():
                rel_path = input_path.relative_to(args.input)
                print(f"  - {rel_path}")
        return 0

    # Sanitize
    print(f"Sanitizing artifacts: {args.input}")
    print(f"Output directory: {args.output}")
    print()

    success, findings, results = sanitize_directory(args.input, args.output)

    # Print verbose output
    if args.verbose:
        print("Sanitization results:")
        for result in results:
            status = "✓" if result.success else "✗"
            print(f"  {status} {result.input_path.relative_to(args.input)}")
            if result.error:
                print(f"    Error: {result.error}")

    # Print findings summary
    print()
    print("Findings:")
    print(format_findings_summary(findings))

    # Summary
    print()
    total = len(results)
    succeeded = sum(1 for r in results if r.success)
    fatal_count = sum(1 for f in findings if f.kind == FindingKind.FATAL)

    print(f"Summary: {succeeded}/{total} files sanitized")
    print(f"Findings: {len(findings)} ({len([f for f in findings if f.kind == FindingKind.FATAL])} fatal, "
          f"{len([f for f in findings if f.kind == FindingKind.WARNING])} warnings, "
          f"{len([f for f in findings if f.kind == FindingKind.INFO])} info)")

    # Write findings to JSON for downstream consumption
    findings_path = args.output / "_findings.json"
    findings_path.parent.mkdir(parents=True, exist_ok=True)
    findings_data = {
        "success": success,
        "total_files": total,
        "succeeded": succeeded,
        "fatal_count": fatal_count,
        "findings": [
            {
                "kind": f.kind,
                "message": f.message,
                "file": f.file,
                "context": f.context,
            }
            for f in findings
        ],
    }
    findings_path.write_text(json.dumps(findings_data, indent=2))
    print(f"\nFindings written to: {findings_path}")

    if fatal_count > 0:
        print("\nFATAL: Actual credential values detected in artifacts!")
        return 1

    if not success:
        return 1

    # Fail on warnings (Secret.data, stringData, etc. need manual review)
    warning_count = sum(1 for f in findings if f.kind == FindingKind.WARNING)
    if warning_count > 0:
        print("\nWARNING: Sensitive fields detected and redacted.")
        return 1

    print("\nSanitization complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
