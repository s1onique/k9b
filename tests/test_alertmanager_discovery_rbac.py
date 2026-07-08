"""Verify Alertmanager discovery RBAC resources and verbs in rendered Helm chart.

This test verifies that the K9B Helm chart renders RBAC with the correct
read-only permissions for Alertmanager discovery.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import yaml


def get_rbac_rules(cluster_scoped: bool) -> Any:
    """Render Helm chart and extract RBAC rules."""
    scope = "true" if cluster_scoped else "false"
    cmd = [
        "helm", "template", "test", "./charts/k9b",
        "--show-only", "templates/rbac.yaml",
        "--set", "rbac.create=true",
        "--set", f"rbac.clusterScoped={scope}",
        "--set", "backend.internalApi.existingSecret=k9b-internal-api",
        "--set", "backend.internalApi.tokenKey=K9B_INTERNAL_API_TOKEN",
        "--set", "scheduler.incidentPromotion.internalApi.existingSecret=k9b-internal-api",
        "--set", "scheduler.incidentPromotion.internalApi.tokenKey=K9B_INTERNAL_API_TOKEN",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    
    docs = list(yaml.safe_load_all(result.stdout))
    # Document index 1 is the ClusterRole/Role (index 0 is ServiceAccount)
    role_doc: dict[str, Any] = docs[1]
    rules = role_doc.get("rules", [])
    return rules


def check_api_group_rules(rules: list, api_group: str, resources: list, expected_verbs: list) -> list:
    """Check that rules contain expected resources with expected verbs for given apiGroup."""
    errors = []
    found_resources = set()
    
    for rule in rules:
        if rule.get("apiGroups") == [api_group]:
            rule_resources = rule.get("resources", [])
            rule_verbs = rule.get("verbs", [])
            
            for resource in resources:
                if resource in rule_resources:
                    found_resources.add(resource)
                    missing_verbs = set(expected_verbs) - set(rule_verbs)
                    if missing_verbs:
                        errors.append(
                            f"Resource {resource} in {api_group} missing verbs: {missing_verbs}"
                        )
    
    missing_resources = set(resources) - found_resources
    if missing_resources:
        errors.append(
            f"Missing resources {missing_resources} in apiGroup {api_group}"
        )
    
    return errors


def check_no_secrets(rules: list) -> list:
    """Verify no secrets permission exists."""
    errors = []
    for rule in rules:
        resources = rule.get("resources", [])
        if "secrets" in resources:
            errors.append("Found secrets permission - should not exist")
    return errors


def check_readonly_verbs(rules: list) -> list:
    """Verify only read-only verbs are used."""
    errors = []
    write_verbs = {"create", "update", "patch", "delete", "deletecollection"}
    
    for rule in rules:
        verbs = set(rule.get("verbs", []))
        found_write = verbs & write_verbs
        if found_write:
            errors.append(f"Found write verbs {found_write} - should be read-only")
    
    return errors


def test_clusterrole_alertmanager_discovery_rbac():
    """Test ClusterRole has correct Alertmanager discovery RBAC (cluster-scoped)."""
    rules = get_rbac_rules(cluster_scoped=True)
    errors = []
    
    # Check core resources
    errors.extend(check_api_group_rules(
        rules, "", 
        ["services", "endpoints", "pods"],
        ["get", "list", "watch"]
    ))
    
    # Check apps resources
    errors.extend(check_api_group_rules(
        rules, "apps",
        ["statefulsets"],
        ["get", "list", "watch"]
    ))
    
    # Check discovery API
    errors.extend(check_api_group_rules(
        rules, "discovery.k8s.io",
        ["endpointslices"],
        ["get", "list", "watch"]
    ))
    
    # Check monitoring CRDs
    errors.extend(check_api_group_rules(
        rules, "monitoring.coreos.com",
        ["alertmanagers", "prometheuses", "alertmanagerconfigs"],
        ["get", "list", "watch"]
    ))
    
    # Security checks
    errors.extend(check_no_secrets(rules))
    errors.extend(check_readonly_verbs(rules))
    
    assert not errors, f"ClusterRole RBAC errors: {errors}"


def test_role_alertmanager_discovery_rbac():
    """Test Role has correct Alertmanager discovery RBAC (namespace-scoped)."""
    rules = get_rbac_rules(cluster_scoped=False)
    errors = []
    
    # Check core resources
    errors.extend(check_api_group_rules(
        rules, "",
        ["services", "endpoints", "pods"],
        ["get", "list", "watch"]
    ))
    
    # Check apps resources
    errors.extend(check_api_group_rules(
        rules, "apps",
        ["statefulsets"],
        ["get", "list", "watch"]
    ))
    
    # Check discovery API
    errors.extend(check_api_group_rules(
        rules, "discovery.k8s.io",
        ["endpointslices"],
        ["get", "list", "watch"]
    ))
    
    # Note: monitoring.coreos.com CRDs are intentionally excluded from the
    # namespace-scoped Role. K9B's operator-CRD discovery path is modeled as
    # cluster-wide / cross-namespace discovery and is granted only via ClusterRole.
    
    # Security checks
    errors.extend(check_no_secrets(rules))
    errors.extend(check_readonly_verbs(rules))
    
    assert not errors, f"Role RBAC errors: {errors}"


def test_namespace_role_excludes_cluster_wide_discovery_api_groups():
    """Verify namespace-scoped Role does not include cluster-wide discovery API groups."""
    rules = get_rbac_rules(cluster_scoped=False)
    errors = []
    
    # These API groups are modeled as cluster-wide / cross-namespace discovery
    # and are granted only via ClusterRole, not namespace-scoped Role.
    cluster_wide_api_groups = [
        "monitoring.coreos.com",
        "operator.victoriametrics.com",
    ]
    
    for rule in rules:
        api_groups = rule.get("apiGroups", [])
        for api_group in api_groups:
            if api_group in cluster_wide_api_groups:
                errors.append(
                    f"Found cluster-wide apiGroup '{api_group}' in namespace Role - "
                    f"resources: {rule.get('resources', [])}"
                )
    
    assert not errors, f"Namespace Role should not include cluster-wide discovery API groups: {errors}"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
