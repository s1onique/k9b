#!/usr/bin/env python3
"""CI Gate Drift Verifier - CLI orchestrator.

Verifies that required verification gates from scripts/verify_all.sh
are represented in GitHub Actions workflows.

Usage:
    python scripts/verify_ci_gate_drift.py              # Run verification
    python scripts/verify_ci_gate_drift.py --self-test  # Run self-tests
    python scripts/verify_ci_gate_drift.py --verbose    # Verbose output

Exit codes:
    0 - All gates verified (PASS)
    1 - Verification failed (FAIL)
    2 - Self-test failed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ci_gate_drift_checks import check_allowlist_entry, verify_gate_mapping
from ci_gate_drift_manifest import load_manifest, validate_manifest
from ci_gate_drift_parser import (
    compare_gate_ids,
    extract_jobs_from_workflow,
    parse_verify_all_gate_ids,
)
from ci_gate_drift_selftest import run_self_tests

REPO_ROOT = Path(__file__).parent.parent.resolve()
MANIFEST_PATH = REPO_ROOT / "scripts" / "ci_gate_mapping.json"
DEFAULT_WORKFLOWS = [
    ".github/workflows/harbor.yml",
    ".github/workflows/verify.yml",
    ".github/workflows/helm-chart.yml",
]


def verify_workflow_exists(workflow_path: Path) -> tuple[bool, str]:
    """Check if a workflow file exists."""
    if workflow_path.exists():
        return True, f"OK: {workflow_path}"
    return False, f"MISSING: {workflow_path}"


def run_verification(verbose: bool = False) -> int:
    """Run the main verification. Returns exit code."""
    print("=== CI Gate Drift Verification ===\n")

    # Load manifest
    try:
        manifest = load_manifest(MANIFEST_PATH)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 1
    except Exception as e:
        print(f"ERROR: Invalid manifest: {e}")
        return 1

    # Validate manifest
    manifest_errors = validate_manifest(manifest)
    if manifest_errors:
        print("ERROR: Manifest validation failed:")
        for err in manifest_errors:
            print(f"  - {err}")
        return 1

    # Parse verify_all.sh gate IDs and compare with manifest
    verify_all_path = REPO_ROOT / "scripts" / "verify_all.sh"
    verify_all_gates = parse_verify_all_gate_ids(verify_all_path)
    manifest_gates = set(manifest.get("required_gates", {}).keys())
    explicit_extras = {"ci-gate-drift"}

    missing_in_manifest, extra_in_manifest = compare_gate_ids(
        verify_all_gates, manifest_gates, explicit_extras
    )

    all_passed = True

    if missing_in_manifest:
        print("ERROR: Gates in verify_all.sh but not in manifest:")
        for gate_id in missing_in_manifest:
            print(f"  - {gate_id}")
        print()
        all_passed = False

    if extra_in_manifest:
        print("ERROR: Gates in manifest but not in verify_all.sh (stale):")
        for gate_id in extra_in_manifest:
            print(f"  - {gate_id}")
        print()
        all_passed = False

    # Load workflow files
    workflows_to_check = manifest.get("workflows_to_check", DEFAULT_WORKFLOWS)
    workflow_contents = {}
    workflow_jobs = {}

    print("Workflow files checked:")
    for wf in workflows_to_check:
        wf_path = REPO_ROOT / wf
        exists, msg = verify_workflow_exists(wf_path)
        print(f"  - {msg}")
        if exists:
            with open(wf_path, encoding="utf-8") as f:
                workflow_contents[wf] = f.read()
            workflow_jobs[wf] = extract_jobs_from_workflow(workflow_contents[wf])

    print()

    # Combine all jobs across workflows
    all_jobs = {}
    for wf_jobs in workflow_jobs.values():
        all_jobs.update(wf_jobs)

    # Verify each gate
    required_gates = manifest.get("required_gates", {})
    allowlist = manifest.get("allowlist", [])

    # Canonical workflow that must have every gate
    # harbor.yml is the canonical push workflow; verify.yml is PR/manual-only
    CANONICAL_WORKFLOWS = {
        ".github/workflows/harbor.yml",
    }

    print("Gate mappings:")
    gate_results = []

    for gate_id, gate_config in sorted(required_gates.items()):
        gate_passed = True
        gate_errors = []

        # Verify EVERY canonical workflow independently - ALL must pass
        for wf in CANONICAL_WORKFLOWS:
            if wf not in workflow_jobs:
                all_passed = False
                gate_passed = False
                gate_errors.append(f"{wf}: missing workflow")
                print(f"  FAIL {gate_id} in {wf}: missing workflow")
                continue

            # Check if this gate is allowlisted for this specific workflow
            is_allowlisted_for_wf = False
            for entry in allowlist:
                if entry.get("gate") == gate_id and entry.get("workflow") == wf:
                    is_allowlisted_for_wf = True
                    break

            if is_allowlisted_for_wf:
                print(f"  ALLOWLISTED {gate_id} in {wf}")
                continue

            jobs = workflow_jobs[wf]
            passed, msg, errors = verify_gate_mapping(
                gate_id, gate_config, jobs, all_jobs, workflow_path=wf
            )

            if passed:
                print(f"  PASS {gate_id} in {wf}")
            else:
                all_passed = False
                gate_passed = False
                err_msg = errors[0] if errors else "No CI equivalent found"
                gate_errors.append(f"{wf}: {err_msg}")
                print(f"  FAIL {gate_id} in {wf}: {err_msg}")

        # Non-canonical workflows are only checked if canonical workflows passed
        # They cannot rescue canonical failures
        if not gate_passed:
            print(f"  FAIL {gate_id}: failed in canonical workflows")

        gate_results.append((gate_id, gate_passed, gate_errors))

    print()

    # Verify allowlist entries
    print("Allowlist entries:")
    stale_allowlist = []
    for entry in allowlist:
        valid, msg, errors = check_allowlist_entry(entry, manifest)
        if valid:
            print(f"  OK: {entry.get('gate')} -> {entry.get('workflow')}")
        else:
            stale_allowlist.append((entry, errors))
            print(f"  STALE: {entry.get('gate')} - {errors[0] if errors else 'Unknown error'}")

    print()

    # Summary
    passed_count = sum(1 for _, passed, _ in gate_results if passed)
    failed_count = len(gate_results) - passed_count

    print("=== Summary ===")
    print(f"Required local gates: {len(required_gates)}")
    print(f"Workflow files checked: {len(workflow_contents)}")
    print(f"Gate mappings: {passed_count} passed, {failed_count} failed")
    print(f"Stale allowlist entries: {len(stale_allowlist)}")

    if stale_allowlist:
        print("\nStale allowlist entries:")
        for entry, errors in stale_allowlist:
            print(f"  - {entry.get('gate')}: {errors[0] if errors else 'Unknown error'}")

    if not all_passed:
        print("\n=== FAILURES ===")
        for gate_id, passed, errors in gate_results:
            if not passed:
                print(f"ERROR: Required gate '{gate_id}' is not properly represented in CI")
                for err in errors:
                    print(f"  - {err}")

    print()

    if all_passed and not stale_allowlist:
        print("VERIFICATION PASSED")
        return 0
    print("VERIFICATION FAILED")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify CI workflow/gate drift.")
    parser.add_argument("--self-test", action="store_true", help="Run self-test fixtures")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.self_test:
        return run_self_tests()
    return run_verification(verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
