"""Self-test fixtures for docs_claim_traceability verifier.

Contains self-test cases and runner.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from docs_claim_traceability_loader import read_matrix, read_registry

SELF_TEST_CASES: list[dict[str, object]] = [
    {
        "name": "valid minimal traceability matrix passes",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Test trace\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": False,
    },
    {
        "name": "duplicate trace ID fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,First\n"
            "DOC-TRACE-0001,DOC-CLAIM-0002,verifier,test_ref2,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Duplicate\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
            "DOC-CLAIM-0002,README.md,test-anchor2,Second claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "Duplicate trace_id",
    },
    {
        "name": "malformed trace ID fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-1,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Bad ID\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "does not match pattern",
    },
    {
        "name": "unsorted trace IDs fail",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0002,DOC-CLAIM-0002,verifier,test_ref2,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Second\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,First\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,First claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
            "DOC-CLAIM-0002,README.md,test-anchor2,Second claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "not sorted ascending",
    },
    {
        "name": "unknown claim ID fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-9999,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Unknown claim\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "not in docs_claims_registry",
    },
    {
        "name": "missing required claim trace fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0002,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Only second\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,First claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
            "DOC-CLAIM-0002,README.md,test-anchor2,Second claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "evidence_required=true but is not in traceability matrix",
    },
    {
        "name": "linked claim referencing unknown trace ID fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Test trace\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,linked,DOC-TRACE-9999,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "references unknown trace_id",
    },
    {
        "name": "invalid evidence_kind fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,invalid_kind,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Bad kind\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "invalid evidence_kind",
    },
    {
        "name": "evidence_kind=none with direct coverage fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,none,,,,,direct,verified,2026-06-19,Bad combo\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "coverage_strength='direct' but evidence_kind='none'",
    },
    {
        "name": "verified trace with coverage_strength=none fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,none,verified,2026-06-19,Bad combo\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "verification_status='verified' but coverage_strength='none'",
    },
    {
        "name": "manual_only without notes fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,manual_lab,manual_test,,,gate_name,manual,manual_only,2026-06-19,\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "manual_only verification requires meaningful notes",
    },
    {
        "name": "duplicate (claim_id, evidence_kind, evidence_ref) fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,First\n"
            "DOC-TRACE-0002,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Duplicate\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "Duplicate (claim_id, evidence_kind, evidence_ref)",
    },
    {
        "name": "malformed CSV header fails",
        "matrix": (
            "trace_id,bad_header,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Bad header\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "CSV header must match",
    },
]


def run_self_test() -> bool:
    """Run self-test mode with inline fixture cases."""
    print("=== Docs Claim Traceability Self-Test ===\n")

    all_passed = True

    for i, case in enumerate(SELF_TEST_CASES):
        print(f"Test case {i + 1}: {case['name']}")

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            tmp_matrix = tmp_path / "docs" / "claims" / "docs_claim_traceability_matrix.csv"
            tmp_matrix.parent.mkdir(parents=True, exist_ok=True)

            tmp_registry = tmp_path / "docs" / "claims" / "docs_claims_registry.csv"
            tmp_registry.parent.mkdir(parents=True, exist_ok=True)

            # Write matrix
            tmp_matrix.write_text(str(case["matrix"]))

            # Write registry
            tmp_registry.write_text(str(case["registry"]))

            # Write gate mapping
            gate_mapping_path = tmp_path / "scripts" / "ci_gate_mapping.json"
            gate_mapping_path.parent.mkdir(parents=True, exist_ok=True)
            gate_mapping = case.get("gate_mapping", {"required_gates": {}})
            gate_mapping_path.write_text(json.dumps(gate_mapping))

            # Create referenced files
            for line in str(case["matrix"]).strip().split("\n")[1:]:
                parts = line.split(",")
                if len(parts) >= 5:
                    evidence_path = parts[4].strip()
                    if evidence_path and evidence_path not in ("", "none"):
                        f = tmp_path / evidence_path
                        f.parent.mkdir(parents=True, exist_ok=True)
                        f.write_text("# Test file\n")

            # Override paths for this test
            import docs_claim_traceability_contract as contract_module
            import docs_claim_traceability_loader as loader_module

            old_matrix = contract_module.MATRIX_CSV
            old_registry = contract_module.REGISTRY_CSV
            old_gate_mapping = contract_module.CI_GATE_MAPPING
            old_repo_root = contract_module.REPO_ROOT

            contract_module.MATRIX_CSV = tmp_matrix
            contract_module.REGISTRY_CSV = tmp_registry
            contract_module.CI_GATE_MAPPING = gate_mapping_path
            contract_module.REPO_ROOT = tmp_path
            loader_module.MATRIX_CSV = tmp_matrix
            loader_module.REGISTRY_CSV = tmp_registry
            loader_module.CI_GATE_MAPPING = gate_mapping_path

            try:
                from docs_claim_traceability_rules import get_all_checks

                rows, error = read_matrix()

                if error and case["should_fail"]:
                    print(f"  [OK] Failed to parse as expected: {error}")
                    continue

                if error and not case["should_fail"]:
                    print(f"  [UNEXPECTED] Parse error: {error}")
                    all_passed = False
                    continue

                registry_rows, _ = read_registry()
                gate_mapping_data, _ = loader_module.read_ci_gate_mapping()

                checks_results = get_all_checks(rows, registry_rows, gate_mapping_data)

                all_errors: list[str] = []
                any_failed = False
                for name, result in checks_results:
                    all_errors.extend(result.errors)
                    if not result.passed:
                        any_failed = True

                expected_fail = bool(case["should_fail"])
                expect_contains = case.get("expect_error_contains", "")

                if expected_fail:
                    if any_failed:
                        if expect_contains:
                            found = any(expect_contains.lower() in e.lower() for e in all_errors)
                            if found:
                                print("  [OK] Failed as expected with matching error")
                            else:
                                print("  [PARTIAL] Failed but error mismatch:")
                                for e in all_errors:
                                    print(f"         {e}")
                                all_passed = False
                        else:
                            print("  [OK] Failed as expected")
                    else:
                        print("  [UNEXPECTED PASS] No checks failed")
                        all_passed = False
                else:
                    if not any_failed:
                        print("  [OK] Passed as expected")
                    else:
                        print("  [UNEXPECTED FAIL] Errors:")
                        for e in all_errors:
                            print(f"         {e}")
                        all_passed = False

            finally:
                contract_module.MATRIX_CSV = old_matrix
                contract_module.REGISTRY_CSV = old_registry
                contract_module.CI_GATE_MAPPING = old_gate_mapping
                contract_module.REPO_ROOT = old_repo_root
                loader_module.MATRIX_CSV = old_matrix
                loader_module.REGISTRY_CSV = old_registry
                loader_module.CI_GATE_MAPPING = old_gate_mapping

    print()
    if all_passed:
        print("SELF-TEST: PASSED")
    else:
        print("SELF-TEST: FAILED")

    return all_passed