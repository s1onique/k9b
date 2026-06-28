#!/usr/bin/env python3
"""Preflight check functions for CNPG Live Lab.

This module contains preflight checks for cluster reachability and permissions.
"""

from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from .k9b_cnpg_live_lab_config import DiagnosisGenerator, PreflightData
from .k9b_cnpg_live_lab_constants import (
    FAILURE_API_DISCOVERY_FAILED,
    FAILURE_CLUSTER_API_TIMEOUT,
)
from .k9b_cnpg_live_lab_helpers import log

# Patterns that indicate cluster_api_timeout
_CLUSTER_API_TIMEOUT_PATTERNS = [
    re.compile(r"i/o timeout", re.IGNORECASE),
    re.compile(r"dial tcp.*timeout", re.IGNORECASE),
    re.compile(r"connection refused", re.IGNORECASE),
    re.compile(r"no route to host", re.IGNORECASE),
    re.compile(r"network is unreachable", re.IGNORECASE),
]

# Patterns that indicate API discovery failed
_API_DISCOVERY_PATTERNS = [
    re.compile(r"couldn't get current server API group list", re.IGNORECASE),
    re.compile(r"error: unable to read kubectl configuration", re.IGNORECASE),
    re.compile(r"no configuration has been provided", re.IGNORECASE),
]


def _classify_connectivity_error(error_output: str | None) -> str | None:
    """Classify a kubectl connectivity error.

    Returns the failure class string if classified, None otherwise.
    """
    if not error_output:
        return None

    for pattern in _CLUSTER_API_TIMEOUT_PATTERNS:
        if pattern.search(error_output):
            return FAILURE_CLUSTER_API_TIMEOUT

    for pattern in _API_DISCOVERY_PATTERNS:
        if pattern.search(error_output):
            return FAILURE_API_DISCOVERY_FAILED

    # Generic check for timeout keywords (case-insensitive)
    lower_output = error_output.lower()
    if "timeout" in lower_output or "timed out" in lower_output:
        return FAILURE_CLUSTER_API_TIMEOUT

    return None


def _extract_api_endpoint(kubeconfig: str) -> tuple[str | None, int | None]:
    """Extract API server endpoint from kubeconfig.

    Returns (host, port) tuple or (None, None) if not found.
    """
    try:
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "config", "view",
             "--minify", "-o", "jsonpath={.clusters[0].cluster.server}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            url = urlparse(result.stdout.strip())
            host = url.hostname
            port = url.port or 443
            return host, port
    except Exception:
        pass
    return None, None


def run_preflight_checks(
    kubeconfig: str,
    namespace: str,
    artifact_dir: Path,
    preflight: PreflightData,
    diagnosis: DiagnosisGenerator,
) -> None:
    """Run preflight checks for cluster reachability and permissions.

    Classifies cluster connectivity failures as cluster_api_timeout when
    TCP-level connectivity to the API server fails.
    """
    if not namespace:
        return

    log(f"Running preflight checks for namespace: {namespace}")
    diagnosis.heading(2, "Kubernetes Preflight Checks")

    # Current context
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "config", "current-context"],
        capture_output=True,
        text=True,
    )
    ctx = result.stdout.strip() or "unknown"
    preflight.current_context = ctx
    diagnosis.text(f"**Current context**: {diagnosis.inline_code(ctx)}")

    # API reachability with classification
    diagnosis.text("**API reachability**: checking...")
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "cluster-info"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    preflight.api_reachable = result.returncode == 0

    error_output = result.stderr or result.stdout

    if result.returncode == 0:
        diagnosis.code(result.stdout, "")
    else:
        diagnosis.code(error_output or "cluster-info failed", "")

        # Classify connectivity errors
        failure_class = _classify_connectivity_error(error_output)
        if failure_class:
            preflight.failure_class = failure_class
            preflight.failure_stage = "cluster_connectivity"
            preflight.failure_reason = f"API server unreachable: {error_output[:200]}"
            log(f"Classified connectivity error as: {failure_class}")

            # Extract API endpoint for diagnostics
            api_host, api_port = _extract_api_endpoint(kubeconfig)
            if api_host:
                diagnosis.text(f"**Target API endpoint**: {api_host}:{api_port}")

    # Namespace check
    diagnosis.text(f"**Namespace {diagnosis.inline_code(namespace)}**: checking...")
    result = subprocess.run(
        ["kubectl", "--kubeconfig", kubeconfig, "get", "namespace", namespace, "-o", "jsonpath={.status.phase}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        preflight.namespace_exists = True
        preflight.namespace_status = result.stdout.strip()
        diagnosis.text(f"Status: {diagnosis.inline_code(preflight.namespace_status)}")
    else:
        preflight.namespace_exists = False
        preflight.namespace_status = "not_found"
        diagnosis.text(f"Not found or not accessible: {result.stderr}")

    # RBAC can-i checks
    diagnosis.text("**RBAC permissions for Helm deployment**: running can-i checks...")
    rbac_lines = []
    rbac_lines.append("=== RBAC can-i checks ===")
    rbac_lines.append(f"Timestamp: {datetime.now(UTC).isoformat()}")
    rbac_lines.append("")

    can_i_checks = [
        ("get", "pods", namespace),
        ("create", "pods", namespace),
        ("delete", "pods", namespace),
        ("get", "services", namespace),
        ("create", "services", namespace),
        ("get", "configmaps", namespace),
        ("create", "configmaps", namespace),
        ("get", "secrets", namespace),
        ("create", "secrets", namespace),
        ("get", "deployments.apps", namespace),
        ("create", "deployments.apps", namespace),
        ("get", "statefulsets.apps", namespace),
        ("create", "statefulsets.apps", namespace),
        ("get", "jobs.batch", namespace),
        ("create", "jobs.batch", namespace),
        ("get", "persistentvolumeclaims", namespace),
        ("create", "persistentvolumeclaims", namespace),
        ("get", "rolebindings.rbac.authorization.k8s.io", namespace),
        ("create", "rolebindings.rbac.authorization.k8s.io", namespace),
        ("get", "roles.rbac.authorization.k8s.io", namespace),
        ("create", "roles.rbac.authorization.k8s.io", namespace),
        ("get", "clusters.postgresql.cnpg.io", namespace),
        ("create", "clusters.postgresql.cnpg.io", namespace),
        ("get", "events", namespace),
        ("get", "pods/log", namespace),
    ]

    failed_count = 0
    for verb, resource, ns in can_i_checks:
        resource_ref = f"{resource} -n {ns}" if ns else resource
        result = subprocess.run(
            ["kubectl", "--kubeconfig", kubeconfig, "auth", "can-i", verb, resource, "-n", ns, "--quiet"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            rbac_lines.append(f"[YES] {verb} {resource_ref}")
        else:
            rbac_lines.append(f"[NO]  {verb} {resource_ref}")
            failed_count += 1

    rbac_lines.append("")
    if failed_count > 0:
        rbac_lines.append(f"FAILED: {failed_count} permission(s) missing")
    else:
        rbac_lines.append("PASSED: All can-i checks succeeded")

    # Write RBAC results
    (artifact_dir / "rbac-can-i.txt").write_text("\n".join(rbac_lines) + "\n")
    diagnosis.text("RBAC checks written to rbac-can-i.txt")
    preflight.rbac_checks_complete = True
