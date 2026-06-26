#!/usr/bin/env python3
"""Workload missing classifier with sub-classifications for CNPG Live Lab.

This module determines the specific cause when Deployment/k9b is not found
in the cluster after a Helm install/upgrade.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.k9b_cnpg_live_lab_constants import (
    FAILURE_ADMISSION_OR_RBAC_REJECTED,
    FAILURE_CHART_VALUES_SUPPRESSED,
    FAILURE_EVIDENCE_COLLECTION_FAILED,
    FAILURE_EXPECTED_WORKLOAD_MISSING,
    FAILURE_HELM_RELEASE_FAILED_BEFORE_WORKLOAD,
    FAILURE_HELM_RELEASE_MISSING,
    FAILURE_WORKLOAD_RENDERED_BUT_CLUSTER_MISSING,
    FAILURE_WORKLOAD_RENDERED_MISSING_DEPLOYMENT,
)
from scripts.k9b_cnpg_live_lab_helm_evidence import check_helm_release_failed
from scripts.k9b_cnpg_live_lab_helm_inventory import (
    check_chart_values_suppression,
    check_rbac_admission_rejection,
    parse_workload_inventory,
    write_workload_inventory,
)


def classify_expected_workload_missing(
    artifact_dir: Path,
    namespace: str,
    deployments_json: str,
    helm_install_stdout: str = "",
    helm_install_stderr: str = "",
    helm_status_json: str = "",
    helm_history_json: str = "",
    helm_values_json: str = "",
    rendered_manifest_yaml: str = "",
) -> tuple[str, dict[str, Any]]:
    """Classify expected_workload_missing into specific sub-causes.

    This function examines evidence from multiple sources to determine
    why Deployment/k9b was not observed in the cluster.

    Args:
        artifact_dir: Directory for artifacts
        namespace: Kubernetes namespace
        deployments_json: JSON from kubectl get deployments -o json
        helm_install_stdout: Helm install/upgrade stdout
        helm_install_stderr: Helm install/upgrade stderr
        helm_status_json: Helm status -o json output
        helm_history_json: Helm history -o json output
        helm_values_json: Helm get values -o json output
        rendered_manifest_yaml: Rendered manifest YAML

    Returns:
        Tuple of (failure_subclass, diagnostics_dict)
    """
    diagnostics: dict[str, Any] = {
        "expected_workload": {
            "kind": "Deployment",
            "name": "k9b",
            "namespace": namespace,
        },
        "rendered_manifest_captured": bool(rendered_manifest_yaml),
        "rendered_deployment_present": False,
        "cluster_deployment_present": _is_deployment_in_cluster(deployments_json, "k9b"),
        "helm_release_status_captured": bool(helm_status_json),
        "helm_release_status": None,
        "helm_history_captured": bool(helm_history_json),
        "helm_history": [],
        "install_exit_code": None,
        "evidence_artifacts": [],
    }

    # Parse Helm status
    helm_release_exists = False
    helm_status = None
    if helm_status_json:
        try:
            status_data = json.loads(helm_status_json)
            helm_release_exists = True
            helm_status = status_data.get("info", {}).get("status", {}).get("status")
            diagnostics["helm_release_status"] = helm_status
        except json.JSONDecodeError:
            pass

    # Parse Helm history
    helm_history = []
    if helm_history_json:
        try:
            helm_history = json.loads(helm_history_json)
            diagnostics["helm_history"] = helm_history
        except json.JSONDecodeError:
            pass

    # Check for RBAC/admission rejection in Helm output
    has_rbac_rejection, rbac_reason = check_rbac_admission_rejection(
        helm_install_stdout, helm_install_stderr
    )
    if has_rbac_rejection:
        diagnostics["rbac_admission_rejection"] = True
        diagnostics["rbac_admission_reason"] = rbac_reason
        return FAILURE_ADMISSION_OR_RBAC_REJECTED, diagnostics

    # Check for chart values suppression
    is_suppressed, suppression_reason = check_chart_values_suppression(
        helm_values_json, rendered_manifest_yaml
    )
    if is_suppressed:
        diagnostics["chart_values_suppressed"] = True
        diagnostics["chart_values_suppression_reason"] = suppression_reason
        return FAILURE_CHART_VALUES_SUPPRESSED, diagnostics

    # Parse rendered manifest if available
    rendered_deployment_present = False
    rendered_inventory = None
    if rendered_manifest_yaml:
        rendered_inventory = parse_workload_inventory(
            rendered_manifest_yaml,
            expected_name="k9b",
            expected_namespace=namespace,
        )
        rendered_deployment_present = rendered_inventory.get("rendered", {}).get(
            "deployment_k9b_present", False
        )
        diagnostics["rendered_deployment_present"] = rendered_deployment_present

        # Check if parsing failed (parse_errors indicate evidence collection failure)
        parse_errors = rendered_inventory.get("parse_errors", [])
        if parse_errors:
            diagnostics["parse_errors"] = parse_errors
            return FAILURE_EVIDENCE_COLLECTION_FAILED, diagnostics

        # Write inventory to artifact
        if rendered_inventory:
            inventory_path = write_workload_inventory(artifact_dir, rendered_inventory)
            diagnostics["evidence_artifacts"].append(inventory_path.name)

    # Check for Helm release failure
    is_release_failed, failed_reason = check_helm_release_failed(helm_history)
    if is_release_failed:
        diagnostics["helm_release_failed"] = True
        diagnostics["helm_release_failed_reason"] = failed_reason
        return FAILURE_HELM_RELEASE_FAILED_BEFORE_WORKLOAD, diagnostics

    # Determine specific sub-classification based on evidence
    cluster_deployment_present = diagnostics["cluster_deployment_present"]

    # Check if rendered manifest artifact exists (even if empty) vs never captured
    # The artifact exists if the file was written, even if empty
    # The artifact is missing only if we never attempted to render
    if not rendered_manifest_yaml:
        # No rendered manifest at all - this is evidence collection failure
        diagnostics["render_analysis"] = "No rendered manifest captured"
        return FAILURE_EVIDENCE_COLLECTION_FAILED, diagnostics

    if rendered_inventory is None:
        # Failed to parse rendered manifest - evidence collection failed
        diagnostics["evidence_collection_error"] = "Failed to parse rendered manifest"
        return FAILURE_EVIDENCE_COLLECTION_FAILED, diagnostics

    if not rendered_deployment_present and not cluster_deployment_present:
        # Rendered manifest doesn't have Deployment/k9b AND cluster doesn't have it
        diagnostics["render_analysis"] = "Deployment/k9b not in rendered manifest"
        return FAILURE_WORKLOAD_RENDERED_MISSING_DEPLOYMENT, diagnostics

    if rendered_deployment_present and not cluster_deployment_present:
        # Rendered manifest has Deployment/k9b but cluster doesn't
        if helm_release_exists:
            # Helm release exists, so apply was attempted
            diagnostics["render_analysis"] = "Deployment/k9b rendered but missing in cluster"
            return FAILURE_WORKLOAD_RENDERED_BUT_CLUSTER_MISSING, diagnostics
        else:
            # No Helm release - install didn't complete
            diagnostics["render_analysis"] = "No Helm release found after install"
            return FAILURE_HELM_RELEASE_MISSING, diagnostics

    # Default fallback
    return FAILURE_EXPECTED_WORKLOAD_MISSING, diagnostics


def _is_deployment_in_cluster(deployments_json: str, name: str) -> bool:
    """Check if a deployment with given name exists in cluster.

    Args:
        deployments_json: JSON from kubectl get deployments -o json
        name: Deployment name to look for

    Returns:
        True if deployment exists, False otherwise
    """
    if not deployments_json:
        return False

    try:
        data = json.loads(deployments_json)
        if not isinstance(data, dict):
            return False

        items = data.get("items", [])
        for deploy in items:
            deploy_name = deploy.get("metadata", {}).get("name", "")
            if deploy_name == name:
                return True
    except json.JSONDecodeError:
        pass

    return False


def build_workload_missing_diagnostics(
    failure_subclass: str,
    artifact_dir: Path,
    helm_evidence: dict[str, Any],
    render_evidence: dict[str, Any],
    cluster_deployment_present: bool,
) -> dict[str, Any]:
    """Build comprehensive diagnostics for workload missing classification.

    Args:
        failure_subclass: The specific sub-classification
        artifact_dir: Directory for artifacts
        helm_evidence: Evidence from Helm release state
        render_evidence: Evidence from rendered manifest
        cluster_deployment_present: Whether Deployment/k9b is in cluster

    Returns:
        Diagnostics dictionary for the classification
    """
    diagnostics: dict[str, Any] = {
        "expected_workload": {
            "kind": "Deployment",
            "name": "k9b",
        },
        "failure_subclass": failure_subclass,
        "cluster_deployment_present": cluster_deployment_present,
    }

    # Add Helm evidence
    if helm_evidence:
        diagnostics["helm_release_exists"] = helm_evidence.get("helm_release_exists")
        diagnostics["helm_release_status"] = helm_evidence.get("helm_release_status")
        diagnostics["evidence_artifacts"] = helm_evidence.get("evidence_artifacts", [])

    # Add render evidence
    if render_evidence:
        diagnostics["rendered_manifest_captured"] = render_evidence.get(
            "rendered_manifest_captured", False
        )
        diagnostics["rendered_deployment_present"] = render_evidence.get(
            "rendered_deployment_present", False
        )

    return diagnostics
