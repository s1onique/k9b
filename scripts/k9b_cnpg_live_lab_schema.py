#!/usr/bin/env python3
"""Schema validation and evidence extraction for CNPG Live Lab bootstrap.

This module contains functions for extracting bounded schema validation
evidence from Helm dry-run and template outputs.
"""

from __future__ import annotations

import re
from pathlib import Path

from .k9b_cnpg_live_lab_constants import (
    FAILURE_HELM_MANIFEST_SCHEMA_WARNING,
    SCHEMA_VALIDATION_PATTERNS,
    VALID_RESOURCE_NAME_PATTERN,
)
from .k9b_cnpg_live_lab_helpers import write_json_atomically

# =============================================================================
# YAML parsing helpers
# =============================================================================

def _parse_rendered_yaml_for_resource(
    rendered_content: str,
    field_path: str,
) -> tuple[str, str, str]:
    """Parse rendered YAML to find the resource containing a field path.

    Args:
        rendered_content: The rendered YAML content
        field_path: The field path to search for (e.g., "spec.template.spec.containers[0].allowPrivilegeEscalation")

    Returns:
        Tuple of (kind, name, namespace) for the resource containing the field
    """
    # Split into YAML documents
    documents = rendered_content.split("---")

    for doc in documents:
        lines = doc.strip().split("\n")
        if not lines:
            continue

        # Find kind and name in this document
        kind = ""
        name = ""
        namespace = ""

        for line in lines:
            kind_match = re.match(r'\s*kind:\s*(\w+)', line)
            if kind_match:
                kind = kind_match.group(1)
            name_match = re.match(r'\s*name:\s*([a-zA-Z0-9][-a-zA-Z0-9_]*)', line)
            if name_match:
                name = name_match.group(1)
            namespace_match = re.match(r'\s*namespace:\s*([a-zA-Z0-9][-a-zA-Z0-9_]*)', line)
            if namespace_match:
                namespace = namespace_match.group(1)

        # Check if this document contains the field path
        # For container fields, check if the document has containers section
        if kind and name:
            doc_content = doc.lower()
            # Check for indicators that this document has the problematic field
            if "containers" in field_path.lower():
                # For container-level fields, check if document has containers section
                if "containers" in doc_content:
                    return kind, name, namespace
            else:
                # For non-container fields, any matching document works
                return kind, name, namespace

    return "", "", ""


# =============================================================================
# Schema warning extraction
# =============================================================================

def extract_schema_warnings(
    log_content: str,
    rendered_content: str = "",
) -> list[dict]:
    """Extract bounded schema warnings from log content.

    Parses log output for schema validation errors and extracts:
    - line number
    - message text
    - unknown field path if present
    - resource kind/name if inferable from rendered YAML
    - source file/log name

    Args:
        log_content: Content of the helm dry-run or template log
        rendered_content: Optional rendered YAML content for accurate resource mapping

    Returns:
        List of warning dictionaries with bounded evidence
    """
    warnings: list[dict] = []
    lines = log_content.split("\n")

    for i, line in enumerate(lines, start=1):
        line_lower = line.lower()

        # Check if line matches any schema validation pattern
        matched_pattern = None
        for pattern in SCHEMA_VALIDATION_PATTERNS:
            # Use IGNORECASE to handle case-insensitive matching
            if re.search(pattern, line_lower, re.IGNORECASE):
                matched_pattern = pattern
                break

        if matched_pattern is None:
            continue

        # Extract field path from "unknown field" messages
        field_path = ""
        field_match = re.search(r'unknown field "([^"]+)"', line)
        if field_match:
            field_path = field_match.group(1)

        # Extract resource kind and name
        kind = ""
        name = ""

        # Priority 1: Use rendered YAML to find the actual resource
        if rendered_content and field_path:
            kind, name, _ = _parse_rendered_yaml_for_resource(rendered_content, field_path)

        # Priority 2: Try to extract from error message format: "error from <kind>/<name>"
        # Only accept if the name matches valid resource name pattern (not "in", "version", etc.)
        if not kind or not name:
            resource_match = re.search(
                rf'(Deployment|StatefulSet|DaemonSet|Job|CronJob|Service|ConfigMap|Secret)/({VALID_RESOURCE_NAME_PATTERN})',
                line
            )
            if resource_match:
                kind = resource_match.group(1)
                name = resource_match.group(2)
                # Additional validation: name must not be a common word
                if name.lower() in ("in", "version", "the", "a", "an", "for", "with"):
                    name = ""  # Reject bogus names

        warning: dict[str, str | int] = {
            "line": i,
            "message": line.strip(),
            "pattern_matched": matched_pattern,
        }

        if field_path:
            warning["field"] = field_path
        if kind:
            warning["kind"] = kind
        if name:
            warning["name"] = name

        warnings.append(warning)

    return warnings


def write_schema_warnings_json(
    artifact_dir: Path,
    warnings: list[dict],
    source_log: str,
    failure_class: str,
) -> Path:
    """Write schema warnings to JSON file atomically.

    Args:
        artifact_dir: Directory to write the JSON file
        warnings: List of warning dictionaries
        source_log: Name of the source log file
        failure_class: The failure class being reported

    Returns:
        Path to the written JSON file
    """
    data = {
        "failure_class": failure_class,
        "source_log": source_log,
        "match_count": len(warnings),
        "matches": warnings,
    }

    output_path = artifact_dir / "logs" / "schema-warnings.json"
    write_json_atomically(output_path, data)
    return output_path


def generate_bounded_summary(warnings: list[dict], max_lines: int = 20) -> str:
    """Generate bounded sanitized summary of schema warnings.

    Args:
        warnings: List of warning dictionaries
        max_lines: Maximum number of warnings to include

    Returns:
        Sanitized summary string suitable for GitHub Actions output
    """
    if not warnings:
        return "No schema warnings detected."

    lines = ["Schema validation failed before Helm install.", ""]
    lines.append(f"Failure class: {FAILURE_HELM_MANIFEST_SCHEMA_WARNING}")
    lines.append("")
    lines.append("Matched warnings:")

    # Bounded output - limit to max_lines
    for warning in warnings[:max_lines]:
        parts = []
        if "field" in warning:
            parts.append(f'unknown field "{warning["field"]}"')
        elif "message" in warning:
            # Truncate long messages
            msg = warning["message"]
            if len(msg) > 120:
                msg = msg[:117] + "..."
            parts.append(msg)

        if "kind" in warning and "name" in warning:
            parts.append(f"({warning['kind']}/{warning['name']})")

        if parts:
            lines.append(f"- {' '.join(parts)}")

    # Indicate truncation if needed
    if len(warnings) > max_lines:
        lines.append(f"... and {len(warnings) - max_lines} more warnings")

    lines.append("")
    lines.append("Evidence:")
    lines.append("- logs/helm-server-dry-run.log")
    lines.append("- logs/helm-rendered.yaml")
    lines.append("- logs/schema-warnings.json")

    return "\n".join(lines)
