"""Embedded Kubernetes manifest sanitization.

This module handles sanitization of Kubernetes manifests embedded as YAML strings
within JSON fields (e.g., helm/status.json with info.manifest containing YAML).

The sanitizer recursively walks through all parsed YAML/JSON nodes to detect and
sanitize Secret objects at any nesting level, including:
- Top-level Secret manifests
- Secret objects inside List.items
- Secret objects inside arbitrary arrays (e.g., resources arrays in Helm status)
- Nested Secret objects in any structure
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import yaml
from sanitize_live_lab_artifacts_contract import Finding, FindingKind


def _sanitize_secret_object(
    data: Mapping[str, Any], file_path: str
) -> tuple[dict[str, Any], list[Finding]]:
    """Object-level sanitization for Kubernetes Secret manifests."""
    findings: list[Finding] = []
    sanitized: dict[str, Any] = {}

    if "metadata" in data:
        sanitized["metadata"] = dict(data["metadata"])
    if "kind" in data:
        sanitized["kind"] = data["kind"]
    if "apiVersion" in data:
        sanitized["apiVersion"] = data["apiVersion"]
    if "type" in data:
        sanitized["type"] = data["type"]

    sanitized["_sanitized"] = "secret"

    if "data" in data:
        sanitized["data"] = {"<redacted>": "contains base64-encoded secret values"}
        findings.append(Finding(
            kind=FindingKind.WARNING,
            message="Secret.data field redacted (contains sensitive values)",
            file=file_path,
            context="Secret.data",
        ))

    if "stringData" in data:
        sanitized["stringData"] = {"<redacted>": "contains plaintext secret values"}
        findings.append(Finding(
            kind=FindingKind.WARNING,
            message="Secret.stringData field redacted (contains sensitive values)",
            file=file_path,
            context="Secret.stringData",
        ))

    if "binaryData" in data:
        sanitized["binaryData"] = {"<redacted>": "contains binary secret values"}
        findings.append(Finding(
            kind=FindingKind.WARNING,
            message="Secret.binaryData field redacted (contains sensitive values)",
            file=file_path,
            context="Secret.binaryData",
        ))

    return sanitized, findings


def _sanitize_manifest_node(
    node: Any,
    file_path: str,
) -> tuple[Any, list[Finding], bool]:
    """Recursively walk and sanitize Secret objects at any nesting level.

    This function recursively traverses all nodes in a parsed YAML/JSON document
    and sanitizes any Secret objects found, regardless of their nesting depth.

    Args:
        node: The current node (dict, list, or scalar) being visited
        file_path: Path to the source file for finding context

    Returns:
        A tuple of (sanitized_node, findings, changed) where:
        - sanitized_node: The sanitized version of the input node
        - findings: List of all findings discovered during sanitization
        - changed: True if any sanitization was performed
    """
    if isinstance(node, Mapping):
        # Check if this mapping is a Secret manifest
        kind = str(node.get("kind", "")).lower()
        if kind == "secret":
            sanitized, secret_findings = _sanitize_secret_object(node, file_path)
            return sanitized, secret_findings, True

        # Not a Secret - recursively process all children
        changed = False
        findings: list[Finding] = []
        result: dict[str, Any] = {}

        for key, value in node.items():
            sanitized_value, sub_findings, sub_changed = _sanitize_manifest_node(value, file_path)
            result[str(key)] = sanitized_value
            findings.extend(sub_findings)
            changed = changed or sub_changed

        return result, findings, changed

    if isinstance(node, list):
        # Process each item in the list
        changed = False
        list_findings: list[Finding] = []
        list_result: list[Any] = []

        for item in node:
            sanitized_item, sub_findings, sub_changed = _sanitize_manifest_node(item, file_path)
            list_result.append(sanitized_item)
            list_findings.extend(sub_findings)
            changed = changed or sub_changed

        return list_result, list_findings, changed

    # Scalar value (str, int, float, bool, None) - no sanitization needed
    return node, [], False


def _sanitize_embedded_manifest_string(
    value: str,
    *,
    field_key: str | None = None,
    file_path: str,
) -> tuple[str, list[Finding]]:
    """Sanitize embedded Kubernetes manifests inside string values.

    This function handles YAML manifests embedded as strings in JSON fields
    (e.g., Helm status info.manifest containing release manifests).

    The sanitization is recursive and will find Secret objects at any nesting
    level, including:
    - Top-level documents
    - Objects inside List.items
    - Objects inside arbitrary arrays (resources, etc.)
    - Nested structures

    Args:
        value: The string containing YAML manifests
        field_key: Optional key name for context in findings
        file_path: Path to the source file for finding context

    Returns:
        A tuple of (sanitized_value, findings) where:
        - sanitized_value: The sanitized string (YAML dump of sanitized docs)
        - findings: List of all findings discovered during sanitization
    """
    # Quick check: only process if it looks like YAML with kind declarations
    if "kind:" not in value and '"kind"' not in value:
        return value, []

    # Try YAML first
    try:
        docs = list(yaml.safe_load_all(value))
        # Accept both mappings and lists as valid YAML document types
        if docs and (any(isinstance(doc, Mapping) for doc in docs) or any(isinstance(doc, list) for doc in docs)):
            sanitized_docs: list[Any] = []
            all_findings: list[Finding] = []
            changed = False

            for doc in docs:
                # Process all docs through the recursive walker (handles Mapping, list, or scalar)
                sanitized_doc, findings, doc_changed = _sanitize_manifest_node(doc, file_path)
                sanitized_docs.append(sanitized_doc)
                all_findings.extend(findings)
                changed = changed or doc_changed

            if changed:
                return yaml.safe_dump_all(sanitized_docs, sort_keys=False, allow_unicode=True), all_findings
            return value, []

    except yaml.YAMLError:
        pass

    # Try JSON (some Helm outputs may be JSON-formatted)
    try:
        json_data = json.loads(value)
        if isinstance(json_data, Mapping):
            sanitized_json, json_findings, json_changed = _sanitize_manifest_node(json_data, file_path)
            if json_changed:
                return json.dumps(sanitized_json, indent=2, ensure_ascii=False), json_findings
        elif isinstance(json_data, list):
            sanitized_json, json_findings, json_changed = _sanitize_manifest_node(json_data, file_path)
            if json_changed:
                return json.dumps(sanitized_json, indent=2, ensure_ascii=False), json_findings
    except json.JSONDecodeError:
        pass

    return value, []
