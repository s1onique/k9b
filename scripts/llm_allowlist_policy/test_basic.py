"""Basic self-tests for the no-new-llm-allowlist verifier.

Tests 1-12 cover core allowlist verification logic.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from llm_allowlist_policy.changed_files import ChangedFile


def run_self_test() -> tuple[bool, list[str]]:
    """Run self-tests to verify the verifier itself.

    Returns:
        (success, error_messages)
    """
    from llm_allowlist_policy.verify import run_verification
    
    errors: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        (repo_root / "docs" / "tooling").mkdir(parents=True)
        (repo_root / "scripts").mkdir(parents=True)

        print("Running self-tests...")

        # Test 1: Clean baseline passes
        print("\nTest 1: Clean baseline (no current entries) passes")
        baseline_csv = repo_root / "docs" / "tooling" / "llm_large_file_allowlist_baseline.csv"
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")

        allowlist_py = repo_root / "scripts" / "llm_friendly_allowlist.py"
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write("ALLOWLIST = []\n")

        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=[],
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if success:
            print("  PASS: Clean baseline passes")
        else:
            errors.append(f"Test 1 FAILED: Clean baseline should pass, got: {test_errors}")

        # Test 2: Adding new entry fails
        print("\nTest 2: Adding new allowlist entry fails")
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('ALLOWLIST = [("src/legacy.py", "[LEGACY] Old debt"), ("src/new_large.py", "[BIG] New")]\n')

        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=[],
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if not success and any("NEW allowlist entries" in e for e in test_errors):
            print("  PASS: Adding new entry correctly fails")
        else:
            errors.append(f"Test 2 FAILED: Adding new entry should fail, got: {test_errors}")

        # Test 3: Existing entry in baseline passes
        print("\nTest 3: Existing baseline entry passes")
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('ALLOWLIST = [("src/legacy.py", "[LEGACY] Old debt")]\n')

        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=[],
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if success:
            print("  PASS: Existing entry passes")
        else:
            errors.append(f"Test 3 FAILED: Existing entry should pass, got: {test_errors}")

        # Test 4: Duplicate baseline entry fails
        print("\nTest 4: Duplicate baseline entry fails")
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Duplicate,team,grandfathered,None\n")

        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=[],
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if not success and any("Duplicate" in e for e in test_errors):
            print("  PASS: Duplicate baseline entry fails")
        else:
            errors.append(f"Test 4 FAILED: Duplicate should fail, got: {test_errors}")

        # Test 5: Path traversal in baseline fails
        print("\nTest 5: Path traversal in baseline fails")
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("../secret.py,llm_friendly_allowlist_py,[BAD] Path traversal,team,grandfathered,None\n")

        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=[],
            old_baseline_paths=set(),
            verbose=False,
        )
        if not success and any(e for e in test_errors):
            print("  PASS: Path traversal fails")
        else:
            errors.append(f"Test 5 FAILED: Path traversal should fail, got: {test_errors}")

        # Test 6: .llm-friendly-ignore new entry fails
        print("\nTest 6: .llm-friendly-ignore new entry fails")
        subdir = repo_root / "src" / "newdir"
        subdir.mkdir(parents=True)
        ignore_file = subdir / ".llm-friendly-ignore"
        with open(ignore_file, "w", encoding="utf-8") as f:
            f.write("# Comment\noversized_file.py\n")

        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")

        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write("ALLOWLIST = []\n")

        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=[],
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if not success and any("NEW allowlist entries" in e for e in test_errors):
            print("  PASS: .llm-friendly-ignore new entry fails")
        else:
            errors.append(f"Test 6 FAILED: Should fail, got: {test_errors}")

        # Test 7: Modified allowlisted file still allowlisted => FAIL
        print("\nTest 7: Modified allowlisted file still allowlisted => FAIL")
        if ignore_file.exists():
            ignore_file.unlink()
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")

        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('ALLOWLIST = [("src/legacy.py", "[LEGACY] Old debt")]\n')

        changed = [ChangedFile(path="src/legacy.py", old_path=None, status="M")]
        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=changed,
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if not success and any("Modified allowlisted files remain" in e for e in test_errors):
            print("  PASS: Modified allowlisted still in allowlist fails")
        else:
            errors.append(f"Test 7 FAILED: Should fail, got: {test_errors}")

        # Test 8: Modified allowlisted file removed from allowlist => PASS
        print("\nTest 8: Modified allowlisted file removed from allowlist => PASS")
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write("ALLOWLIST = []\n")

        changed = [ChangedFile(path="src/legacy.py", old_path=None, status="M")]
        success, test_errors, test_warnings = run_verification(
            repo_root,
            changed_files=changed,
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if success and any("removed from allowlist" in w for w in test_warnings):
            print("  PASS: Modified and removed from allowlist passes")
        else:
            errors.append(f"Test 8 FAILED: Should pass, got: {test_errors}")

        # Test 9: Deleted allowlisted file plus removed allowlist entry => PASS
        print("\nTest 9: Deleted allowlisted file plus removed entry => PASS")
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write("ALLOWLIST = []\n")

        changed = [ChangedFile(path="src/legacy.py", old_path=None, status="D")]
        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=changed,
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if success:
            print("  PASS: Deleted file removed from allowlist passes")
        else:
            errors.append(f"Test 9 FAILED: Should pass, got: {test_errors}")

        # Test 10: Renamed allowlisted file still allowlisted => FAIL
        print("\nTest 10: Renamed allowlisted file still allowlisted => FAIL")
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('ALLOWLIST = [("src/new_name.py", "[LEGACY] Old debt")]\n')

        changed = [ChangedFile(path="src/new_name.py", old_path="src/legacy.py", status="R")]
        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=changed,
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if not success and any("Renamed allowlisted file still allowlisted" in e for e in test_errors):
            print("  PASS: Renamed allowlisted still in allowlist fails")
        else:
            errors.append(f"Test 10 FAILED: Should fail, got: {test_errors}")

        # Test 11: .llm-friendly-ignore with repo escape => FAIL
        print("\nTest 11: .llm-friendly-ignore with repo escape => FAIL")
        subdir2 = repo_root / "src" / "testdir"
        subdir2.mkdir(parents=True)
        ignore_file2 = subdir2 / ".llm-friendly-ignore"
        with open(ignore_file2, "w", encoding="utf-8") as f:
            f.write("../outside.py\n")

        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")

        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('ALLOWLIST = [("src/legacy.py", "[LEGACY] Old debt")]\n')

        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=[],
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if not success and any(e for e in test_errors):
            print("  PASS: .llm-friendly-ignore repo escape fails")
        else:
            errors.append(f"Test 11 FAILED: Should fail, got: {test_errors}")

        # Test 12: Baseline growth => FAIL
        print("\nTest 12: Baseline growth => FAIL")
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")
            f.write("src/new_entry.py,llm_friendly_allowlist_py,[NEW] New entry,team,grandfathered,None\n")

        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('ALLOWLIST = [("src/legacy.py", "[LEGACY] Old debt")]\n')

        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=[],
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if not success and any("BASELINE GROWTH" in e for e in test_errors):
            print("  PASS: Baseline growth fails")
        else:
            errors.append(f"Test 12 FAILED: Should fail, got: {test_errors}")

    print("\n" + "=" * 50)
    if errors:
        print(f"Self-tests FAILED ({len(errors)} errors):")
        for err in errors:
            print(f"  - {err}")
        return False, errors
    else:
        print("All self-tests PASSED")
        return True, []
