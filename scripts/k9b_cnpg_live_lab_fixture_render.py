#!/usr/bin/env python3
"""Fixture namespace renderer for CNPG Live Lab.

Renders incident fixture manifests with namespace normalization:
- Parses all YAML documents
- For namespaced resources, sets metadata.namespace = LAB_NAMESPACE
- For Namespace objects, requires the name to equal LAB_NAMESPACE
- Leaves cluster-scoped resources untouched
- Preserves labels/annotations/spec
- Writes the rendered manifest to artifacts
- Fails closed if any namespaced object still has a namespace different from LAB_NAMESPACE

Usage:
    python k9b_cnpg_live_lab_fixture_render.py render \
        --fixture <path> --output <path> --namespace <ns>

    python k9b_cnpg_live_lab_fixture_render.py verify \
        --fixture <path> --namespace <ns>
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

# Failure class constant
FAILURE_CLASS_FIXTURE_NAMESPACE_MISMATCH = "incident_fixture_namespace_mismatch"

# Cluster-scoped resource kinds (no namespace)
CLUSTER_SCOPED_KINDS = {
    "Namespace",
    "Node",
    "PersistentVolume",
    "ClusterRole",
    "ClusterRoleBinding",
    "CustomResourceDefinition",
    "APIService",
    "MeshPeer",
}

# Namespace-scoped resource kinds that MUST have namespace = LAB_NAMESPACE
# Resources with these kinds that declare a different namespace will fail
NAMESPACED_KINDS = {
    "Pod",
    "Service",
    "ConfigMap",
    "Secret",
    "Deployment",
    "StatefulSet",
    "DaemonSet",
    "ReplicaSet",
    "Job",
    "CronJob",
    "Ingress",
    "ServiceAccount",
    "Role",
    "RoleBinding",
    "PersistentVolumeClaim",
    "HorizontalPodAutoscaler",
    "NetworkPolicy",
    "LimitRange",
    "ResourceQuota",
    "PodDisruptionBudget",
    "Endpoints",
    "Event",
    "NodeMetrics",  # metrics.k8s.io
}


def log(msg: str) -> None:
    """Log info message."""
    print(f"[fixture-render] {msg}", flush=True)


def warn(msg: str) -> None:
    """Log warning message."""
    print(f"[fixture-render] WARNING: {msg}", file=sys.stderr, flush=True)


def error(msg: str) -> None:
    """Log error message."""
    print(f"[fixture-render] ERROR: {msg}", file=sys.stderr, flush=True)


def is_cluster_scoped(kind: str) -> bool:
    """Check if a resource kind is cluster-scoped."""
    return kind in CLUSTER_SCOPED_KINDS


def is_namespaced_kind(kind: str) -> bool:
    """Check if a resource kind is namespaced (excluding Namespace itself)."""
    # Namespace objects are handled specially
    if kind == "Namespace":
        return False
    return kind in NAMESPACED_KINDS


def parse_yaml_documents(content: str) -> list[dict[str, Any]]:
    """Parse YAML content into a list of documents."""
    documents = list(yaml.safe_load_all(content))
    return [doc for doc in documents if doc is not None]


def render_fixture(
    fixture_path: Path,
    output_path: Path,
    target_namespace: str,
    allow_cluster_scoped: bool = False,
) -> tuple[bool, list[dict[str, Any]]]:
    """Render a fixture manifest with namespace normalization.

    Args:
        fixture_path: Path to the source fixture YAML
        output_path: Path to write the rendered YAML
        target_namespace: The target namespace for namespaced resources
        allow_cluster_scoped: If True, preserve cluster-scoped resources.
                              If False, reject them as fatal.

    Returns:
        Tuple of (success, list of issues)
        - success=True: render succeeded, issues contains normalized mismatches
        - success=False: fatal error (parse failure, disallowed cluster-scoped, etc.)
        - issues contains both normalized and fatal entries
    """
    if not fixture_path.exists():
        error(f"Fixture not found: {fixture_path}")
        return False, [{"error": f"Fixture not found: {fixture_path}"}]

    content = fixture_path.read_text()
    documents = parse_yaml_documents(content)

    if not documents:
        error(f"No valid YAML documents found in {fixture_path}")
        return False, [{"error": "No valid YAML documents found"}]

    rendered_docs: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    fatal_issues: list[dict[str, Any]] = []

    for i, doc in enumerate(documents):
        kind = doc.get("kind", "")
        metadata = doc.get("metadata", {})

        # Handle Namespace objects specially
        if kind == "Namespace":
            ns_name = metadata.get("name", "")
            if ns_name != target_namespace:
                # Namespace object name mismatch is ALWAYS fatal
                fatal_issues.append({
                    "document_index": i,
                    "kind": kind,
                    "name": ns_name,
                    "problem": "namespace_object_mismatch",
                    "fixture_namespace": ns_name,
                    "target_namespace": target_namespace,
                    "message": f"Namespace object name '{ns_name}' must equal target namespace '{target_namespace}'",
                    "severity": "fatal",
                })
            # Render with correct namespace (even if we'll fail later)
            doc["metadata"]["name"] = target_namespace
            rendered_docs.append(doc)
            continue

        # Handle cluster-scoped resources
        if is_cluster_scoped(kind):
            if not allow_cluster_scoped:
                # Reject cluster-scoped resources by default
                fatal_issues.append({
                    "document_index": i,
                    "kind": kind,
                    "name": metadata.get("name", ""),
                    "problem": "cluster_scoped_resource",
                    "message": f"Cluster-scoped resource {kind}/{metadata.get('name')} not allowed in namespace-mode lab",
                    "severity": "fatal",
                })
            else:
                # Preserve cluster-scoped resources when explicitly allowed
                rendered_docs.append(doc)
            continue

        # Handle namespaced resources
        if is_namespaced_kind(kind) or "namespace" in metadata:
            fixture_ns = metadata.get("namespace", "")

            # Namespace mismatch on namespaced resource is NORMALIZABLE
            if fixture_ns and fixture_ns != target_namespace:
                issues.append({
                    "document_index": i,
                    "kind": kind,
                    "name": metadata.get("name", ""),
                    "problem": "namespace_normalized",
                    "fixture_namespace": fixture_ns,
                    "target_namespace": target_namespace,
                    "message": f"Namespaced resource {kind}/{metadata.get('name')} namespace normalized from '{fixture_ns}' to '{target_namespace}'",
                    "severity": "normalized",
                })

            # Always set namespace to target
            metadata["namespace"] = target_namespace
            doc["metadata"] = metadata
            rendered_docs.append(doc)
        else:
            # Unknown kind - leave untouched but log
            warn(f"Unknown resource kind '{kind}' at document {i}, leaving unchanged")
            rendered_docs.append(doc)

    # Write rendered output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.dump_all(rendered_docs, f, default_flow_style=False, sort_keys=False)

    # Combine all issues (normalized mismatches are NOT fatal)
    all_issues = issues + fatal_issues

    # Success only fails if there are fatal issues
    return len(fatal_issues) == 0, all_issues


def verify_fixture(fixture_path: Path, target_namespace: str) -> tuple[bool, list[dict[str, Any]]]:
    """Verify a fixture manifest for namespace compliance.

    Args:
        fixture_path: Path to the fixture YAML
        target_namespace: The expected target namespace

    Returns:
        Tuple of (is_compliant, list of violations)
    """
    if not fixture_path.exists():
        return False, [{"error": f"Fixture not found: {fixture_path}"}]

    content = fixture_path.read_text()
    documents = parse_yaml_documents(content)

    violations: list[dict[str, Any]] = []

    for i, doc in enumerate(documents):
        kind = doc.get("kind", "")
        metadata = doc.get("metadata", {})
        name = metadata.get("name", "(unnamed)")

        # Handle Namespace objects
        if kind == "Namespace":
            ns_name = metadata.get("name", "")
            if ns_name != target_namespace:
                violations.append({
                    "document_index": i,
                    "kind": kind,
                    "name": ns_name,
                    "fixture_namespace": ns_name,
                    "target_namespace": target_namespace,
                    "violation": f"Namespace object name '{ns_name}' differs from target '{target_namespace}'",
                })
            continue

        # Check namespaced resources
        fixture_ns = metadata.get("namespace", "")
        if fixture_ns and fixture_ns != target_namespace:
            violations.append({
                "document_index": i,
                "kind": kind,
                "name": name,
                "fixture_namespace": fixture_ns,
                "target_namespace": target_namespace,
                "violation": f"Namespaced resource {kind}/{name} has namespace '{fixture_ns}' which differs from target '{target_namespace}'",
            })

    return len(violations) == 0, violations


def cmd_render(
    fixture: str,
    output: str,
    namespace: str,
    artifact_dir: str,
    allow_cluster_scoped: bool = False,
) -> int:
    """Execute render command."""
    fixture_path = Path(fixture)
    output_path = Path(output)
    artifact_path = Path(artifact_dir)

    log(f"Rendering fixture: {fixture}")
    log(f"Target namespace: {namespace}")
    log(f"Output path: {output}")

    success, issues = render_fixture(fixture_path, output_path, namespace, allow_cluster_scoped)

    # Separate normalized vs fatal issues
    normalized_issues = [i for i in issues if i.get("severity") == "normalized"]
    fatal_issues = [i for i in issues if i.get("severity") == "fatal"]

    # Write result artifact
    result: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "command": "render",
        "fixture": str(fixture_path),
        "output": str(output_path),
        "target_namespace": namespace,
        "success": success,
        "document_count": len(parse_yaml_documents(fixture_path.read_text())) if fixture_path.exists() else 0,
    }

    if normalized_issues:
        result["normalized_namespaces"] = normalized_issues

    if fatal_issues:
        result["fatal_issues"] = fatal_issues
        # Only emit failure_class on fatal issues
        result["failure_class"] = fatal_issues[0].get("problem", "unknown_error")

    result_path = artifact_path / "fixture-render-result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2))

    if success:
        if normalized_issues:
            log(f"SUCCESS: Rendered {result['document_count']} documents to {output_path}")
            for issue in normalized_issues:
                log(f"  normalized: {issue.get('message', '')}")
        else:
            log(f"SUCCESS: Rendered {result['document_count']} documents to {output_path}")
        return 0
    else:
        error(f"FAILURE: {len(fatal_issues)} fatal issue(s) detected")
        for issue in fatal_issues:
            error(f"  - {issue.get('message', str(issue))}")
        error(f"FAILURE_CLASS={result['failure_class']}")
        error("NOT_APPLYING_FIXTURE=true")
        return 1


def cmd_verify(fixture: str, namespace: str) -> int:
    """Execute verify command (preflight check)."""
    fixture_path = Path(fixture)

    log(f"Verifying fixture namespace compliance: {fixture}")
    log(f"Target namespace: {namespace}")

    is_compliant, violations = verify_fixture(fixture_path, namespace)

    if is_compliant:
        log("SUCCESS: Fixture is namespace-compliant")
        return 0
    else:
        error(f"FAILURE: {len(violations)} namespace violation(s) detected")
        for violation in violations:
            error(f"  - {violation.get('violation', str(violation))}")
        error(f"FAILURE_CLASS={FAILURE_CLASS_FIXTURE_NAMESPACE_MISMATCH}")
        return 1


def cmd_verify_all(fixtures_dir: str, namespace: str) -> int:
    """Execute verify-all command to check all fixtures in a directory."""
    fixtures_path = Path(fixtures_dir)

    if not fixtures_path.is_dir():
        error(f"Fixtures directory not found: {fixtures_dir}")
        return 1

    all_violations: dict[str, list[dict[str, Any]]] = {}
    total_violations = 0

    for yaml_file in fixtures_path.rglob("*.yaml"):
        is_compliant, violations = verify_fixture(yaml_file, namespace)
        if not is_compliant:
            all_violations[str(yaml_file)] = violations
            total_violations += len(violations)

    if total_violations == 0:
        log(f"SUCCESS: All fixtures in {fixtures_dir} are namespace-compliant")
        return 0
    else:
        error(f"FAILURE: {total_violations} namespace violation(s) in {len(all_violations)} file(s)")
        for fixture_file, violations in all_violations.items():
            error(f"\n{fixture_file}:")
            for violation in violations:
                error(f"  - {violation.get('violation', str(violation))}")
        return 1


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Fixture namespace renderer and verifier for CNPG Live Lab"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Render command
    p_render = subparsers.add_parser("render", help="Render fixture with namespace normalization")
    p_render.add_argument("--fixture", required=True, help="Path to source fixture YAML")
    p_render.add_argument("--output", required=True, help="Path to write rendered YAML")
    p_render.add_argument("--namespace", required=True, help="Target namespace")
    p_render.add_argument("--artifact-dir", default="./lab-artifacts/live", help="Artifact directory")

    # Verify command
    p_verify = subparsers.add_parser("verify", help="Verify fixture namespace compliance")
    p_verify.add_argument("--fixture", required=True, help="Path to fixture YAML")
    p_verify.add_argument("--namespace", required=True, help="Expected namespace")

    # Verify-all command
    p_verify_all = subparsers.add_parser("verify-all", help="Verify all fixtures in directory")
    p_verify_all.add_argument("--fixtures-dir", required=True, help="Directory containing fixtures")
    p_verify_all.add_argument("--namespace", required=True, help="Expected namespace")

    args = parser.parse_args()

    match args.command:
        case "render":
            return cmd_render(args.fixture, args.output, args.namespace, args.artifact_dir)
        case "verify":
            return cmd_verify(args.fixture, args.namespace)
        case "verify-all":
            return cmd_verify_all(args.fixtures_dir, args.namespace)
        case _:
            parser.print_help()
            return 1


if __name__ == "__main__":
    sys.exit(main())
