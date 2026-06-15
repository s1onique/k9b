#!/usr/bin/env python3
"""
verify_pvc_rollout_policy.py

Verifies that Kubernetes Deployments mounting persistentVolumeClaim volumes
use strategy.type=Recreate to prevent Multi-Attach errors during rollouts.

Policy:
  For each apps/v1 Deployment:
    if spec.template.spec.volumes[*].persistentVolumeClaim exists:
      require spec.strategy.type == "Recreate"
      unless deployment is listed in docs/reference_allowlists/pvc_rolling_update_allowlist.csv

Usage:
  scripts/verify_pvc_rollout_policy.py                    # verify rendered manifests
  scripts/verify_pvc_rollout_policy.py --self-test         # run self-test mode
  scripts/verify_pvc_rollout_policy.py --manifests DIR    # verify directory of YAML files

Self-test mode proves:
  - BAD fixture: PVC Deployment with default RollingUpdate → FAIL
  - GOOD fixture: PVC Deployment with Recreate → PASS
  - ALLOWLISTED fixture: PVC Deployment with RollingUpdate but allowlisted → PASS
"""

import argparse
import csv
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent.resolve()
ALLOWLIST_PATH = REPO_ROOT / "docs" / "reference_allowlists" / "pvc_rolling_update_allowlist.csv"


def load_allowlist(path: Path) -> set[str]:
    """Load deployment names from allowlist CSV."""
    allowlisted: set[str] = set()
    if not path.exists():
        return allowlisted
    
    with open(path) as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or row[0].startswith("#"):
                continue
            if len(row) >= 1 and row[0].strip():
                allowlisted.add(row[0].strip())
    return allowlisted


def parse_yaml_documents(content: str) -> list[dict]:
    """Parse all YAML documents from content string."""
    documents = []
    for doc in yaml.safe_load_all(content):
        if doc is not None:
            documents.append(doc)
    return documents


def check_deployment(doc: dict, allowlisted: set[str]) -> tuple[bool, str | None]:
    """
    Check a single Deployment resource.
    
    Returns:
        (passes, error_message)
        - (True, None) if deployment passes policy
        - (False, error_message) if deployment violates policy
    """
    kind = doc.get("kind", "")
    if kind != "Deployment":
        return True, None  # Skip non-Deployment resources
    
    api_version = doc.get("apiVersion", "")
    if not api_version.startswith("apps/"):
        return True, None  # Skip non-apps/v1 Deployments
    
    metadata = doc.get("metadata", {})
    name = metadata.get("name", "unknown")
    
    spec = doc.get("spec", {})
    template_spec = spec.get("template", {}).get("spec", {})
    
    # Check if any volume mounts a PVC
    volumes = template_spec.get("volumes", [])
    has_pvc = False
    for volume in volumes:
        if "persistentVolumeClaim" in volume:
            has_pvc = True
            break
    
    if not has_pvc:
        return True, None  # No PVC, no policy applies
    
    # PVC found - check strategy
    strategy = spec.get("strategy", {})
    strategy_type = strategy.get("type", "RollingUpdate")  # Default in Kubernetes
    
    if strategy_type == "Recreate":
        return True, None  # Passes policy
    
    # Check allowlist
    if name in allowlisted:
        return True, None  # Explicitly allowlisted
    
    # Violation
    return False, (
        f"Deployment '{name}' mounts a persistentVolumeClaim but uses "
        f"strategy.type='{strategy_type}' (expected 'Recreate'). "
        f"RollingUpdate can cause Multi-Attach errors when old pod hasn't terminated "
        f"before new pod tries to mount the same PVC."
    )


def verify_manifests(manifests: list[dict], allowlisted: set[str]) -> list[tuple[str, bool, str | None]]:
    """
    Verify all manifests.
    
    Returns:
        List of (resource_name, passed, error_message) tuples.
    """
    results = []
    for doc in manifests:
        kind = doc.get("kind", "")
        if kind != "Deployment":
            continue
        
        metadata = doc.get("metadata", {})
        name = metadata.get("name", "unknown")
        
        passed, error = check_deployment(doc, allowlisted)
        results.append((name, passed, error))
    
    return results


def run_self_test() -> bool:
    """Run self-test mode to prove the verifier works correctly."""
    print("Running self-test mode...")
    print()
    
    allowlisted = load_allowlist(ALLOWLIST_PATH)
    # Add test allowlisted deployment
    allowlisted.add("test-allowlisted-deployment")
    
    all_passed = True
    
    # BAD fixture: PVC Deployment with default RollingUpdate
    print("=== Test 1: BAD fixture (RollingUpdate with PVC) should FAIL ===")
    bad_fixture = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-bad-deployment
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test
  template:
    spec:
      containers:
        - name: test
          image: test:latest
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: test-pvc
"""
    bad_docs = parse_yaml_documents(bad_fixture)
    bad_results = verify_manifests(bad_docs, allowlisted)
    
    test1_passed = False
    for name, passed, error in bad_results:
        if name == "test-bad-deployment":
            if not passed and error:
                print("  PASS: Correctly detected violation")
                print(f"  Error: {error}")
                test1_passed = True
            else:
                print(f"  FAIL: Should have detected violation but got passed={passed}")
                all_passed = False
    
    if not test1_passed:
        print("  FAIL: Bad fixture not correctly detected")
        all_passed = False
    
    print()
    
    # GOOD fixture: PVC Deployment with Recreate
    print("=== Test 2: GOOD fixture (Recreate with PVC) should PASS ===")
    good_fixture = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-good-deployment
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: test
  template:
    spec:
      containers:
        - name: test
          image: test:latest
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: test-pvc
"""
    good_docs = parse_yaml_documents(good_fixture)
    good_results = verify_manifests(good_docs, allowlisted)
    
    test2_passed = False
    for name, passed, error in good_results:
        if name == "test-good-deployment":
            if passed:
                print("  PASS: Correctly allowed Recreate strategy")
                test2_passed = True
            else:
                print(f"  FAIL: Should have passed but got error: {error}")
                all_passed = False
    
    if not test2_passed:
        print("  FAIL: Good fixture not correctly allowed")
        all_passed = False
    
    print()
    
    # ALLOWLISTED fixture: PVC Deployment with RollingUpdate but allowlisted
    print("=== Test 3: ALLOWLISTED fixture (RollingUpdate with PVC, allowlisted) should PASS ===")
    allowlisted_fixture = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-allowlisted-deployment
spec:
  replicas: 1
  strategy:
    type: RollingUpdate
  selector:
    matchLabels:
      app: test
  template:
    spec:
      containers:
        - name: test
          image: test:latest
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: test-pvc
"""
    allowlisted_docs = parse_yaml_documents(allowlisted_fixture)
    allowlisted_results = verify_manifests(allowlisted_docs, allowlisted)
    
    test3_passed = False
    for name, passed, error in allowlisted_results:
        if name == "test-allowlisted-deployment":
            if passed:
                print("  PASS: Correctly allowed allowlisted deployment")
                test3_passed = True
            else:
                print(f"  FAIL: Should have passed but got error: {error}")
                all_passed = False
    
    if not test3_passed:
        print("  FAIL: Allowlisted fixture not correctly allowed")
        all_passed = False
    
    print()
    
    # NON-PVC fixture: Deployment without PVC should always pass
    print("=== Test 4: NON-PVC fixture (no PVC) should PASS ===")
    non_pvc_fixture = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-non-pvc-deployment
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test
  template:
    spec:
      containers:
        - name: test
          image: test:latest
"""
    non_pvc_docs = parse_yaml_documents(non_pvc_fixture)
    non_pvc_results = verify_manifests(non_pvc_docs, allowlisted)
    
    test4_passed = False
    for name, passed, error in non_pvc_results:
        if name == "test-non-pvc-deployment":
            if passed:
                print("  PASS: Correctly allowed non-PVC deployment")
                test4_passed = True
            else:
                print(f"  FAIL: Should have passed but got error: {error}")
                all_passed = False
    
    if not test4_passed:
        print("  FAIL: Non-PVC fixture not correctly allowed")
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
    allowlisted = load_allowlist(ALLOWLIST_PATH)
    
    print("==========================================")
    print("PVC Rollout Policy Verification")
    print("==========================================")
    print()
    print(f"Allowlist: {ALLOWLIST_PATH}")
    print(f"Allowlisted deployments: {len(allowlisted)}")
    if allowlisted:
        for name in sorted(allowlisted):
            print(f"  - {name}")
    print()
    
    all_passed = True
    yaml_files = list(manifest_dir.rglob("*.yaml")) + list(manifest_dir.rglob("*.yml"))
    
    if not yaml_files:
        print(f"WARNING: No YAML files found in {manifest_dir}")
        return True  # No files to check is not a failure
    
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
        results = verify_manifests(docs, allowlisted)
        
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
        print()
        print("All Deployments with persistentVolumeClaim volumes use Recreate strategy.")
        return True
    else:
        print("RESULT: FAILED")
        print()
        print("Deployments mounting PVCs must use strategy.type=Recreate.")
        print("Add deployments to allowlist only if they use multi-writer storage (ReadWriteMany).")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify PVC rollout policy for Kubernetes Deployments."
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
    allowlisted = load_allowlist(ALLOWLIST_PATH)
    
    print("==========================================")
    print("PVC Rollout Policy Verification")
    print("==========================================")
    print()
    print(f"Allowlist: {ALLOWLIST_PATH}")
    print(f"Allowlisted deployments: {len(allowlisted)}")
    if allowlisted:
        for name in sorted(allowlisted):
            print(f"  - {name}")
    print()
    
    docs = parse_yaml_documents(result.stdout)
    results = verify_manifests(docs, allowlisted)
    
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
        print("All Deployments with persistentVolumeClaim volumes use Recreate strategy.")
        return 0
    else:
        print("RESULT: FAILED")
        print()
        print("Deployments mounting PVCs must use strategy.type=Recreate.")
        print("Add deployments to allowlist only if they use multi-writer storage (ReadWriteMany).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
