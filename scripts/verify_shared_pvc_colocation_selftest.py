#!/usr/bin/env python3
"""
Self-test runner for shared PVC colocation verifier.

Loads fixture files from fixtures/shared_pvc_colocation/ and verifies
that the production verifier produces expected PASS/FAIL results.

Usage:
    python scripts/verify_shared_pvc_colocation_selftest.py
    (or via main verifier: python scripts/verify_shared_pvc_colocation.py --self-test)
"""

from pathlib import Path

# Import production verification functions
from verify_shared_pvc_colocation import (
    parse_yaml_documents,
    verify_manifests,
)

REPO_ROOT = Path(__file__).parent.parent.resolve()
FIXTURE_DIR = REPO_ROOT / "fixtures" / "shared_pvc_colocation"

# Backend deployment fixture (shared PVC partner)
BACKEND_YAML = """
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
"""

# Test cases: (fixture_name, deployment_name, expected_pass, check_error_contains)
TEST_CASES = [
    # Bad fixtures (should FAIL)
    ("bad-no-affinity.yaml", "k9b-scheduler", False, None),
    ("bad-preferred-only.yaml", "k9b-scheduler", False, None),
    ("bad-zone-topology.yaml", "k9b-scheduler", False, "topology.kubernetes.io/zone"),
    ("bad-wrong-target.yaml", "k9b-scheduler", False, "app.kubernetes.io/component=backend"),
    ("bad-missing-component.yaml", "k9b-scheduler", False, "app.kubernetes.io/component=backend"),
    # Selector edge case fixtures (should FAIL with clear diagnostics)
    # Null values are normalized to {} which fails the backend targeting check
    ("bad-null-label-selector.yaml", "k9b-scheduler", False, "app.kubernetes.io/component=backend"),
    ("bad-null-match-labels.yaml", "k9b-scheduler", False, "app.kubernetes.io/component=backend"),
    # Non-dict labelSelector and matchLabels are caught by the type check
    ("bad-non-dict-label-selector.yaml", "k9b-scheduler", False, "not a dict"),
    ("bad-non-dict-match-labels.yaml", "k9b-scheduler", False, "not a dict"),
    # Good fixtures (should PASS)
    ("good-required-affinity.yaml", "k9b-scheduler", True, None),
    ("good-non-shared.yaml", "k9b-frontend", True, None),
    ("good-full-backend-affinity.yaml", "k9b-scheduler", True, None),
]


def load_fixture(fixture_name: str) -> str:
    """Load fixture file content."""
    fixture_path = FIXTURE_DIR / fixture_name
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_path}")
    with open(fixture_path) as f:
        return f.read()


def run_self_test() -> bool:
    """Run self-test mode to prove the verifier works correctly."""
    print("Running self-test mode...")
    print()

    all_passed = True

    for i, (fixture_name, deployment_name, expected_pass, error_contains) in enumerate(TEST_CASES, 1):
        print(f"=== Test {i}: {fixture_name} (expected {'PASS' if expected_pass else 'FAIL'}) ===")

        # Load and combine with backend
        try:
            fixture_content = load_fixture(fixture_name)
        except FileNotFoundError as e:
            print(f"  FAIL: {e}")
            all_passed = False
            print()
            continue

        combined_yaml = BACKEND_YAML + "\n---\n" + fixture_content
        docs = parse_yaml_documents(combined_yaml)
        results, _, _ = verify_manifests(docs)

        test_passed = False
        for name, passed, error in results:
            if name == deployment_name:
                if passed == expected_pass:
                    if error_contains is None or (error and error_contains in error):
                        print(f"  PASS: Correctly returned {passed}")
                        test_passed = True
                    elif error_contains and not error:
                        print(f"  FAIL: Expected error containing '{error_contains}' but no error")
                        all_passed = False
                else:
                    expected = "PASS" if expected_pass else "FAIL"
                    got = "PASS" if passed else "FAIL"
                    print(f"  FAIL: Expected {expected} but got {got}")
                    if error:
                        print(f"  Error: {error}")
                    all_passed = False

        if not test_passed:
            print(f"  FAIL: Fixture {fixture_name} not correctly verified")

        print()

    print()
    if all_passed:
        print("SELF-TEST: PASSED")
        return True
    else:
        print("SELF-TEST: FAILED")
        return False


if __name__ == "__main__":
    import sys

    success = run_self_test()
    sys.exit(0 if success else 1)