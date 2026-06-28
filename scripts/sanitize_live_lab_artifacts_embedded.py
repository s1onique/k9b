"""Embedded Kubernetes manifest sanitization.

This module handles sanitization of Kubernetes manifests embedded as YAML strings
within JSON fields (e.g., helm/status.json with info.manifest containing YAML).
"""

from __future__ import annotations

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


def _sanitize_embedded_manifest_string(
    value: str,
    *,
    field_key: str | None = None,
    file_path: str,
) -> tuple[str, list[Finding]]:
    """Sanitize embedded Kubernetes manifests inside string values."""
    if "kind:" not in value and '"kind"' not in value:
        return value, []

    try:
        docs = list(yaml.safe_load_all(value))
    except yaml.YAMLError:
        return value, []

    if not docs or not any(isinstance(doc, Mapping) for doc in docs):
        return value, []

    sanitized_docs: list[Any] = []
    findings: list[Finding] = []
    changed = False

    for doc in docs:
        if isinstance(doc, Mapping) and str(doc.get("kind", "")).lower() == "secret":
            sanitized_doc, secret_findings = _sanitize_secret_object(doc, file_path)
            sanitized_docs.append(sanitized_doc)
            findings.extend(secret_findings)
            changed = True
        else:
            sanitized_docs.append(doc)

    if not changed:
        return value, []

    return yaml.safe_dump_all(sanitized_docs, sort_keys=False, allow_unicode=True), findings
