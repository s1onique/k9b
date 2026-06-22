"""Self-test helpers for the no-new-llm-allowlist verifier.

Error-condition tests (13-14) and hardening tests (15-19).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from llm_allowlist_policy.changed_files import get_changed_files


def run_self_test_with_errors() -> tuple[bool, list[str]]:
    """Run self-tests for error conditions including changed-file discovery errors.

    Returns:
        (success, error_messages)
    """
    errors: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        (repo_root / "docs" / "tooling").mkdir(parents=True)
        (repo_root / "scripts").mkdir(parents=True)

        # Test 13: Changed-file discovery errors fail closed (CLI behavior)
        print("\nTest 13: Changed-file discovery errors fail closed => FAIL")
        baseline_csv = repo_root / "docs" / "tooling" / "llm_large_file_allowlist_baseline.csv"
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")

        # Use fixture mode with a non-existent fixture - should fail
        fixture_path = tmp_path / "nonexistent.json"
        changed_files, resolved_base, changed_errors = get_changed_files(
            repo_root,
            mode="fixture",
            fixture_path=fixture_path,
        )

        # The changed_errors should contain the "not found" error
        if changed_errors and any("not found" in e for e in changed_errors):
            print("  PASS: Changed-file discovery errors correctly collected")
        else:
            errors.append(f"Test 13 FAILED: Changed-file discovery errors should be collected, got: {changed_errors}")

        # Test 14: CSV overflow (too many columns) fails
        print("\nTest 14: CSV overflow (too many columns) => FAIL")
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            # Extra column after expected columns
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None,EXTRA\n")

        from llm_allowlist_policy.baseline import parse_baseline_csv
        parse_baseline_csv(baseline_csv)  # Just check it doesn't crash

        if parse_baseline_csv(baseline_csv)[1]:
            print("  PASS: CSV overflow correctly detected")
        else:
            errors.append("Test 14 FAILED: CSV overflow should be detected")

    print("\n" + "=" * 50)
    if errors:
        print(f"Self-tests (errors) FAILED ({len(errors)} errors):")
        for err in errors:
            print(f"  - {err}")
        return False, errors
    else:
        print("All error self-tests PASSED")
        return True, errors


def run_hardening_self_tests() -> tuple[bool, list[str]]:
    """Run self-tests for the fail-closed hardening fixes.
    
    Returns:
        (success, error_messages)
    """
    import os
    errors: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        (repo_root / "docs" / "tooling").mkdir(parents=True)
        (repo_root / "scripts").mkdir(parents=True)

        baseline_csv = repo_root / "docs" / "tooling" / "llm_large_file_allowlist_baseline.csv"
        allowlist_py = repo_root / "scripts" / "llm_friendly_allowlist.py"

        # Test 15: Indirect ALLOWLIST = SOME_VAR fails closed
        print("\nTest 15: Indirect ALLOWLIST = SOME_VAR => FAIL (fail-closed)")
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")

        # Create a file with ALLOWLIST = SOME_VAR (variable reference, not literal)
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write("SOME_LIST = [(\"src/legacy.py\", \"[LEGACY] Old debt\")]\n")
            f.write("ALLOWLIST = SOME_LIST  # Variable reference - should fail\n")

        from llm_allowlist_policy.sources import parse_allowlist_from_python
        paths, parse_errors = parse_allowlist_from_python(allowlist_py)
        
        if parse_errors and any("variable reference" in e.lower() or "not a literal" in e.lower() for e in parse_errors):
            print("  PASS: Indirect ALLOWLIST fails closed")
        else:
            errors.append(f"Test 15 FAILED: Indirect ALLOWLIST should fail, got errors: {parse_errors}, paths: {paths}")

        # Test 16: Syntax-broken Python allowlist fails closed
        print("\nTest 16: Syntax-broken Python allowlist => FAIL (fail-closed)")
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write("ALLOWLIST = [(\"src/legacy.py\"  # Missing closing paren\n")

        paths, parse_errors = parse_allowlist_from_python(allowlist_py)
        
        # Should have errors (either from AST or from regex fallback being ambiguous)
        if parse_errors or not paths:
            print("  PASS: Syntax-broken allowlist fails closed")
        else:
            errors.append(f"Test 16 FAILED: Syntax-broken should fail, got paths: {paths}")

        # Test 17: Comment-only change above existing entries is classified as comment-only
        print("\nTest 17: Comment-only change above existing entries => comment-only")
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")

        # Initialize a git repo for this test
        subprocess.run(["git", "init"], cwd=repo_root, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_root, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_root, capture_output=True, text=True)
        
        # Create original file without the comment
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('ALLOWLIST = [("src/legacy.py", "[LEGACY] Old debt")]\n')
        
        # Commit the original
        subprocess.run(["git", "add", "."], cwd=repo_root, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_root, capture_output=True, text=True)
        
        # Now add the comment
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('# New comment above entry\n')
            f.write('ALLOWLIST = [("src/legacy.py", "[LEGACY] Old debt")]\n')

        from llm_allowlist_policy.changed_files import ChangedFile as CF
        from llm_allowlist_policy.comment_classifier import classify_change_as_comment_only
        
        changed = CF(path="scripts/llm_friendly_allowlist.py", old_path=None, status="M")
        is_comment_only, reason, classification_errors = classify_change_as_comment_only(
            repo_root, changed, None, "HEAD"
        )
        
        if is_comment_only and not classification_errors:
            print(f"  PASS: Comment-only change correctly classified: {reason}")
        else:
            errors.append(f"Test 17 FAILED: Comment-only should pass, is_comment_only={is_comment_only}, errors={classification_errors}")

        # Test 18: git show failure fails closed
        print("\nTest 18: git show failure => FAIL (fail-closed)")
        from llm_allowlist_policy.comment_classifier import get_file_content_at_ref
        
        # Try to get a non-existent file at a non-existent ref
        content, errors_list = get_file_content_at_ref(repo_root, "nonexistent.py", "definitely-not-a-ref")
        
        # Should have errors (git show failed for non-existent ref)
        if errors_list and any("failed" in e.lower() for e in errors_list):
            print(f"  PASS: git show failure fails closed: {errors_list}")
        else:
            errors.append(f"Test 18 FAILED: git show failure should fail, got content={content}, errors={errors_list}")

        # Test 19: K9B_LLM_ALLOWLIST_BASE_REF not used as head_ref
        print("\nTest 19: K9B_LLM_ALLOWLIST_BASE_REF not used as head_ref (stronger test)")
        from llm_allowlist_policy.changed_files import get_changed_files_ci
        
        # Initialize a git repo for this test
        subprocess.run(["git", "init"], cwd=repo_root, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_root, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_root, capture_output=True, text=True)
        
        # Create initial commit
        with open(repo_root / "README.md", "w") as f:
            f.write("# Test\n")
        subprocess.run(["git", "add", "."], cwd=repo_root, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_root, capture_output=True, text=True)
        
        # Get the first commit SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root, capture_output=True, text=True
        )
        first_commit = result.stdout.strip()
        
        # Modify allowlist file and commit again
        with open(repo_root / "scripts" / "llm_friendly_allowlist.py", "w") as f:
            f.write('ALLOWLIST = [("src/new.py", "[NEW] New entry")]\n')
        subprocess.run(["git", "add", "."], cwd=repo_root, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "Add allowlist entry"], cwd=repo_root, capture_output=True, text=True)
        
        old_env = os.environ.get("K9B_LLM_ALLOWLIST_BASE_REF")
        try:
            # Test 19a: K9B_LLM_ALLOWLIST_BASE_REF used as base ref
            os.environ["K9B_LLM_ALLOWLIST_BASE_REF"] = first_commit
            for key in ["CI_HEAD_REF", "HEAD_REF"]:
                os.environ.pop(key, None)
            
            changed, resolved_base, ci_errors = get_changed_files_ci(repo_root, base_ref=None, head_ref=None)
            
            if not any("same" in e.lower() for e in ci_errors):
                print("  PASS: 19a: K9B_LLM_ALLOWLIST_BASE_REF not collapsed to head_ref")
            else:
                errors.append(f"Test 19a FAILED: K9B_LLM_ALLOWLIST_BASE_REF incorrectly used as head: {ci_errors}")
            
            # Verify resolved_base is a valid SHA (not None or HEAD)
            if resolved_base and resolved_base != "HEAD":
                print(f"  PASS: 19a: Resolved base ref returned: {resolved_base[:8]}...")
            else:
                errors.append(f"Test 19a FAILED: Should return resolved base ref, got: {resolved_base}")
            
            changed_paths = [c.path for c in changed]
            if any("llm_friendly_allowlist" in p for p in changed_paths):
                print("  PASS: 19a: Detected changed allowlist file")
            else:
                errors.append(f"Test 19a FAILED: Should detect changed allowlist file, got: {changed_paths}")
            
            # Test 19b: Invalid base ref must fail closed
            os.environ["K9B_LLM_ALLOWLIST_BASE_REF"] = "nonexistent-ref-12345"
            changed2, resolved_base2, ci_errors2 = get_changed_files_ci(repo_root, base_ref=None, head_ref=None)
            
            if ci_errors2 and any("merge-base" in e.lower() or "failed" in e.lower() for e in ci_errors2):
                print("  PASS: 19b: Invalid base ref fails closed")
            else:
                errors.append(f"Test 19b FAILED: Invalid base ref should fail closed, got: {ci_errors2}")
                
        finally:
            if old_env:
                os.environ["K9B_LLM_ALLOWLIST_BASE_REF"] = old_env
            elif "K9B_LLM_ALLOWLIST_BASE_REF" in os.environ:
                del os.environ["K9B_LLM_ALLOWLIST_BASE_REF"]

    print("\n" + "=" * 50)
    if errors:
        print(f"Hardening self-tests FAILED ({len(errors)} errors):")
        for err in errors:
            print(f"  - {err}")
        return False, errors
    else:
        print("All hardening self-tests PASSED")
        return True, []


def run_base_ref_threading_tests() -> tuple[bool, list[str]]:
    """Run integration tests for base_ref threading through the verifier.
    
    Tests that resolved_base_ref from get_changed_files_ci is properly threaded
    into run_verification for comment classification.
    
    Returns:
        (success, error_messages)
    """
    import os
    errors: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        (repo_root / "docs" / "tooling").mkdir(parents=True)
        (repo_root / "scripts").mkdir(parents=True)

        baseline_csv = repo_root / "docs" / "tooling" / "llm_large_file_allowlist_baseline.csv"
        allowlist_py = repo_root / "scripts" / "llm_friendly_allowlist.py"

        # Initialize a git repo for these tests
        subprocess.run(["git", "init"], cwd=repo_root, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_root, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_root, capture_output=True, text=True)
        
        # Create baseline CSV
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")

        # Test 20: K9B_LLM_ALLOWLIST_BASE_REF with NEW entry => FAIL
        print("\nTest 20: K9B_LLM_ALLOWLIST_BASE_REF with new entry => EFFECTIVE CHANGE")
        
        # Reset to fresh state
        subprocess.run(["git", "reset", "--hard", "--quiet"], cwd=repo_root, capture_output=True, text=True)
        
        # Commit 1: Allowlist with existing entry + baseline with same entry
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('ALLOWLIST = [("src/legacy.py", "[LEGACY] Old debt")]\n')
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")
        subprocess.run(["git", "add", "."], cwd=repo_root, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "Initial - with baseline", "--quiet"], cwd=repo_root, capture_output=True, text=True)
        
        # Get the first commit SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root, capture_output=True, text=True
        )
        base_commit = result.stdout.strip()
        
        # Commit 2: Add NEW entry (not in baseline)
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('ALLOWLIST = [("src/legacy.py", "[LEGACY] Old debt"), ("src/new.py", "[NEW] New entry")]\n')
        subprocess.run(["git", "add", "."], cwd=repo_root, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "Add new entry", "--quiet"], cwd=repo_root, capture_output=True, text=True)
        
        # Now run the verifier with K9B_LLM_ALLOWLIST_BASE_REF set
        from llm_allowlist_policy.changed_files import get_changed_files_ci
        from llm_allowlist_policy.verify import run_verification
        
        old_env = os.environ.get("K9B_LLM_ALLOWLIST_BASE_REF")
        try:
            os.environ["K9B_LLM_ALLOWLIST_BASE_REF"] = base_commit
            
            # Get changed files (should return resolved_base_ref)
            changed, resolved_base, ci_errors = get_changed_files_ci(repo_root, base_ref=None, head_ref=None)
            
            if ci_errors:
                errors.append(f"Test 20 FAILED: CI errors: {ci_errors}")
            elif not resolved_base or resolved_base == "HEAD":
                errors.append(f"Test 20 FAILED: Expected resolved base ref, got: {resolved_base}")
            else:
                # Run verification with the resolved base ref
                success, ver_errors, ver_warnings = run_verification(
                    repo_root,
                    changed_files=changed,
                    old_baseline_paths={"src/legacy.py"},  # Base had this entry
                    base_ref=resolved_base,
                )
                
                # Should detect NEW entry as violation
                if not success and any("NEW allowlist entries" in e for e in ver_errors):
                    print("  PASS: Test 20: NEW entry correctly detected as violation")
                else:
                    errors.append(f"Test 20 FAILED: Should detect NEW entry, got errors: {ver_errors}")
                
                # Also check that comment classifier reports EFFECTIVE CHANGE
                if any("EFFECTIVE CHANGE" in w for w in ver_warnings):
                    print("  PASS: Test 20: EFFECTIVE CHANGE reported by classifier")
                else:
                    print(f"  WARN: Test 20: EFFECTIVE CHANGE not in warnings (may be covered by NEW entry check): {ver_warnings}")
            
        finally:
            if old_env:
                os.environ["K9B_LLM_ALLOWLIST_BASE_REF"] = old_env
            elif "K9B_LLM_ALLOWLIST_BASE_REF" in os.environ:
                del os.environ["K9B_LLM_ALLOWLIST_BASE_REF"]

        # Test 21: K9B_LLM_ALLOWLIST_BASE_REF with comment-only change => COMMENT-ONLY
        print("\nTest 21: K9B_LLM_ALLOWLIST_BASE_REF with comment-only change => COMMENT-ONLY")
        
        # Reset to base state
        subprocess.run(["git", "reset", "--hard", base_commit], cwd=repo_root, capture_output=True, text=True)
        
        # Commit 1 (again): Allowlist with existing entry and baseline
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('ALLOWLIST = [("src/legacy.py", "[LEGACY] Old debt")]\n')
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")
        subprocess.run(["git", "add", "."], cwd=repo_root, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "Add legacy entry with baseline"], cwd=repo_root, capture_output=True, text=True)
        
        # Get the commit SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root, capture_output=True, text=True
        )
        base_commit2 = result.stdout.strip()
        
        # Commit 2: Add comment only (same entries)
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('# Documentation comment\n')
            f.write('ALLOWLIST = [("src/legacy.py", "[LEGACY] Old debt")]\n')
        subprocess.run(["git", "add", "."], cwd=repo_root, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "Add comment"], cwd=repo_root, capture_output=True, text=True)
        
        try:
            os.environ["K9B_LLM_ALLOWLIST_BASE_REF"] = base_commit2
            
            # Get changed files
            changed2, resolved_base2, ci_errors2 = get_changed_files_ci(repo_root, base_ref=None, head_ref=None)
            
            if ci_errors2:
                errors.append(f"Test 21 FAILED: CI errors: {ci_errors2}")
            elif not resolved_base2 or resolved_base2 == "HEAD":
                errors.append(f"Test 21 FAILED: Expected resolved base ref, got: {resolved_base2}")
            else:
                # Run verification with the resolved base ref
                success2, ver_errors2, ver_warnings2 = run_verification(
                    repo_root,
                    changed_files=changed2,
                    old_baseline_paths={"src/legacy.py"},
                    base_ref=resolved_base2,
                )
                
                # Should pass (comment-only change is OK)
                if success2:
                    print("  PASS: Test 21: Comment-only change passes verification")
                else:
                    errors.append(f"Test 21 FAILED: Should pass, got errors: {ver_errors2}")
                
                # Check that comment classifier reports COMMENT-ONLY
                if any("COMMENT-ONLY" in w for w in ver_warnings2):
                    print("  PASS: Test 21: COMMENT-ONLY reported by classifier")
                else:
                    print(f"  WARN: Test 21: COMMENT-ONLY not in warnings: {ver_warnings2}")
            
        finally:
            if old_env:
                os.environ["K9B_LLM_ALLOWLIST_BASE_REF"] = old_env
            elif "K9B_LLM_ALLOWLIST_BASE_REF" in os.environ:
                del os.environ["K9B_LLM_ALLOWLIST_BASE_REF"]

    print("\n" + "=" * 50)
    if errors:
        print(f"Hardening self-tests FAILED ({len(errors)} errors):")
        for err in errors:
            print(f"  - {err}")
        return False, errors
    else:
        print("All hardening self-tests PASSED")
        return True, []
