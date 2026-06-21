"""Self-test fixtures for docs_claims_registry verifier.

Contains all self-test cases and the self-test runner.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from docs_claims_registry_loader import read_inventory_paths, read_registry
from docs_claims_registry_rules import get_all_checks

# Self-test fixtures
SELF_TEST_CASES: list[dict[str, object]] = [
    {
        "name": "valid minimal registry passes",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes,candidate_ids\n"
            "DOC-CLAIM-0001,README.md,test-anchor,This is a test claim with enough length.,"
            "behavior,current,test,true,pending,,on_change,Test claim,\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": False,
    },
    {
        "name": "duplicate claim ID fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,First claim with enough text here.,"
            "behavior,current,test,true,pending,,on_change,First\n"
            "DOC-CLAIM-0001,README.md,test-anchor-2,Second claim with enough text here.,"
            "behavior,current,test,true,pending,,on_change,Duplicate ID\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "Duplicate claim_id",
    },
    {
        "name": "malformed claim ID fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-1,README.md,test-anchor,Claim text with enough length.,"
            "behavior,current,test,true,pending,,on_change,Bad ID\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "does not match pattern",
    },
    {
        "name": "unsorted claim IDs fail",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0002,README.md,test-anchor-2,Second claim with enough text here.,"
            "behavior,current,test,true,pending,,on_change,Second\n"
            "DOC-CLAIM-0001,README.md,test-anchor-1,First claim with enough text here.,"
            "behavior,current,test,true,pending,,on_change,First\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "not sorted ascending",
    },
    {
        "name": "unknown doc path fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,docs/unknown.md,test-anchor,Claim text with enough length.,"
            "behavior,current,test,true,pending,,on_change,Unknown doc\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "not in docs_inventory",
    },
    {
        "name": "invalid claim_type fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Claim text with enough length.,"
            "invalid_type,current,test,true,pending,,on_change,Bad type\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "invalid claim_type",
    },
    {
        "name": "invalid claim_status fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Claim text with enough length.,"
            "behavior,invalid_status,test,true,pending,,on_change,Bad status\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "invalid claim_status",
    },
    {
        "name": "invalid boolean fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Claim text with enough length.,"
            "behavior,current,test,maybe,pending,,on_change,Bad bool\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "not a valid boolean",
    },
    {
        "name": "current claim with unsupported evidence fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Claim text with enough length.,"
            "behavior,current,test,true,unsupported,,on_change,Unsupported\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "current claims must have supported evidence",
    },
    {
        "name": "unsupported current claim combination fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Claim text with enough length.,"
            "behavior,current,test,true,unsupported,,on_change,Combo fail\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "unsupported evidence cannot back current claims",
    },
    {
        "name": "historical claim with wrong freshness policy fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Claim text with enough length.,"
            "behavior,historical,test,false,not_required,,per_release,Wrong freshness\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "historical_only or not_applicable",
    },
    {
        "name": "linked evidence without evidence_ref fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Claim text with enough length.,"
            "behavior,current,test,true,linked,,on_change,Missing ref\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "evidence_ref required for linked",
    },
    {
        "name": "evidence_required=false with non-not_required status fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Claim text with enough length.,"
            "behavior,current,test,false,pending,,on_change,Bad combo\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "expected: not_required",
    },
    {
        "name": "duplicate (doc_path, anchor, claim_text) fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Same claim text here.,"
            "behavior,current,test,true,pending,,on_change,First\n"
            "DOC-CLAIM-0002,README.md,test-anchor,Same claim text here.,"
            "behavior,current,test,true,pending,,on_change,Duplicate\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "Duplicate",
    },
    {
        "name": "empty anchor fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,,Claim text with enough length.,"
            "behavior,current,test,true,pending,,on_change,No anchor\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "anchor is empty",
    },
]


def run_self_test() -> bool:
    """Run self-test mode with inline fixture cases."""
    print("=== Docs Claims Registry Self-Test ===\n")

    all_passed = True

    for i, case in enumerate(SELF_TEST_CASES):
        print(f"Test case {i + 1}: {case['name']}")

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            tmp_registry = tmp_path / "docs" / "claims" / "docs_claims_registry.csv"
            tmp_registry.parent.mkdir(parents=True, exist_ok=True)

            tmp_inventory = tmp_path / "docs" / "docs_inventory.csv"
            tmp_inventory.parent.mkdir(parents=True, exist_ok=True)

            # Write registry
            tmp_registry.write_text(str(case["registry"]))

            # Write inventory
            tmp_inventory.write_text(str(case["inventory"]))

            # Write candidates CSV if fixture provides one
            if "candidates" in case:
                tmp_candidates = tmp_path / "docs" / "claims" / "generated_claim_candidates.csv"
                tmp_candidates.parent.mkdir(parents=True, exist_ok=True)
                tmp_candidates.write_text(str(case["candidates"]))

            # Create all referenced files
            registry_text = str(case["registry"])
            inventory_text = str(case["inventory"])

            # Parse paths from inventory
            for line in inventory_text.strip().split("\n")[1:]:
                parts = line.split(",")
                if parts:
                    doc_path = parts[0].strip()
                    if doc_path:
                        f = tmp_path / doc_path
                        f.parent.mkdir(parents=True, exist_ok=True)
                        f.write_text("# Test file\n")

            # Parse paths from registry
            for line in registry_text.strip().split("\n")[1:]:
                parts = line.split(",")
                if parts:
                    doc_path = parts[1].strip()
                    if doc_path:
                        f = tmp_path / doc_path
                        f.parent.mkdir(parents=True, exist_ok=True)
                        f.write_text("# Test file\n")

            # Override paths for this test
            from docs_claims_registry_contract import INVENTORY_CSV, REGISTRY_CSV
            from docs_claims_registry_contract import REPO_ROOT as CONTRACT_REPO_ROOT
            old_registry = REGISTRY_CSV
            old_inventory = INVENTORY_CSV
            old_repo_root = CONTRACT_REPO_ROOT

            # Patch the module-level variables
            import docs_claims_registry_contract as contract_module
            import docs_claims_registry_loader as loader_module
            
            contract_module.REGISTRY_CSV = tmp_registry
            contract_module.INVENTORY_CSV = tmp_inventory
            contract_module.REPO_ROOT = tmp_path
            loader_module.REGISTRY_CSV = tmp_registry
            loader_module.INVENTORY_CSV = tmp_inventory

            try:
                # Read and run checks
                rows, error = read_registry()

                if error and case["should_fail"]:
                    print(f"  [OK] Failed to parse as expected: {error}")
                    continue

                if error and not case["should_fail"]:
                    print(f"  [UNEXPECTED] Parse error: {error}")
                    all_passed = False
                    continue

                # Read inventory paths
                inventory_paths, _ = read_inventory_paths()

                # Run all checks
                checks_results = get_all_checks(rows, inventory_paths)

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
                # Restore original paths
                contract_module.REGISTRY_CSV = old_registry
                contract_module.INVENTORY_CSV = old_inventory
                contract_module.REPO_ROOT = old_repo_root
                loader_module.REGISTRY_CSV = old_registry
                loader_module.INVENTORY_CSV = old_inventory

    print()
    if all_passed:
        print("SELF-TEST: PASSED")
    else:
        print("SELF-TEST: FAILED")

    return all_passed