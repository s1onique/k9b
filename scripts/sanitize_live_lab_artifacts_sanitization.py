"""Sanitization logic for sanitize_live_lab_artifacts.

This module contains the core sanitization functions for parsing and
redacting sensitive data from JSON/YAML artifacts.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from sanitize_live_lab_artifacts_contract import (
    _FATAL_PATTERNS,
    _NON_SECRET_AUTH_PATH_SUFFIXES,
    _NON_SECRET_AUTH_PATHS,
    _SAFE_BOOLEAN_PATTERNS,
    _SAFE_K8S_FIELDS,
    _SENSITIVE_VALUE_FIELDS,
    REDACTION_PLACEHOLDER,
    Finding,
    FindingKind,
    SanitizationResult,
)


def _is_safe_k8s_field(key: str) -> bool:
    normalized = key.lower().replace("-", "").replace("_", "")
    return normalized in _SAFE_K8S_FIELDS or normalized in _SAFE_BOOLEAN_PATTERNS


def _should_redact_value_for_field(key: str) -> bool:
    normalized = key.lower().replace("-", "").replace("_", "")
    return normalized in _SENSITIVE_VALUE_FIELDS


def _check_for_fatal_patterns(value: str) -> list[str]:
    return [p.pattern[:50] + "..." if len(p.pattern) > 50 else p.pattern
            for p in _FATAL_PATTERNS if p.search(value)]


def _sanitize_string_value(value: str, field_key: str | None = None) -> tuple[str, list[Finding]]:
    if not isinstance(value, str):
        return value, []
    findings = []
    for match in _check_for_fatal_patterns(value):
        findings.append(Finding(kind=FindingKind.FATAL,
            message=f"Found credential pattern: {match}", file="", context=field_key))
    if findings:
        return REDACTION_PLACEHOLDER, findings
    return value, findings


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


def _sanitize_value(
    value: Any,
    parent_key: str | None = None,
    file_path: str = "",
) -> tuple[Any, list[Finding]]:
    """
    Type-dispatched sanitization entry point.
    
    Handles any JSON/YAML value type:
    - dict/Mapping -> _sanitize_mapping
    - list -> _sanitize_sequence
    - str -> _sanitize_string_value
    
    Returns (sanitized_value, findings).
    """
    if isinstance(value, Mapping):
        return _sanitize_mapping(value, parent_key, file_path)
    if isinstance(value, list):
        return _sanitize_sequence(value, parent_key, file_path)
    if isinstance(value, str):
        return _sanitize_string_value(value, parent_key)
    return value, []


def _sanitize_sequence(
    values: list[Any],
    parent_key: str | None = None,
    file_path: str = "",
) -> tuple[list[Any], list[Finding]]:
    """
    Sanitize a sequence (list), handling arrays at any level including top-level.
    
    This enables handling of JSON/YAML files whose root is an array,
    such as top-level arrays of incident objects or symptom snapshots.
    
    Returns (sanitized_list, findings).
    """
    sanitized: list[Any] = []
    findings: list[Finding] = []

    for index, item in enumerate(values):
        index_key = f"{parent_key}[{index}]" if parent_key else f"[{index}]"
        sanitized_item, item_findings = _sanitize_value(item, index_key, file_path)
        sanitized.append(sanitized_item)
        findings.extend(item_findings)

    return sanitized, findings


def _is_non_secret_auth_path(current_path: str) -> bool:
    """Check if path is a known non-secret auth configuration."""
    if current_path in _NON_SECRET_AUTH_PATHS:
        return True
    for suffix in _NON_SECRET_AUTH_PATH_SUFFIXES:
        if current_path.endswith(suffix):
            return True
    return False


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
            # Build the current path for allowlist check
            current_path = key_str if parent_key is None else f"{parent_key}.{key_str}"
            
            # Not a sensitive field - process normally
            if isinstance(value, str):
                sanitized_value, sub_findings = _sanitize_string_value(value, key_str)
                sanitized[key_str] = sanitized_value
                findings.extend(sub_findings)
            elif isinstance(value, Mapping):
                # Complex structure under sensitive field - need to check each child against allowlist
                sanitized[key_str] = {}
                for sub_key, sub_value in value.items():
                    sub_path = f"{current_path}.{sub_key}"
                    # Check if this specific path is in the allowlist
                    if _is_non_secret_auth_path(sub_path):
                        # Allowlist match: keep the value, but still check for embedded patterns
                        if isinstance(sub_value, str):
                            sanitized_value, sub_findings = _sanitize_string_value(sub_value, sub_key)
                            sanitized[key_str][sub_key] = sanitized_value
                            findings.extend(sub_findings)
                        elif isinstance(sub_value, Mapping):
                            # Recursively sanitize nested objects
                            sanitized[key_str][sub_key], sub_findings = _sanitize_mapping(sub_value, sub_path, file_path)
                            findings.extend(sub_findings)
                        elif isinstance(sub_value, list):
                            sanitized[key_str][sub_key], sub_findings = _sanitize_sequence(sub_value, sub_path, file_path)
                            findings.extend(sub_findings)
                        else:
                            sanitized[key_str][sub_key] = sub_value
                    elif isinstance(sub_value, str):
                        # Not in allowlist - redact string values
                        findings.append(Finding(
                            kind=FindingKind.FATAL,
                            message=f"Credential data in {current_path}.{sub_key} redacted",
                            file=file_path,
                            context=sub_path,
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
            sanitized[key_str], sub_findings = _sanitize_sequence(value, key_str, file_path)
            findings.extend(sub_findings)
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
                # Use _sanitize_value for JSON: handles both dict (mapping) and list (array) roots
                sanitized_data, findings = _sanitize_value(data, None, file_path_str)
                output_content = json.dumps(sanitized_data, indent=2)
            except json.JSONDecodeError:
                # Not valid JSON, treat as raw text
                output_content, findings = _sanitize_raw_text(content, file_path_str)

        elif suffix in (".yaml", ".yml"):
            try:
                data = list(yaml.safe_load_all(content))
                if data:
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
                        output_content = yaml.safe_dump_all(sanitized_items, default_flow_style=False, sort_keys=False, allow_unicode=True)
                    elif isinstance(data, Mapping):
                        sanitized_data, findings = _sanitize_mapping(data, None, file_path_str)
                        output_content = yaml.safe_dump(sanitized_data, default_flow_style=False, sort_keys=False, allow_unicode=True)
                    else:
                        output_content = content
                else:
                    output_content = content
            except yaml.YAMLError:
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
