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

Self-test mode proves:
  - BAD fixture: scheduler shares PVC but has no affinity -> FAIL
  - BAD fixture: scheduler has soft/preferred affinity only -> FAIL
  - BAD fixture: scheduler affinity uses zone topology -> FAIL
  - GOOD fixture: scheduler has required backend pod affinity on hostname -> PASS
  - GOOD fixture: deployment doesn't share PVC -> PASS
"""

import argparse
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
        - (True, None) if deployment passes policy
        - (False, error_message) if deployment violates policy
    """
    kind = doc.get("kind", "")
    if kind != "Deployment":
        return True, None
    
    api_version = doc.get("apiVersion", "")
    if not api_version.startswith("apps/"):
        return True, None
    
    metadata = doc.get("metadata", {})
    name = metadata.get("name", "unknown")
    
    # Skip deployments that don't share PVCs
    if name not in shared_pvc_deployments:
        return True, None
    
    # Check for required pod affinity
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
    
    # Check each affinity term
    for affinity_term in required_affinities:
        topology_key = affinity_term.get("topologyKey", "")
        if topology_key != "kubernetes.io/hostname":
            return False, (
                f"Deployment '{name}' has podAffinity but uses topologyKey='{topology_key}' "
                f"(expected 'kubernetes.io/hostname'). "
                f"Zone topology does not guarantee same-node placement for RWO PVCs."
            )
        
        # Verify the selector targets the backend pod
        label_selector = affinity_term.get("labelSelector", {})
        match_labels = label_selector.get("matchLabels", {})
        
        # Must match at least app.kubernetes.io/component=backend
        if match_labels.get("app.kubernetes.io/component") != "backend":
            return False, (
                f"Deployment '{name}' has podAffinity but selector does not target "
                f"app.kubernetes.io/component=backend. "
                f"Selector matchLabels: {match_labels}"
            )
        
        # Should also match app.kubernetes.io/name if backend has it (and it's non-empty)
        backend_name = backend_labels.get("app.kubernetes.io/name", "")
        if backend_name:
            if match_labels.get("app.kubernetes.io/name") != backend_name:
                return False, (
                    f"Deployment '{name}' has podAffinity but selector does not match "
                    f"app.kubernetes.io/name from backend. "
                    f"Expected: {backend_name}, "
                    f"Got: {match_labels.get('app.kubernetes.io/name')}"
                )
        
        # Should also match app.kubernetes.io/instance if backend has it (and it's non-empty)
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


def get_component(doc: dict) -> str:
    """Extract app.kubernetes.io/component label from deployment's pod template."""
    template_labels = (
        doc.get("spec", {})
        .get("template", {})
        .get("metadata", {})
        .get("labels", {})
    )
    return template_labels.get("app.kubernetes.io/component", "")


def find_shared_pvc_deployments(manifests: list[dict]) -> tuple[set[str], dict[str, list[str]]]:
    """
    Find deployments that mount the same PVC as another deployment.
    
    Policy: shared PVC deployments with app.kubernetes.io/component=backend are primary
            (they don't need affinity). All others sharing the same PVC are secondary.
    
    Returns:
        (shared_pvc_deployments, pvc_to_deployments)
        - shared_pvc_deployments: Set of deployment names that share PVCs
          (only secondary deployments that need affinity - backend is excluded by component label)
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
    
    # Find PVCs shared by multiple deployments
    # Backend component is primary (doesn't need affinity); all others need affinity
    shared_pvc_deployments: set[str] = set()
    for deployments in pvc_to_deployments.values():
        if len(deployments) <= 1:
            continue
        
        for deployment in deployments:
            # Backend is primary - it schedules first and owns the PVC
            if deployment_components.get(deployment) == "backend":
                continue
            shared_pvc_deployments.add(deployment)
    
    return shared_pvc_deployments, pvc_to_deployments


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
        
        # Check component label in pod template
        template_labels = doc.get("spec", {}).get("template", {}).get("metadata", {}).get("labels", {})
        component = template_labels.get("app.kubernetes.io/component", "")
        
        if component == "backend":
            # Return the relevant labels for affinity matching
            return {
                "app.kubernetes.io/name": template_labels.get("app.kubernetes.io/name", ""),
                "app.kubernetes.io/instance": template_labels.get("app.kubernetes.io/instance", ""),
                "app.kubernetes.io/component": component,
            }
    
    return {}


def verify_manifests(manifests: list[dict]) -> tuple[list[tuple[str, bool, str | None]], set[str], dict[str, list[str]]]:
    """
    Verify all manifests for shared PVC colocation policy.
    
    Returns:
        (results, shared_pvc_deployments, pvc_to_deployments)
    """
    shared_pvc_deployments, pvc_to_deployments = find_shared_pvc_deployments(manifests)
    
    # Extract backend labels for selector verification
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


def run_self_test() -> bool:
    """Run self-test mode to prove the verifier works correctly."""
    print("Running self-test mode...")
    print()
    
    all_passed = True
    
    # Backend deployment (shared PVC partner) - includes instance label for Test 8
    backend_yaml = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-backend
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: k9b
      app.kubernetes.io/instance: RELEASE_NAME
      app.kubernetes.io/component: backend
  template:
    metadata:
      labels:
        app.kubernetes.io/name: k9b
        app.kubernetes.io/instance: RELEASE_NAME
        app.kubernetes.io/component: backend
    spec:
      containers:
        - name: backend
          image: k9b:latest
      volumes:
        - name: runs
          persistentVolumeClaim:
            claimName: k9b-runs
---
"""
    
    # BAD fixture: scheduler shares PVC but has no affinity
    print("=== Test 1: BAD fixture (scheduler shares PVC, no affinity) should FAIL ===")
    bad_no_affinity = backend_yaml + """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-scheduler
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: k9b
      app.kubernetes.io/component: scheduler
  template:
    metadata:
      labels:
        app.kubernetes.io/name: k9b
        app.kubernetes.io/component: scheduler
    spec:
      containers:
        - name: scheduler
          image: k9b:latest
      volumes:
        - name: runs
          persistentVolumeClaim:
            claimName: k9b-runs
"""
    docs = parse_yaml_documents(bad_no_affinity)
    shared, _ = find_shared_pvc_deployments(docs)
    results, _, _ = verify_manifests(docs)
    
    test1_passed = False
    for name, passed, error in results:
        if name == "k9b-scheduler":
            if not passed and error:
                print("  PASS: Correctly detected violation")
                print(f"  Error: {error}")
                test1_passed = True
            else:
                print(f"  FAIL: Should have detected violation but got passed={passed}")
                all_passed = False
    
    if not test1_passed:
        print("  FAIL: Bad fixture (no affinity) not correctly detected")
        all_passed = False
    
    print()
    
    # BAD fixture: scheduler has soft/preferred affinity only
    print("=== Test 2: BAD fixture (scheduler has preferred affinity only) should FAIL ===")
    bad_preferred = backend_yaml + """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-scheduler
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: k9b
      app.kubernetes.io/component: scheduler
  template:
    metadata:
      labels:
        app.kubernetes.io/name: k9b
        app.kubernetes.io/component: scheduler
    spec:
      containers:
        - name: scheduler
          image: k9b:latest
      volumes:
        - name: runs
          persistentVolumeClaim:
            claimName: k9b-runs
      affinity:
        podAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app.kubernetes.io/name: k9b
                    app.kubernetes.io/component: backend
                topologyKey: kubernetes.io/hostname
"""
    docs = parse_yaml_documents(bad_preferred)
    results, _, _ = verify_manifests(docs)
    
    test2_passed = False
    for name, passed, error in results:
        if name == "k9b-scheduler":
            if not passed and error:
                print("  PASS: Correctly detected violation")
                print(f"  Error: {error}")
                test2_passed = True
            else:
                print(f"  FAIL: Should have detected violation but got passed={passed}")
                all_passed = False
    
    if not test2_passed:
        print("  FAIL: Bad fixture (preferred affinity) not correctly detected")
        all_passed = False
    
    print()
    
    # BAD fixture: scheduler affinity uses zone topology
    print("=== Test 3: BAD fixture (scheduler uses zone topology) should FAIL ===")
    bad_zone = backend_yaml + """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-scheduler
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: k9b
      app.kubernetes.io/component: scheduler
  template:
    metadata:
      labels:
        app.kubernetes.io/name: k9b
        app.kubernetes.io/component: scheduler
    spec:
      containers:
        - name: scheduler
          image: k9b:latest
      volumes:
        - name: runs
          persistentVolumeClaim:
            claimName: k9b-runs
      affinity:
        podAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchLabels:
                  app.kubernetes.io/name: k9b
                  app.kubernetes.io/component: backend
              topologyKey: topology.kubernetes.io/zone
"""
    docs = parse_yaml_documents(bad_zone)
    results, _, _ = verify_manifests(docs)
    
    test3_passed = False
    for name, passed, error in results:
        if name == "k9b-scheduler":
            if not passed and error:
                print("  PASS: Correctly detected violation")
                print(f"  Error: {error}")
                test3_passed = True
            else:
                print(f"  FAIL: Should have detected violation but got passed={passed}")
                all_passed = False
    
    if not test3_passed:
        print("  FAIL: Bad fixture (zone topology) not correctly detected")
        all_passed = False
    
    print()
    
    # GOOD fixture: scheduler has required backend pod affinity on hostname
    print("=== Test 4: GOOD fixture (scheduler has required pod affinity) should PASS ===")
    good_affinity = backend_yaml + """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-scheduler
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: k9b
      app.kubernetes.io/component: scheduler
  template:
    metadata:
      labels:
        app.kubernetes.io/name: k9b
        app.kubernetes.io/component: scheduler
    spec:
      containers:
        - name: scheduler
          image: k9b:latest
      volumes:
        - name: runs
          persistentVolumeClaim:
            claimName: k9b-runs
      affinity:
        podAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchLabels:
                  app.kubernetes.io/name: k9b
                  app.kubernetes.io/instance: RELEASE_NAME
                  app.kubernetes.io/component: backend
              topologyKey: kubernetes.io/hostname
"""
    docs = parse_yaml_documents(good_affinity)
    results, _, _ = verify_manifests(docs)
    
    test4_passed = False
    for name, passed, error in results:
        if name == "k9b-scheduler":
            if passed:
                print("  PASS: Correctly allowed required pod affinity")
                test4_passed = True
            else:
                print(f"  FAIL: Should have passed but got error: {error}")
                all_passed = False
    
    if not test4_passed:
        print("  FAIL: Good fixture not correctly allowed")
        all_passed = False
    
    print()
    
    # GOOD fixture: deployment doesn't share PVC
    print("=== Test 5: GOOD fixture (deployment doesn't share PVC) should PASS ===")
    good_no_share = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-frontend
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: k9b
      app.kubernetes.io/component: frontend
  template:
    metadata:
      labels:
        app.kubernetes.io/name: k9b
        app.kubernetes.io/component: frontend
    spec:
      containers:
        - name: frontend
          image: k9b:latest
"""
    docs = parse_yaml_documents(good_no_share)
    results, _, _ = verify_manifests(docs)
    
    test5_passed = False
    for name, passed, error in results:
        if name == "k9b-frontend":
            if passed:
                print("  PASS: Correctly allowed non-shared PVC deployment")
                test5_passed = True
            else:
                print(f"  FAIL: Should have passed but got error: {error}")
                all_passed = False
    
    if not test5_passed:
        print("  FAIL: Non-shared fixture not correctly allowed")
        all_passed = False
    
    print()
    
    # BAD fixture: required hostname affinity targets frontend instead of backend
    print("=== Test 6: BAD fixture (affinity targets frontend, not backend) should FAIL ===")
    bad_wrong_target = backend_yaml + """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-scheduler
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: k9b
      app.kubernetes.io/component: scheduler
  template:
    metadata:
      labels:
        app.kubernetes.io/name: k9b
        app.kubernetes.io/component: scheduler
    spec:
      containers:
        - name: scheduler
          image: k9b:latest
      volumes:
        - name: runs
          persistentVolumeClaim:
            claimName: k9b-runs
      affinity:
        podAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchLabels:
                  app.kubernetes.io/name: k9b
                  app.kubernetes.io/component: frontend
              topologyKey: kubernetes.io/hostname
"""
    docs = parse_yaml_documents(bad_wrong_target)
    results, _, _ = verify_manifests(docs)
    
    test6_passed = False
    for name, passed, error in results:
        if name == "k9b-scheduler":
            if not passed and error and "app.kubernetes.io/component=backend" in error:
                print("  PASS: Correctly detected wrong target")
                print(f"  Error: {error}")
                test6_passed = True
            else:
                print(f"  FAIL: Should have detected wrong target but got passed={passed}")
                all_passed = False
    
    if not test6_passed:
        print("  FAIL: Bad fixture (wrong target) not correctly detected")
        all_passed = False
    
    print()
    
    # BAD fixture: required hostname affinity omits component label
    print("=== Test 7: BAD fixture (affinity omits component label) should FAIL ===")
    bad_missing_component = backend_yaml + """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-scheduler
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: k9b
      app.kubernetes.io/component: scheduler
  template:
    metadata:
      labels:
        app.kubernetes.io/name: k9b
        app.kubernetes.io/component: scheduler
    spec:
      containers:
        - name: scheduler
          image: k9b:latest
      volumes:
        - name: runs
          persistentVolumeClaim:
            claimName: k9b-runs
      affinity:
        podAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchLabels:
                  app.kubernetes.io/name: k9b
              topologyKey: kubernetes.io/hostname
"""
    docs = parse_yaml_documents(bad_missing_component)
    results, _, _ = verify_manifests(docs)
    
    test7_passed = False
    for name, passed, error in results:
        if name == "k9b-scheduler":
            if not passed and error and "app.kubernetes.io/component=backend" in error:
                print("  PASS: Correctly detected missing component label")
                print(f"  Error: {error}")
                test7_passed = True
            else:
                print(f"  FAIL: Should have detected missing component but got passed={passed}")
                all_passed = False
    
    if not test7_passed:
        print("  FAIL: Bad fixture (missing component) not correctly detected")
        all_passed = False
    
    print()
    
    # GOOD fixture: required hostname affinity targets backend with all labels
    # This test proves the instance-label matching path since backend fixture has instance
    print("=== Test 8: GOOD fixture (affinity targets backend with name/component/instance) should PASS ===")
    good_full_affinity = backend_yaml + """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: k9b-scheduler
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app.kubernetes.io/name: k9b
      app.kubernetes.io/component: scheduler
  template:
    metadata:
      labels:
        app.kubernetes.io/name: k9b
        app.kubernetes.io/component: scheduler
    spec:
      containers:
        - name: scheduler
          image: k9b:latest
      volumes:
        - name: runs
          persistentVolumeClaim:
            claimName: k9b-runs
      affinity:
        podAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchLabels:
                  app.kubernetes.io/name: k9b
                  app.kubernetes.io/instance: RELEASE_NAME
                  app.kubernetes.io/component: backend
              topologyKey: kubernetes.io/hostname
"""
    docs = parse_yaml_documents(good_full_affinity)
    results, _, _ = verify_manifests(docs)
    
    test8_passed = False
    for name, passed, error in results:
        if name == "k9b-scheduler":
            if passed:
                print("  PASS: Correctly allowed full backend affinity")
                test8_passed = True
            else:
                print(f"  FAIL: Should have passed but got error: {error}")
                all_passed = False
    
    if not test8_passed:
        print("  FAIL: Good fixture (full affinity) not correctly allowed")
        all_passed = False
    
    print()
    
    if all_passed:
        print("SELF-TEST: PASSED")
        return True
    else:
        print("SELF-TEST: FAILED")
        return False


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
    
    # Render Helm templates
    import subprocess
    
    print("Rendering Helm templates...")
    result = subprocess.run(
        ["helm", "template", "k9b", str(chart_dir)],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        print(f"ERROR: helm template failed: {result.stderr}", file=sys.stderr)
        return 1
    
    # Verify rendered manifests
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
