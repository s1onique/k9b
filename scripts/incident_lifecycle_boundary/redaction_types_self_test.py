"""Self-test runner for redaction-types verifier.

This module contains the self-test infrastructure for verifying that
the AST-based redaction type checks work correctly.

R7 Requirements:
- Self-tests run production verifier functions against temporary repository trees
- Constructor fixtures create files at realistic paths and invoke check_trusted_constructor_usage()
- Boundary fixtures create protected file paths and invoke check_protected_boundary_imports()
- Negative tests require BOTH at least one verifier error AND every expected diagnostic substring

R10 Requirements:
- Canonical shared evaluator `evaluate_fixture()` lives here so both the
  pytest harness AND the canonical `redaction_types.py --self-test` use
  identical semantics:
      accepted fixture: errors == []
      rejected fixture: errors != [] AND every expected diagnostic substring
                         is present AND an unrelated error MUST NOT satisfy
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

# ---------------------------------------------------------------------------
# Shared evaluator (R10 §2)
# ---------------------------------------------------------------------------


def evaluate_fixture(
    *,
    name: str,
    content: str,
    expected_pass: bool,
    expected_errors_containing: list[str],
    check_func: Callable[..., list[str]],
    setup_path: bool = True,
) -> tuple[bool, list[str]]:
    """Evaluate a single fixture case through `check_func`.

    `check_func` receives a single filesystem path. By default the
    content is materialised in a fresh NamedTemporaryFile; when the check
    needs a populated source tree (constructor / boundary checks) the
    caller should pre-arrange the path and pass `setup_path=False`.

    Returns:
        (passed, errors)
    """
    temp_path: str | None = None
    if setup_path:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
        ) as fh:
            fh.write(content)
            temp_path = fh.name
    try:
        errors = list(check_func(temp_path))
        errors_serialised = [str(e) for e in errors]

        if expected_pass:
            passed = len(errors_serialised) == 0
        else:
            # Rejected: must be non-empty AND every expected substring
            # must appear AND an unrelated error must NOT satisfy.
            passed = len(errors_serialised) > 0
            if expected_errors_containing:
                missing = [sub for sub in expected_errors_containing if not any(sub in e for e in errors_serialised)]
                if missing:
                    passed = False

        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            for err in errors_serialised[:5]:
                print(f"        - {err[:140]}")
        return passed, errors_serialised
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Repository-tree helpers (used by canonical --self-test for
# constructor and boundary subsystems)
# ---------------------------------------------------------------------------


def create_temp_repo_tree(
    fixture_files: dict[str, str],
    source_dir: str = "k8s_diag_agent",
    collect_subdir: str = "collect",
) -> tuple[str, Path]:
    """Create a temporary repository tree with fixture files.

    Args:
        fixture_files: Dict mapping relative paths to file contents
        source_dir: Source directory name (e.g., "k8s_diag_agent")
        collect_subdir: Subdirectory for collect module files

    Returns:
        Tuple of (temp_dir, repo_root Path)
    """
    temp_dir = tempfile.mkdtemp()
    repo_root = Path(temp_dir)

    src_dir = repo_root / source_dir
    src_dir.mkdir(parents=True, exist_ok=True)

    collect_dir = src_dir / collect_subdir
    collect_dir.mkdir(parents=True, exist_ok=True)

    for rel_path, content in fixture_files.items():
        file_path = src_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    return temp_dir, repo_root


def cleanup_temp_repo_tree(temp_dir: str) -> None:
    """Clean up temporary repository tree."""
    shutil.rmtree(temp_dir, ignore_errors=True)


def run_self_tests_from_cases(
    test_cases: list[dict[str, object]],
    check_func: Callable[[str], list[str]],
) -> bool:
    """Run a list of test cases against a single file-based check function.

    Each test case dict has keys: name, content, expected_pass,
    expected_errors_containing.
    """
    all_passed = True
    for test_case in test_cases:
        if not isinstance(test_case, dict):
            all_passed = False
            continue
        name_obj = test_case.get("name", "")
        content_obj = test_case.get("content", "")
        expected_pass = bool(test_case.get("expected_pass", False))
        expected_errors_obj = test_case.get("expected_errors_containing", [])
        if not isinstance(name_obj, str) or not isinstance(content_obj, str):
            all_passed = False
            continue
        name: str = name_obj
        content: str = content_obj
        expected_errors = [str(e) for e in expected_errors_obj if isinstance(e, str)]

        passed, _ = evaluate_fixture(
            name=name,
            content=content,
            expected_pass=expected_pass,
            expected_errors_containing=expected_errors,
            check_func=check_func,
        )
        if not passed:
            all_passed = False
    return all_passed


def run_constructor_self_tests(
    check_func: Callable[[Path, str], list[str]],
    fixture_files: dict[str, str],
    expected_pass: bool,
    expected_errors_containing: list[str],
) -> bool:
    """Run constructor self-tests with a temporary repo tree."""
    temp_dir, repo_root = create_temp_repo_tree(fixture_files)
    try:
        errors = check_func(repo_root, "k8s_diag_agent")
        violations_found = len(errors) > 0
        passed = violations_found == (not expected_pass)
        if expected_errors_containing:
            all_expected = all(any(sub in err for err in errors) for sub in expected_errors_containing)
            passed = passed and all_expected
        return passed
    finally:
        cleanup_temp_repo_tree(temp_dir)


def run_boundary_self_tests(
    check_func: Callable[[Path], list[str]],
    protected_module_content: str,
    module_name: str,
    expected_pass: bool,
    expected_errors_containing: list[str],
) -> bool:
    """Run boundary self-tests with a temporary protected module."""
    fixture_files = {
        module_name: protected_module_content,
        "collect/incident_evidence_redaction.py": '''\
"""Privacy-state types."""
from typing import NewType

RawEvidenceText = NewType("RawEvidenceText", str)
RedactedEvidenceText = NewType("RedactedEvidenceText", str)
LLMSafeEvidenceText = NewType("LLMSafeEvidenceText", RedactedEvidenceText)
''',
    }
    temp_dir, repo_root = create_temp_repo_tree(fixture_files)
    try:
        errors = check_func(repo_root)
        violations_found = len(errors) > 0
        passed = violations_found == (not expected_pass)
        if expected_errors_containing:
            all_expected = all(any(sub in err for err in errors) for sub in expected_errors_containing)
            passed = passed and all_expected
        return passed
    finally:
        cleanup_temp_repo_tree(temp_dir)
