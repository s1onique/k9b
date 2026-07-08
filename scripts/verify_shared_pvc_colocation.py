#!/usr/bin/env python3
"""
verify_shared_pvc_colocation.py

Verifies that Kubernetes Deployments mounting persistentVolumeClaim volumes
that are shared with other Deployments have required pod affinity to ensure
co-location on the same node.

Policy:
  For each apps/v1 Deployment:
    if spec.template.spec.volumes[*].persistentVolumeClaim.claimName is shared:
      require spec.template.spec.affinity.podAffinity.requiredDuringSchedulingIgnoredDuringExecution
        with topologyKey: kubernetes.io/hostname

Canonical policy for this chart:
  k9b-scheduler shares PVC with k9b-backend
  => scheduler must require podAffinity to backend on kubernetes.io/hostname

Usage:
  scripts/verify_shared_pvc_colocation.py                    # verify rendered manifests
  scripts/verify_shared_pvc_colocation.py --self-test        # run self-test mode
  scripts/verify_shared_pvc_colocation.py --manifests DIR    # verify directory of YAML files
"""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent.resolve()


def parse_yaml_documents(content: str) -> list[dict]:
    """Parse all YAML documents from content string."""
    documents = []
    for doc in yaml.safe_load_all(content):
        if doc is not None:
            documents.append(doc)
    return documents


def get_deployment_pvc_names(doc: dict) -> dict[str, str]:
    """
    Extract PVC names from a Deployment's volumes.
    
    Returns:
        Dict mapping volume name -> claim name
    """
    volumes = doc.get("spec", {}).get("template", {}).get("spec", {}).get("volumes", [])
    pvc_map = {}
    for volume in volumes:
        if "persistentVolumeClaim" in volume:
            claim_name = volume["persistentVolumeClaim"].get("claimName", "")
            volume_name = volume.get("name", "")
            if claim_name and volume_name:
                pvc_map[volume_name] = claim_name
    return pvc_map


def get_component(doc: dict) -> str:
    """Extract app.kubernetes.io/component label from deployment's pod template."""
    spec = doc.get("spec", {})
    if not spec:
        return ""
    template_spec = spec.get("template", {})
    if not template_spec:
        return ""
    metadata = template_spec.get("metadata", {})
    if not metadata:
        return ""
    template_labels = metadata.get("labels", {})
    component = template_labels.get("app.kubernetes.io/component")
    return component if isinstance(component, str) else ""


def extract_backend_labels(manifests: list[dict]) -> dict[str, str]:
    """
    Extract labels from the backend deployment's pod template.
    
    For the k9b chart, the backend is identified by:
    - kind: Deployment
    - app.kubernetes.io/component: backend
    """
    for doc in manifests:
        kind = doc.get("kind", "")
        if kind != "Deployment":
            continue
        
        template_labels = doc.get("spec", {}).get("template", {}).get("metadata", {}).get("labels", {})
        component = template_labels.get("app.kubernetes.io/component", "")
        
        if component == "backend":
            return {
                "app.kubernetes.io/name": template_labels.get("app.kubernetes.io/name", ""),
                "app.kubernetes.io/instance": template_labels.get("app.kubernetes.io/instance", ""),
                "app.kubernetes.io/component": component,
            }
    
    return {}


def find_shared_pvc_deployments(manifests: list[dict]) -> tuple[set[str], dict[str, list[str]]]:
    """
    Find deployments that mount the same PVC as another deployment.
    
    Policy: shared PVC deployments with app.kubernetes.io/component=backend are primary
            (they don't need affinity). All others sharing the same PVC are secondary.
    
    Returns:
        (shared_pvc_deployments, pvc_to_deployments)
        - shared_pvc_deployments: Set of deployment names that share PVCs
        - pvc_to_deployments: Map of PVC claim name -> list of deployment names
    """
    pvc_to_deployments: dict[str, list[str]] = {}
    deployment_components: dict[str, str] = {}
    
    for doc in manifests:
        if doc.get("kind", "") != "Deployment":
            continue
        if not doc.get("apiVersion", "").startswith("apps/"):
            continue
        
        name = doc.get("metadata", {}).get("name", "unknown")
        deployment_components[name] = get_component(doc)
        
        for claim_name in get_deployment_pvc_names(doc).values():
            pvc_to_deployments.setdefault(claim_name, []).append(name)
    
    shared_pvc_deployments: set[str] = set()
    for deployments in pvc_to_deployments.values():
        if len(deployments) <= 1:
            continue
        
        for deployment in deployments:
            if deployment_components.get(deployment) == "backend":
                continue
            shared_pvc_deployments.add(deployment)
    
    return shared_pvc_deployments, pvc_to_deployments


def check_deployment_colocation(
    doc: dict,
    shared_pvc_deployments: set[str],
    backend_labels: dict[str, str],
) -> tuple[bool, str | None]:
    """
    Check a single Deployment for shared PVC colocation policy.
    
    Args:
        doc: Deployment resource dict
        shared_pvc_deployments: Set of deployment names that share PVCs
        backend_labels: Labels from the backend deployment's pod template
        
    Returns:
        (passes, error_message)
    """
    kind = doc.get("kind", "")
    if kind != "Deployment":
        return True, None
    
    api_version = doc.get("apiVersion", "")
    if not api_version.startswith("apps/"):
        return True, None
    
    metadata = doc.get("metadata", {})
    name = metadata.get("name", "unknown")
    
    if name not in shared_pvc_deployments:
        return True, None
    
    spec = doc.get("spec", {})
    template_spec = spec.get("template", {}).get("spec", {})
    affinity = template_spec.get("affinity", {})
    pod_affinity = affinity.get("podAffinity", {})
    required_affinities = pod_affinity.get("requiredDuringSchedulingIgnoredDuringExecution", [])
    
    if not required_affinities:
        return False, (
            f"Deployment '{name}' shares a persistentVolumeClaim but lacks required "
            f"podAffinity.requiredDuringSchedulingIgnoredDuringExecution. "
            f"Deployments sharing RWO PVCs must co-locate on the same node."
        )
    
    for affinity_term in required_affinities:
        topology_key = affinity_term.get("topologyKey", "")
        if topology_key != "kubernetes.io/hostname":
            return False, (
                f"Deployment '{name}' has podAffinity but uses topologyKey='{topology_key}' "
                f"(expected 'kubernetes.io/hostname'). "
                f"Zone topology does not guarantee same-node placement for RWO PVCs."
            )
        
        label_selector = affinity_term.get("labelSelector") or {}
        
        if not isinstance(label_selector, dict):
            return False, (
                f"Deployment '{name}' has podAffinity labelSelector "
                f"that is not a dict (got {type(label_selector).__name__}). "
                f"Only labelSelector dict is supported for backend targeting."
            )
        
        match_labels = label_selector.get("matchLabels") or {}
        
        if not isinstance(match_labels, dict):
            return False, (
                f"Deployment '{name}' has podAffinity labelSelector.matchLabels "
                f"that is not a dict (got {type(match_labels).__name__}). "
                f"Only matchLabels dict is supported for backend targeting."
            )
        
        if match_labels.get("app.kubernetes.io/component") != "backend":
            return False, (
                f"Deployment '{name}' has podAffinity but selector does not target "
                f"app.kubernetes.io/component=backend. "
                f"Selector matchLabels: {match_labels}"
            )
        
        backend_name = backend_labels.get("app.kubernetes.io/name", "")
        if backend_name:
            if match_labels.get("app.kubernetes.io/name") != backend_name:
                return False, (
                    f"Deployment '{name}' has podAffinity but selector does not match "
                    f"app.kubernetes.io/name from backend. "
                    f"Expected: {backend_name}, "
                    f"Got: {match_labels.get('app.kubernetes.io/name')}"
                )
        
        backend_instance = backend_labels.get("app.kubernetes.io/instance", "")
        if backend_instance:
            if match_labels.get("app.kubernetes.io/instance") != backend_instance:
                return False, (
                    f"Deployment '{name}' has podAffinity but selector does not match "
                    f"app.kubernetes.io/instance from backend. "
                    f"Expected: {backend_instance}, "
                    f"Got: {match_labels.get('app.kubernetes.io/instance')}"
                )
    
    return True, None


def verify_manifests(manifests: list[dict]) -> tuple[list[tuple[str, bool, str | None]], set[str], dict[str, list[str]]]:
    """
    Verify all manifests for shared PVC colocation policy.
    
    Returns:
        (results, shared_pvc_deployments, pvc_to_deployments)
    """
    shared_pvc_deployments, pvc_to_deployments = find_shared_pvc_deployments(manifests)
    backend_labels = extract_backend_labels(manifests)
    
    results = []
    for doc in manifests:
        kind = doc.get("kind", "")
        if kind != "Deployment":
            continue
        
        metadata = doc.get("metadata", {})
        name = metadata.get("name", "unknown")
        
        passed, error = check_deployment_colocation(doc, shared_pvc_deployments, backend_labels)
        results.append((name, passed, error))
    
    return results, shared_pvc_deployments, pvc_to_deployments


def verify_directory(manifest_dir: Path) -> bool:
    """Verify all YAML files in a directory."""
    print("==========================================")
    print("Shared PVC Colocation Policy Verification")
    print("==========================================")
    print()
    
    all_passed = True
    yaml_files = list(manifest_dir.rglob("*.yaml")) + list(manifest_dir.rglob("*.yml"))
    
    if not yaml_files:
        print(f"WARNING: No YAML files found in {manifest_dir}")
        return True
    
    for yaml_file in sorted(yaml_files):
        print(f"Checking: {yaml_file.relative_to(manifest_dir)}")
        
        try:
            with open(yaml_file) as f:
                content = f.read()
        except Exception as e:
            print(f"  ERROR: Could not read file: {e}")
            all_passed = False
            continue
        
        docs = parse_yaml_documents(content)
        results, shared_deployments, pvc_map = verify_manifests(docs)
        
        if shared_deployments:
            print(f"  Shared PVCs detected: {shared_deployments}")
        
        for name, passed, error in results:
            if not passed:
                print(f"  FAIL: {error}")
                all_passed = False
            else:
                print(f"  OK: {name}")
    
    print()
    print("==========================================")
    if all_passed:
        print("RESULT: PASSED")
        return True
    else:
        print("RESULT: FAILED")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify shared PVC colocation policy for Kubernetes Deployments.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mode to prove verifier correctness",
    )
    parser.add_argument(
        "--manifests",
        type=Path,
        help="Directory containing YAML manifest files to verify",
    )
    
    args = parser.parse_args()
    
    if args.self_test:
        # Delegate to self-test module
        from verify_shared_pvc_colocation_selftest import run_self_test

        success = run_self_test()
        return 0 if success else 1
    
    if args.manifests:
        if not args.manifests.is_dir():
            print(f"ERROR: {args.manifests} is not a directory", file=sys.stderr)
            return 1
        success = verify_directory(args.manifests)
        return 0 if success else 1
    
    # Default: verify rendered Helm templates
    chart_dir = REPO_ROOT / "charts" / "k9b"
    
    if not chart_dir.exists():
        print(f"ERROR: Chart directory not found: {chart_dir}", file=sys.stderr)
        return 1
    
    print("Rendering Helm templates...")
    result = subprocess.run(
        [
            "helm",
            "template",
            "k9b",
            str(chart_dir),
            "--set",
            "backend.internalApi.existingSecret=k9b-internal-api",
            "--set",
            "scheduler.incidentPromotion.internalApi.existingSecret=k9b-internal-api",
        ],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        print(f"ERROR: helm template failed: {result.stderr}", file=sys.stderr)
        return 1
    
    docs = parse_yaml_documents(result.stdout)
    results, shared_deployments, pvc_map = verify_manifests(docs)
    
    print("==========================================")
    print("Shared PVC Colocation Policy Verification")
    print("==========================================")
    print()
    
    if shared_deployments:
        print("Shared PVC deployments detected:")
        for pvc, deployments in pvc_map.items():
            if len(deployments) > 1:
                print(f"  {pvc}: {deployments}")
        print()
    
    all_passed = True
    for name, passed, error in results:
        if not passed:
            print(f"FAIL: {error}")
            all_passed = False
        else:
            print(f"OK: {name}")
    
    print()
    print("==========================================")
    if all_passed:
        print("RESULT: PASSED")
        print()
        print("All Deployments sharing PVCs have required podAffinity on kubernetes.io/hostname.")
        return 0
    else:
        print("RESULT: FAILED")
        print()
        print("Deployments sharing RWO PVCs must co-locate on the same node using required pod affinity.")
        return 1


if __name__ == "__main__":
    sys.exit(main())