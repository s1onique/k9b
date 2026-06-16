"""Self-tests for CI gate drift verifier."""

from __future__ import annotations

from pathlib import Path

from ci_gate_drift_checks import check_allowlist_entry, verify_gate_mapping
from ci_gate_drift_manifest import load_manifest, validate_manifest
from ci_gate_drift_parser import (
    compare_gate_ids,
    extract_jobs_from_workflow,
    parse_verify_all_gate_ids,
)

REPO_ROOT = Path(__file__).parent.parent.resolve()
MANIFEST_PATH = REPO_ROOT / "scripts" / "ci_gate_mapping.json"
DEFAULT_WORKFLOWS = [
    ".github/workflows/harbor.yml",
    ".github/workflows/verify.yml",
    ".github/workflows/helm-chart.yml",
]


def run_self_tests() -> int:
    """Run self-test fixtures. Returns exit code (0 = all pass, non-zero = failures)."""
    print("=== CI Gate Drift Verifier Self-Tests ===\n")

    failures = []
    passes = []

    # Test 1: Valid manifest loads correctly
    print("Test 1: Valid manifest loads correctly")
    try:
        manifest = load_manifest(MANIFEST_PATH)
        passes.append("Test 1: Manifest loads correctly")
    except Exception as e:
        failures.append(f"Test 1: Failed to load manifest: {e}")
        print(f"  FAIL: {e}\n")
        return 1

    # Test 2: Manifest validation passes
    print("Test 2: Manifest validation")
    errors = validate_manifest(manifest)
    if errors:
        failures.append(f"Test 2: Manifest validation errors: {errors}")
        print(f"  FAIL: {errors}\n")
    else:
        passes.append("Test 2: Manifest validation passes")
        print("  PASS\n")

    # Test 3: All required gates have mappings
    print("Test 3: All required gates have mappings")
    required_gates = manifest.get("required_gates", {})
    missing_mappings = []
    for gate_id, gate_config in required_gates.items():
        if not gate_config.get("ci_equivalent"):
            missing_mappings.append(gate_id)
    if missing_mappings:
        failures.append(f"Test 3: Gates missing ci_equivalent: {missing_mappings}")
        print(f"  FAIL: {missing_mappings}\n")
    else:
        passes.append("Test 3: All gates have ci_equivalent")
        print("  PASS\n")

    # Test 4: All allowlist entries have sufficient reasons
    print("Test 4: Allowlist entries have sufficient reasons")
    allowlist = manifest.get("allowlist", [])
    bad_allowlist = []
    for entry in allowlist:
        reason = entry.get("reason", "")
        if len(reason.strip()) < 10:
            bad_allowlist.append(entry.get("gate", "unknown"))
    if bad_allowlist:
        failures.append(f"Test 4: Allowlist entries with bad reasons: {bad_allowlist}")
        print(f"  FAIL: {bad_allowlist}\n")
    else:
        passes.append("Test 4: All allowlist entries valid")
        print("  PASS\n")

    # Test 5: Workflow files exist
    print("Test 5: Workflow files exist")
    workflows = manifest.get("workflows_to_check", DEFAULT_WORKFLOWS)
    missing_workflows = []
    for wf in workflows:
        wf_path = REPO_ROOT / wf
        if not wf_path.exists():
            missing_workflows.append(wf)
    if missing_workflows:
        failures.append(f"Test 5: Missing workflow files: {missing_workflows}")
        print(f"  FAIL: {missing_workflows}\n")
    else:
        passes.append("Test 5: All workflow files exist")
        print("  PASS\n")

    # Test 6: Parse workflow and extract jobs
    print("Test 6: Workflow parsing")
    harbor_yml = REPO_ROOT / ".github/workflows/harbor.yml"
    if harbor_yml.exists():
        with open(harbor_yml, encoding="utf-8") as f:
            content = f.read()
        jobs = extract_jobs_from_workflow(content)
        if "lint-policy" in jobs:
            passes.append("Test 6: Workflow parsing works")
            print("  PASS\n")
        else:
            failures.append("Test 6: Failed to extract jobs from harbor.yml")
            print("  FAIL: No jobs extracted\n")
    else:
        failures.append("Test 6: harbor.yml not found")
        print("  FAIL: harbor.yml not found\n")

    # Test 7: Check unit-tests shard mapping
    print("Test 7: unit-tests shard mapping")
    unit_tests_config = required_gates.get("unit-tests", {})
    if unit_tests_config.get("shard_required") and unit_tests_config.get(
        "shard_union_required"
    ):
        passes.append("Test 7: unit-tests has shard requirements")
        print("  PASS\n")
    else:
        failures.append("Test 7: unit-tests missing shard requirements")
        print("  FAIL\n")

    # Test 8: Check frontend test command mapping
    print("Test 8: npm-test-ui command mapping")
    npm_test_config = required_gates.get("npm-test-ui", {})
    fragments = npm_test_config.get("required_command_fragments", [])
    if "npm run test:ui" in fragments:
        passes.append("Test 8: npm-test-ui has correct command fragment")
        print("  PASS\n")
    else:
        failures.append("Test 8: npm-test-ui missing 'npm run test:ui' fragment")
        print("  FAIL\n")

    # Test 9: Check helm-chart command mapping
    print("Test 9: helm-chart command mapping")
    helm_config = required_gates.get("helm-chart", {})
    fragments = helm_config.get("required_command_fragments", [])
    if "verify_helm_chart.sh" in fragments:
        passes.append("Test 9: helm-chart has correct command fragment")
        print("  PASS\n")
    else:
        failures.append("Test 9: helm-chart missing 'verify_helm_chart.sh' fragment")
        print("  FAIL\n")

    # Test 10: Check allowlist entry validation
    print("Test 10: Allowlist entry validation")
    if allowlist:
        valid, msg, errs = check_allowlist_entry(allowlist[0], manifest)
        if valid:
            passes.append("Test 10: Allowlist entry validation works")
            print("  PASS\n")
        else:
            failures.append(f"Test 10: Allowlist validation failed: {errs}")
            print(f"  FAIL: {errs}\n")
    else:
        passes.append("Test 10: No allowlist entries to validate (SKIP)")
        print("  SKIP: No allowlist entries\n")

    # Test 11: Negative fixture - missing command fragment fails
    print("Test 11: Negative fixture - missing command fragment fails")
    fake_jobs = {
        "fake-job": {
            "commands": ["some command"],
            "has_needs": False,
            "raw_content": "fake-job:\n  commands: []",
        }
    }
    fake_config = {
        "ci_equivalent": ["fake-job"],
        "required_command_fragments": ["nonexistent-command-xyz"],
        "reason": "test",
    }
    passed, msg, errors = verify_gate_mapping(
        "fake-gate", fake_config, fake_jobs, fake_jobs
    )
    if not passed and "not found in CI" in errors[0]:
        passes.append("Test 11: Missing command fragment correctly fails")
        print("  PASS\n")
    else:
        failures.append("Test 11: Should fail on missing command fragment")
        print(f"  FAIL: expected failure, got {passed}\n")

    # Test 12: Negative fixture - missing CI job fails
    print("Test 12: Negative fixture - missing CI job fails")
    fake_config2 = {
        "ci_equivalent": ["nonexistent-job-xyz"],
        "required_command_fragments": ["some-command"],
        "reason": "test",
    }
    passed, msg, errors = verify_gate_mapping(
        "fake-gate2", fake_config2, fake_jobs, fake_jobs
    )
    if not passed and "no matching CI job" in errors[0]:
        passes.append("Test 12: Missing CI job correctly fails")
        print("  PASS\n")
    else:
        failures.append("Test 12: Should fail on missing CI job")
        print(f"  FAIL: expected failure, got {passed}\n")

    # Test 13: Negative fixture - allowlist without reason fails
    print("Test 13: Negative fixture - allowlist without reason fails")
    fake_entry = {
        "gate": "test-gate",
        "workflow": ".github/workflows/verify.yml",
        "reason": "x",
    }
    valid, msg, errors = check_allowlist_entry(fake_entry, manifest)
    if not valid and "insufficient reason" in errors[0]:
        passes.append("Test 13: Allowlist without sufficient reason correctly fails")
        print("  PASS\n")
    else:
        failures.append("Test 13: Should fail on insufficient allowlist reason")
        print(f"  FAIL: expected failure, got {valid}\n")

    # Test 14: Negative fixture - stale allowlist (unknown gate) fails
    print("Test 14: Negative fixture - stale allowlist (unknown gate) fails")
    fake_entry2 = {
        "gate": "nonexistent-gate-xyz",
        "workflow": ".github/workflows/verify.yml",
        "reason": "this is a test reason",
    }
    valid, msg, errors = check_allowlist_entry(fake_entry2, manifest)
    if not valid and "unknown gate" in errors[0]:
        passes.append("Test 14: Stale allowlist (unknown gate) correctly fails")
        print("  PASS\n")
    else:
        failures.append("Test 14: Should fail on stale allowlist entry")
        print(f"  FAIL: expected failure, got {valid}\n")

    # Test 15: Negative fixture - verify_all.sh gate not in manifest fails
    print("Test 15: Negative fixture - verify_all.sh gate not in manifest fails")
    fake_verify_all = '''
_run_and_record "python" "new-gate-xyz" "message"
'''
    fake_verify_path = REPO_ROOT / "scripts" / "fake_verify_all.sh"
    fake_verify_path.write_text(fake_verify_all)
    try:
        gate_ids = parse_verify_all_gate_ids(fake_verify_path)
        manifest_gates = {"existing-gate"}
        missing, extra = compare_gate_ids(gate_ids, manifest_gates, set())
        if "new-gate-xyz" in missing:
            passes.append("Test 15: New verify_all gate not in manifest correctly detected")
            print("  PASS\n")
        else:
            failures.append("Test 15: Should detect gate in verify_all but not manifest")
            print(f"  FAIL: expected 'new-gate-xyz' in missing, got {missing}\n")
    finally:
        fake_verify_path.unlink()

    # Test 16: Negative fixture - shard matrix without shard union fails
    print("Test 16: Negative fixture - shard matrix without shard union fails")
    fake_jobs_with_matrix = {
        "python-unit-tests": {
            "commands": ["scripts/run_unit_tests.sh --shard 0 2"],
            "has_needs": False,
            "raw_content": """python-unit-tests:
  strategy:
    matrix:
      shard_index: [0, 1]
      shard_total: [2]
  steps:
    - run: scripts/run_unit_tests.sh --shard 0 2
""",
        }
    }
    fake_config_shard = {
        "ci_equivalent": ["python-unit-tests"],
        "required_command_fragments": ["run_unit_tests.sh --shard"],
        "shard_required": True,
        "shard_union_required": True,
        "reason": "test",
    }
    passed, msg, errors = verify_gate_mapping(
        "unit-tests", fake_config_shard, fake_jobs_with_matrix, fake_jobs_with_matrix
    )
    if not passed and "shard union verifier" in errors[0]:
        passes.append("Test 16: Shard matrix without union correctly fails")
        print("  PASS\n")
    else:
        failures.append("Test 16: Should fail on shard matrix without union")
        print(f"  FAIL: expected failure, got {passed}\n")

    # Test 17: Negative fixture - canonical workflow missing gate should fail
    # harbor.yml is the ONLY canonical push workflow
    print("Test 17: Negative fixture - canonical workflow missing gate fails")
    # harbor.yml is missing npm-test-ui
    harbor_jobs = {
        "frontend-tests": {
            "commands": ["npm ci", "npm run build"],
            "has_needs": False,
            "raw_content": "frontend-tests:\n  steps:\n    - run: npm ci\n    - run: npm run build",
        }
    }
    # verify.yml has npm-test-ui (but this doesn't matter for push gates)
    verify_jobs = {
        "frontend-tests": {
            "commands": ["npm ci", "npm run test:ui", "npm run build"],
            "has_needs": False,
            "raw_content": "frontend-tests:\n  steps:\n    - run: npm ci\n    - run: npm run test:ui\n    - run: npm run build",
        }
    }
    fake_config_frontend = {
        "ci_equivalent": ["frontend-tests"],
        "required_command_fragments": ["npm run test:ui"],
        "reason": "test",
    }

    # Simulate the orchestrator logic: harbor.yml is the ONLY canonical workflow
    CANONICAL_WORKFLOWS = {
        ".github/workflows/harbor.yml",
    }
    workflow_jobs = {
        ".github/workflows/harbor.yml": harbor_jobs,
        ".github/workflows/verify.yml": verify_jobs,
    }
    all_jobs = {}
    all_jobs.update(harbor_jobs)
    all_jobs.update(verify_jobs)

    gate_passed = True
    for wf in CANONICAL_WORKFLOWS:
        jobs = workflow_jobs[wf]
        passed, msg, errors = verify_gate_mapping(
            "npm-test-ui", fake_config_frontend, jobs, all_jobs
        )
        if not passed:
            gate_passed = False
            break

    if not gate_passed:
        passes.append("Test 17: Canonical workflow missing gate correctly fails")
        print("  PASS\n")
    else:
        failures.append("Test 17: Should fail when canonical workflow is missing gate")
        print(f"  FAIL: expected failure, got {gate_passed}\n")

    # Summary
    print("=== Self-Test Summary ===")
    print(f"Passed: {len(passes)}")
    print(f"Failed: {len(failures)}")

    if failures:
        print("\nFailures:")
        for f in failures:
            print(f"  - {f}")
        return 2

    print("\nVERIFICATION PASSED: All self-tests passed")
    return 0
