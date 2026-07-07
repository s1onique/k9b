#!/usr/bin/env python3
"""Static verifier for Kubernetes Python client critical paths policy.

This script scans production source files for direct kubectl subprocess usage
in critical paths that should use the Kubernetes Python client instead.

Policy:
- Production scheduler/health-loop/incident-evidence paths must use Kubernetes Python client
- kubectl is allowed only as bounded fallback/debug seam
- Allowed kubectl seams: kubectl_logs.py, kubectl_subprocess.py, kubectl_bounded.py, kubectl_collect.py

Usage:
    python scripts/verify_kubernetes_client_critical_paths.py [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Patterns that indicate direct kubectl usage in critical paths
CRITICAL_KUBECTL_PATTERNS = {
    "run_kubectl(": {
        "severity": "error",
        "message": "run_kubectl() in critical path should use Kubernetes Python client",
        "suggestion": "Use KubernetesReadClient from k8s_diag_agent.security.kubernetes_client",
    },
    "collect_pod_logs_bounded(": {
        "severity": "error",
        "message": "collect_pod_logs_bounded() should be replaced with Kubernetes Python client",
        "suggestion": "Use KubernetesReadClient.read_pod_logs_bounded()",
    },
    '["kubectl"': {
        "severity": "error",
        "message": "kubectl command list in critical path should use Kubernetes Python client",
        "suggestion": "Use KubernetesReadClient from k8s_diag_agent.security.kubernetes_client",
    },
    '["helm"': {
        "severity": "info",  # helm is allowed
        "message": "helm usage is allowed",
    },
}

# Critical paths that must use Kubernetes Python client
CRITICAL_PATHS = [
    "src/k8s_diag_agent/identity/",
    "src/k8s_diag_agent/collect/incident_diagnosis_loop_gate.py",
    "src/k8s_diag_agent/health/image_pull_secret.py",
    "src/k8s_diag_agent/collect/incident_collectors.py",
    "src/k8s_diag_agent/collect/live_snapshot.py",
]

# Files/directories to exclude from scanning
EXCLUDED_PATHS = {
    "tests/",
    "test_",
    "conftest.py",
    "__pycache__/",
    ".venv/",
    "fixtures/",
    "evals/",
    "docs/",
}

# Files that are explicitly allowlisted (kubectl fallback seam)
ALLOWLISTED_FILES = {
    "src/k8s_diag_agent/security/kubectl_bounded.py",
    "src/k8s_diag_agent/security/kubectl_subprocess.py",
    "src/k8s_diag_agent/security/kubectl_logs.py",
    "src/k8s_diag_agent/security/kubectl_collect.py",
    "src/k8s_diag_agent/health/loop_alertmanager_port_forward.py",  # port-forward specific
    "src/k8s_diag_agent/health/drilldown.py",  # drilldown uses kubectl for specific UI ops
}


def is_critical_path(path: str) -> bool:
    """Check if a path is a critical path that must use Kubernetes Python client."""
    # Check for exact matches first
    for critical_path in CRITICAL_PATHS:
        if critical_path.endswith("/"):
            if path.startswith(critical_path):
                return True
        elif path == critical_path:
            return True
    return False


def is_excluded(path: str) -> bool:
    """Check if a path should be excluded from scanning."""
    path_lower = path.lower()
    for excluded in EXCLUDED_PATHS:
        if excluded in path_lower:
            return True
    return False


def is_allowlisted(path: str) -> bool:
    """Check if a path is explicitly allowlisted."""
    return any(allowlisted in path for allowlisted in ALLOWLISTED_FILES)


def scan_file(path: Path) -> list[dict]:
    """Scan a single file for kubectl usage in critical paths."""
    findings: list[dict] = []

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
    except (UnicodeDecodeError, OSError) as e:
        return [{
            "path": str(path),
            "line": 0,
            "pattern": "<read_error>",
            "message": f"Could not read file: {e}",
            "severity": "warning",
        }]

    rel_path = str(path)

    # Skip non-critical paths
    if not is_critical_path(rel_path):
        return findings

    # Skip allowlisted files
    if is_allowlisted(rel_path):
        return findings

    # Check for kubectl patterns
    for line_num, line in enumerate(lines, start=1):
        for pattern, info in CRITICAL_KUBECTL_PATTERNS.items():
            if pattern in line:
                # Skip comments
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue

                # Check for kubernetes client import (if present, the line might be OK)
                if "kubernetes_client" in line:
                    continue

                # Check for import statement (imports are OK)
                if "from ..security.kubectl" in line and "import" in line:
                    continue

                # helm is always allowed
                if pattern == '["helm"':
                    continue

                findings.append({
                    "path": rel_path,
                    "line": line_num,
                    "code": line.strip(),
                    "pattern": pattern,
                    "message": info["message"],
                    "suggestion": info.get("suggestion", ""),
                    "severity": info["severity"],
                })

    return findings


def scan_directory(repo_root: Path) -> list[dict]:
    """Scan the repository for kubectl usage in critical paths."""
    all_findings = []

    src_dir = repo_root / "src" / "k8s_diag_agent"

    for path in src_dir.rglob("*.py"):
        rel_path = str(path.relative_to(repo_root))

        if is_excluded(rel_path):
            continue

        findings = scan_file(path)
        all_findings.extend(findings)

    return all_findings


def format_findings(findings: list[dict], json_output: bool = False) -> str:
    """Format findings for output."""
    if json_output:
        return json.dumps({
            "findings": findings,
            "summary": {
                "total": len(findings),
                "errors": sum(1 for f in findings if f["severity"] == "error"),
                "warnings": sum(1 for f in findings if f["severity"] == "warning"),
                "info": sum(1 for f in findings if f["severity"] == "info"),
            }
        }, indent=2)

    if not findings:
        return "No Kubernetes client critical paths violations found."

    # Filter to only errors
    errors = [f for f in findings if f["severity"] == "error"]

    if not errors:
        return "No Kubernetes client critical paths violations found."

    output = []
    output.append("=" * 70)
    output.append("KUBERNETES CLIENT CRITICAL PATHS VIOLATIONS")
    output.append("=" * 70)
    output.append("")

    output.append(f"ERRORS ({len(errors)}):")
    output.append("-" * 70)
    for finding in errors:
        output.append(f"\n{finding['path']}:{finding['line']}")
        output.append(f"  Pattern: {finding['pattern']}")
        output.append(f"  {finding['message']}")
        if finding.get("suggestion"):
            output.append(f"  Suggestion: {finding['suggestion']}")
        output.append(f"  Code: {finding.get('code', '')}")

    output.append("")
    output.append("=" * 70)
    output.append(f"Total: {len(errors)} errors")
    output.append("=" * 70)

    return "\n".join(output)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify Kubernetes client critical paths policy compliance"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).parent.parent,
        help="Repository root path"
    )
    args = parser.parse_args()

    findings = scan_directory(args.repo_root)

    output = format_findings(findings, json_output=args.json)
    print(output)

    # Return non-zero if there are errors
    errors = [f for f in findings if f["severity"] == "error"]
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
