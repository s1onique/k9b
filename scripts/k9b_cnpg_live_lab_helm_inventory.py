#!/usr/bin/env python3
"""Helm rendered manifest inventory parser for CNPG Live Lab.

This module parses Helm-rendered YAML manifests and builds a workload inventory
focused on workload identity (Deployment, StatefulSet, DaemonSet, Job, CronJob, Pod, ReplicaSet).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

# Workload kinds to track
WORKLOAD_KINDS = frozenset([
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "Job",
    "CronJob",
    "Pod",
    "ReplicaSet",
])


def parse_workload_inventory(
    rendered_yaml: str,
    expected_name: str = "k9b",
    expected_namespace: str = "",
) -> dict[str, Any]:
    """Parse Helm-rendered YAML into a workload inventory.

    Args:
        rendered_yaml: Raw YAML content from helm template/render output
        expected_name: Expected workload name to look for (default: "k9b")
        expected_namespace: Expected namespace for the workload (default: "")

    Returns:
        Dictionary with:
        - expected: expected workload spec (kind, name, namespace)
        - rendered: rendered inventory results
          - deployment_k9b_present: bool
          - matching_workloads: list of matching workload manifests
          - all_workloads: list of all workloads found
        - parse_errors: list of errors encountered
    """
    result: dict[str, Any] = {
        "expected": {
            "kind": "Deployment",
            "name": expected_name,
            "namespace": expected_namespace,
        },
        "rendered": {
            "deployment_k9b_present": False,
            "matching_workloads": [],
            "all_workloads": [],
        },
        "parse_errors": [],
    }

    if not rendered_yaml or not rendered_yaml.strip():
        result["parse_errors"].append("Empty or whitespace-only YAML content")
        return result

    try:
        # Split multi-document YAML
        docs = list(yaml.safe_load_all(rendered_yaml))

        for doc in docs:
            # Skip non-dict documents (comments, empty docs, etc.)
            if not isinstance(doc, dict):
                continue

            kind = doc.get("kind", "")
            if kind not in WORKLOAD_KINDS:
                continue

            metadata = doc.get("metadata", {})
            name = metadata.get("name", "")
            namespace = metadata.get("namespace", "")

            workload_entry = {
                "apiVersion": doc.get("apiVersion", ""),
                "kind": kind,
                "metadata": {
                    "name": name,
                    "namespace": namespace,
                },
            }

            # Add to all workloads
            result["rendered"]["all_workloads"].append(workload_entry)

            # Check if this is the expected k9b Deployment
            if kind == "Deployment" and name == expected_name:
                result["rendered"]["deployment_k9b_present"] = True
                result["rendered"]["matching_workloads"].append(workload_entry)

    except yaml.YAMLError as e:
        result["parse_errors"].append(f"YAML parse error: {e}")
    except Exception as e:
        result["parse_errors"].append(f"Unexpected error: {e}")

    return result


def parse_workload_inventory_from_file(
    file_path: Path,
    expected_name: str = "k9b",
    expected_namespace: str = "",
) -> dict[str, Any]:
    """Parse Helm-rendered YAML from a file into a workload inventory.

    Args:
        file_path: Path to YAML file
        expected_name: Expected workload name to look for (default: "k9b")
        expected_namespace: Expected namespace for the workload (default: "")

    Returns:
        Dictionary with workload inventory (same as parse_workload_inventory)
    """
    if not file_path.exists():
        return {
            "expected": {
                "kind": "Deployment",
                "name": expected_name,
                "namespace": expected_namespace,
            },
            "rendered": {
                "deployment_k9b_present": False,
                "matching_workloads": [],
                "all_workloads": [],
            },
            "parse_errors": [f"File not found: {file_path}"],
        }

    try:
        content = file_path.read_text(encoding="utf-8")
        return parse_workload_inventory(content, expected_name, expected_namespace)
    except Exception as e:
        return {
            "expected": {
                "kind": "Deployment",
                "name": expected_name,
                "namespace": expected_namespace,
            },
            "rendered": {
                "deployment_k9b_present": False,
                "matching_workloads": [],
                "all_workloads": [],
            },
            "parse_errors": [f"Failed to read file: {e}"],
        }


def write_workload_inventory(
    artifact_dir: Path,
    inventory: dict[str, Any],
) -> Path:
    """Write workload inventory to JSON file.

    Args:
        artifact_dir: Directory to write the inventory file
        inventory: Workload inventory dictionary

    Returns:
        Path to the written file
    """
    helm_dir = artifact_dir / "helm"
    helm_dir.mkdir(parents=True, exist_ok=True)
    output_path = helm_dir / "rendered-workload-inventory.json"
    output_path.write_text(
        json.dumps(inventory, indent=2),
        encoding="utf-8",
    )
    return output_path


def check_chart_values_suppression(
    values_json: str | None = None,
    rendered_yaml: str | None = None,
) -> tuple[bool, str]:
    """Check if chart values explicitly suppress the k9b workload.

    This function looks for explicit evidence that the k9b backend/deployment
    is intentionally disabled via chart values or conditional templates.

    Args:
        values_json: Helm values as JSON string (optional)
        rendered_yaml: Rendered YAML manifest (optional)

    Returns:
        Tuple of (is_suppressed, reason)
    """
    if values_json:
        try:
            values = json.loads(values_json)
            # Check for explicit disable flags
            if values.get("k9b", {}).get("enabled", True) is False:
                return True, "k9b.enabled=false in values"
            if values.get("backend", {}).get("enabled", True) is False:
                return True, "backend.enabled=false in values"
            if values.get("backend", {}).get("replicas", 0) == 0:
                return True, "backend.replicas=0 in values"
        except json.JSONDecodeError:
            pass

    if rendered_yaml:
        # Check for conditional template that disables k9b
        yaml_lower = rendered_yaml.lower()
        if "k9b" in yaml_lower and "enabled: false" in yaml_lower:
            return True, "k9b enabled:false found in rendered manifest"

    return False, ""


def check_rbac_admission_rejection(helm_output: str, helm_stderr: str = "") -> tuple[bool, str]:
    """Check Helm output for RBAC/admission rejection evidence.

    Args:
        helm_output: Helm install/upgrade stdout
        helm_stderr: Helm install/upgrade stderr

    Returns:
        Tuple of (has_rejection, reason)
    """
    import re
    combined = (helm_output + "\n" + helm_stderr).lower()

    rejection_patterns = [
        (r"forbidden", "RBAC/forbidden: access denied"),
        (r"is forbidden", "RBAC/forbidden: resource access denied"),
        (r"cannot get resource", "RBAC: missing get permission"),
        (r"admission.*denied", "Admission webhook denied"),
        (r"webhook.*rejected", "Admission webhook rejected"),
        (r"validation.*failed", "OpenAPI validation failed"),
        (r"immutable.*field", "Immutable field conflict"),
        (r"ownership.*conflict", "Ownership/annotation conflict"),
        (r"namespace.*not found", "Namespace not found"),
        (r"resource.*quota.*exceeded", "Resource quota exceeded"),
    ]

    for pattern, reason in rejection_patterns:
        if re.search(pattern, combined):
            return True, reason

    return False, ""
