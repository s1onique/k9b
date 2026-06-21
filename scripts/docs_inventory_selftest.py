"""Self-test fixtures for docs_inventory verifier.

Contains self-test cases and runner.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from docs_inventory_loader import read_inventory
from docs_inventory_rules import get_all_checks

# Self-test fixtures
SELF_TEST_CASES: list[dict[str, object]] = [
    {
        "name": "missing inventory row",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,"
            "replacement_doc,claim_trace_required,notes\n"
            "README.md,canonical,current,general,,,false,Root README\n"
        ),
        "scope": {"README.md": True, "docs/missing.md": True},
        "should_fail": True,
        "expect_error_contains": "is not in inventory",
    },
    {
        "name": "duplicate doc row",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\n"
            "README.md,canonical,current,general,,,false,First\n"
            "README.md,canonical,current,general,,,false,Duplicate\n"
        ),
        "should_fail": True,
        "expect_error_contains": "Duplicate",
    },
    {
        "name": "invalid class",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\n"
            "README.md,bad_class,current,general,,,false,Bad class\n"
        ),
        "should_fail": True,
        "expect_error_contains": "invalid doc_class",
    },
    {
        "name": "invalid status",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\n"
            "README.md,canonical,bad_status,general,,,false,Bad status\n"
        ),
        "should_fail": True,
        "expect_error_contains": "invalid truth_status",
    },
    {
        "name": "generated doc without generator",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\n"
            "docs/generated.md,generated,current,tooling,,,Missing generator\n"
        ),
        "should_fail": True,
        "expect_error_contains": "generated_by is empty",
    },
    {
        "name": "superseded doc without replacement/note",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\n"
            "docs/old.md,reference,superseded,artifacts,,,\n"
        ),
        "should_fail": True,
        "expect_error_contains": "replacement_doc and notes are empty",
    },
    {
        "name": "invalid boolean",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\n"
            "README.md,canonical,current,general,,,maybe,Invalid boolean\n"
        ),
        "should_fail": True,
        "expect_error_contains": "not a valid boolean",
    },
    {
        "name": "historical marked current",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\n"
            "README.md,historical,current,general,,,false,Conflicting\n"
        ),
        "should_fail": True,
        "expect_error_contains": "conflicting",
    },
    {
        "name": "valid inventory passes",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\n"
            "README.md,canonical,current,general,,,false,Root README\n"
        ),
        "should_fail": False,
    },
]


def run_self_test() -> bool:
    """Run self-test mode with inline fixture cases."""
    print("=== Docs Inventory Self-Test ===\n")

    all_passed = True

    for i, case in enumerate(SELF_TEST_CASES):
        print(f"Test case {i + 1}: {case['name']}")

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            tmp_inventory = tmp_path / "docs" / "docs_inventory.csv"
            tmp_inventory.parent.mkdir(parents=True, exist_ok=True)

            tmp_inventory.write_text(str(case["inventory"]))

            inventory_text = str(case["inventory"])
            referenced_files: set[str] = set()
            for line in inventory_text.strip().split("\n")[1:]:
                parts = line.split(",")
                if parts:
                    doc_path = parts[0].strip()
                    if doc_path:
                        referenced_files.add(doc_path)

            scope_files: set[Path] = set()
            scope_data = case.get("scope", {})
            skip_scope_check = case.get("skip_scope_check", False)

            if isinstance(scope_data, dict) and scope_data:
                for rel_path in scope_data:
                    f = tmp_path / rel_path
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_text("# Test file\n")
                    scope_files.add(f)
            elif not skip_scope_check:
                for rel_path in referenced_files:
                    f = tmp_path / rel_path
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_text("# Test file\n")
                    scope_files.add(f)

            # Override paths
            import docs_inventory_contract as contract_module
            import docs_inventory_loader as loader_module

            old_inventory = contract_module.INVENTORY_CSV
            old_repo_root = contract_module.REPO_ROOT
            contract_module.INVENTORY_CSV = tmp_inventory
            contract_module.REPO_ROOT = tmp_path
            loader_module.INVENTORY_CSV = tmp_inventory
            loader_module.REPO_ROOT = tmp_path

            try:
                rows, error = read_inventory()

                if error and case["should_fail"]:
                    print(f"  [OK] Failed to parse as expected: {error}")
                    continue

                if error and not case["should_fail"]:
                    print(f"  [UNEXPECTED] Parse error: {error}")
                    all_passed = False
                    continue

                checks_results = get_all_checks(rows, scope_files, tmp_path)

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
                contract_module.INVENTORY_CSV = old_inventory
                contract_module.REPO_ROOT = old_repo_root
                loader_module.INVENTORY_CSV = old_inventory
                loader_module.REPO_ROOT = old_repo_root

    print()
    if all_passed:
        print("SELF-TEST: PASSED")
    else:
        print("SELF-TEST: FAILED")

    return all_passed