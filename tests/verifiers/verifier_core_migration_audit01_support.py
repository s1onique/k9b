"""Ordinary support utilities for the split audit01 test family.

This module owns reusable test data, hermetic Git helpers, the canonical
artifact hash snapshot, and the authoritative split-module inventory.
Pytest fixtures remain in :mod:`tests.verifiers.conftest`.
"""

from __future__ import annotations

import ast
import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts.verifiers_audit.discovery import REPO_ROOT

TESTS_ROOT = REPO_ROOT / "tests" / "verifiers"

AUDIT01_TEST_MODULES_WITHOUT_SUPPORT: tuple[Path, ...] = (
    TESTS_ROOT / "test_verifier_core_migration_audit01.py",
    TESTS_ROOT / "test_verifier_core_migration_audit01_cmd.py",
    TESTS_ROOT / "test_verifier_core_migration_audit01_layout.py",
    TESTS_ROOT / "test_verifier_core_migration_audit01_r.py",
    TESTS_ROOT / "test_verifier_core_migration_audit01_range.py",
    TESTS_ROOT / "test_verifier_core_migration_audit01_range_adversarial.py",
    TESTS_ROOT / "test_verifier_core_migration_audit01_correction13.py",
    TESTS_ROOT / "test_verifier_core_migration_audit01_correction13_cmd.py",
    TESTS_ROOT / "test_verifier_core_migration_audit01_correction13_evidence.py",
    TESTS_ROOT / "test_verifier_core_migration_audit01_correction14.py",
    TESTS_ROOT / "test_verifier_core_migration_audit01_correction14_layout.py",
    TESTS_ROOT / "test_verifier_core_migration_audit01_correction14_evidence.py",
    TESTS_ROOT / "test_verifier_core_migration_audit01_correction15.py",
    TESTS_ROOT / "test_verifier_core_migration_audit01_correction15_bundle.py",
    TESTS_ROOT / "test_verifier_core_migration_audit01_correction15_evidence.py",
    TESTS_ROOT / "test_verifier_core_migration_audit01_correction15_inventory.py",
)

AUDIT01_TEST_MODULES: tuple[Path, ...] = (
    *AUDIT01_TEST_MODULES_WITHOUT_SUPPORT,
    TESTS_ROOT / "conftest.py",
    TESTS_ROOT / "verifier_core_migration_audit01_support.py",
    TESTS_ROOT / "verifier_core_migration_audit01_source_guard.py",
)

AUDIT01_PRODUCTION_MODULES: tuple[Path, ...] = (
    REPO_ROOT / "scripts" / "verifiers_audit" / "range_evidence.py",
    REPO_ROOT / "scripts" / "verifiers_audit" / "range_evidence_helpers.py",
    REPO_ROOT / "scripts" / "verifiers_audit" / "range_evidence_identity.py",
    REPO_ROOT / "scripts" / "verifiers_audit" / "range_evidence_writer.py",
    REPO_ROOT / "scripts" / "verifiers_audit" / "range_evidence_orchestrator.py",
    REPO_ROOT / "scripts" / "verifiers_audit" / "range_evidence_builders.py",
    REPO_ROOT / "scripts" / "verifiers_audit" / "range_evidence_classification.py",
    REPO_ROOT / "scripts" / "verifiers_audit" / "range_evidence_bundle.py",
    REPO_ROOT / "scripts" / "verifiers_audit" / "range_evidence_gates.py",
    REPO_ROOT / "scripts" / "verifiers_audit" / "range_evidence_inventory.py",
    REPO_ROOT / "scripts" / "verifiers_audit" / "typed_results.py",
)


AUDIT01_ALL_PYTHON_MODULES: tuple[Path, ...] = (
    *AUDIT01_PRODUCTION_MODULES,
    *AUDIT01_TEST_MODULES,
)


def audit01_source_guard_violations() -> dict[str, tuple[str, ...]]:
    """Return complete split-wide source-guard violations by contract key."""
    violations: dict[str, list[str]] = {
        "imports_tests_verifiers_conftest": [],
        "fixed_shared_tmp_paths": [],
        "hardcoded_k9b_commit_fixture_bindings": [],
        "direct_canonical_writer_calls_outside_allowed_tests": [],
        "files_over_500_lines": [],
    }
    from tests.verifiers.verifier_core_migration_audit01_source_guard import (
        _build_detection_helpers,
        detect_fixed_shared_tmp,
    )

    helpers = _build_detection_helpers()
    fixed_tmp_tokens = helpers["fixed_tmp_tokens"]
    assert isinstance(fixed_tmp_tokens, tuple)
    fixture_base_name = "FIXTURE_" + "BASE"
    fixture_subject_name = "FIXTURE_" + "SUBJECT"
    forbidden_values = {
        "4bf" + "51fbf" + "870fa21b6e2519dc3c7c1bbb89017c96",
        "78b" + "e1ce8a" + "cea4aa67fcf266496127825e7d00219",
        "75a" + "43f3f" + "317c6f2dc571e4fe5e988d00ba00285c",
        "0c9" + "226e0" + "3a043631ea3f4bfe2e55c8b84c713c4a",
    }
    allowed_cmd_write_tests = {
        "test_cmd_write_calls_write_audit_exactly_once",
        "test_cmd_write_supplies_canonical_layout",
        "test_cmd_write_caller_supplied_classification_returns_2_before_writer",
        "test_cmd_write_rejects_caller_supplied_gc_with_nonzero",
        "test_cmd_write_writer_exception_returns_nonzero",
        "test_cmd_write_os_error_returns_nonzero",
        "test_cmd_write_value_error_returns_nonzero",
        "test_cmd_write_no_artifact_changes_after_rejected_write",
        "test_cmd_write_no_artifact_changes_after_failed_write",
    }
    allowed_writer_functions: dict[Path, frozenset[str]] = {
        TESTS_ROOT / "test_verifier_core_migration_audit01_cmd.py": frozenset(
            {"test_cmd_write_no_artifact_changes_after_failed_write"}
        ),
        TESTS_ROOT / "test_verifier_core_migration_audit01_layout.py": frozenset(
            {
                "test_writes_through_temporary_layout_do_not_touch_canonical",
                "test_recorded_shard_paths_match_layout",
                "test_canonical_gate_classification_not_written_by_write_audit",
            }
        ),
        TESTS_ROOT / "test_verifier_core_migration_audit01_r.py": frozenset(
            {"test_required_shards_complete"}
        ),
        TESTS_ROOT / "test_verifier_core_migration_audit01_range.py": frozenset(
            {
                "test_inconsistent_layout_rejected_by_writer",
                "test_parallel_layouts_are_isolated",
            }
        ),
        TESTS_ROOT
        / "test_verifier_core_migration_audit01_correction13.py": frozenset(
            {"_build_comparison_layouts"}
        ),
        TESTS_ROOT
        / "test_verifier_core_migration_audit01_correction13_cmd.py": frozenset(
            {
                "_build_comparison_layouts",
                "test_compare_report_layouts_returns_empty_for_equal_layouts",
                "test_cmd_check_detects_schema_version_mutation",
                "test_cmd_check_detects_analysis_base_commit_mutation",
                "test_cmd_check_detects_identity_binding_mutation",
                "test_cmd_check_detects_totals_mutation",
                "test_cmd_check_detects_shard_hash_mutation",
                "test_cmd_check_detects_shard_set_mutation",
                "test_cmd_check_detects_unknown_extra_field",
                "test_cmd_check_detects_wrong_shard_basename",
                "test_cmd_check_detects_wrong_shard_parent",
                "test_cmd_check_detects_swapped_shard_paths",
                "test_cmd_check_production_invocation_detects_totals_mutation",
            }
        ),
        TESTS_ROOT
        / "test_verifier_core_migration_audit01_correction14_layout.py": frozenset(
            {"_build_complete_index"}
        ),
    }


    cmd_module = TESTS_ROOT / "test_verifier_core_migration_audit01_cmd.py"

    for path in AUDIT01_TEST_MODULES:
        source = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        tree = ast.parse(source, filename=str(path))
        violations["fixed_shared_tmp_paths"].extend(
            detect_fixed_shared_tmp(
                relative_path=relative_path,
                source=source,
                tree=tree,
                fixed_tmp_tokens=fixed_tmp_tokens,
                helpers=helpers,
            )
        )

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imports_conftest = (
                    node.module == "tests.verifiers.conftest"
                    or (
                        node.module == "tests.verifiers"
                        and any(alias.name == "conftest" for alias in node.names)
                    )
                    or (
                        node.level > 0
                        and any(alias.name == "conftest" for alias in node.names)
                    )
                )
                if imports_conftest:
                    violations["imports_tests_verifiers_conftest"].append(
                        f"{relative_path}:{node.lineno}"
                    )
            elif isinstance(node, ast.Import):
                if any(
                    alias.name == "tests.verifiers.conftest"
                    or alias.name.startswith("tests.verifiers.conftest.")
                    for alias in node.names
                ):
                    violations["imports_tests_verifiers_conftest"].append(
                        f"{relative_path}:{node.lineno}"
                    )

            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (
                    node.targets
                    if isinstance(node, ast.Assign)
                    else [node.target]
                )
                bound_names = {
                    target.id
                    for target in targets
                    if isinstance(target, ast.Name)
                }
                value = node.value
                value_text = (
                    value.value
                    if isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                    else None
                )
                if (
                    fixture_base_name in bound_names
                    or fixture_subject_name in bound_names
                    or value_text in forbidden_values
                ):
                    violations[
                        "hardcoded_k9b_commit_fixture_bindings"
                    ].append(f"{relative_path}:{node.lineno}")

        for function in (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            for call in (
                node for node in ast.walk(function) if isinstance(node, ast.Call)
            ):
                if isinstance(call.func, ast.Name):
                    call_name = call.func.id
                elif isinstance(call.func, ast.Attribute):
                    call_name = call.func.attr
                else:
                    continue
                if call_name in {"write_audit", "write_all"}:
                    allowed_function = function.name in allowed_writer_functions.get(
                        path, frozenset()
                    )
                    layout_keywords = [
                        keyword
                        for keyword in call.keywords
                        if keyword.arg == "layout"
                    ]
                    if not allowed_function or not layout_keywords or any(
                        isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is None
                        for keyword in layout_keywords
                    ):
                        violations[
                            "direct_canonical_writer_calls_outside_allowed_tests"
                        ].append(
                            f"{relative_path}:{call.lineno}:{function.name}"
                        )
                elif call_name == "cmd_write" and not (
                    path == cmd_module
                    and function.name in allowed_cmd_write_tests
                ):
                    violations[
                        "direct_canonical_writer_calls_outside_allowed_tests"
                    ].append(
                        f"{relative_path}:{call.lineno}:{function.name}"
                    )

    for path in AUDIT01_ALL_PYTHON_MODULES:
        count = len(path.read_text(encoding="utf-8").splitlines())
        if count > 500:
            violations["files_over_500_lines"].append(
                f"{path.relative_to(REPO_ROOT).as_posix()}: {count}"
            )

    return {key: tuple(items) for key, items in violations.items()}


@dataclass
class RangeRepo:
    """A self-contained temporary Git repository for range tests."""

    root: Path
    base: str
    subject: str
    trailing_whitespace_supported: bool = False
    embedded_newline_supported: bool = False


def _git_run(repo_root: Path, args: list[str]) -> None:
    """Run Git with a deterministic identity and raise on failure."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "CORRECTION12 Test",
            "GIT_AUTHOR_EMAIL": "cor12@test.local",
            "GIT_COMMITTER_NAME": "CORRECTION12 Test",
            "GIT_COMMITTER_EMAIL": "cor12@test.local",
            "PATH": os.environ.get("PATH", ""),
        },
    )
    if proc.returncode != 0:
        message = (
            proc.stderr.decode("utf-8", errors="replace")
            if proc.stderr
            else ""
        )
        raise RuntimeError(
            f"git {' '.join(args)} failed in {repo_root}: "
            f"returncode={proc.returncode}: {message}"
        )


def git_init(repo: Path) -> None:
    """Initialise an empty Git repository with deterministic settings."""
    repo.mkdir(parents=True, exist_ok=True)
    _git_run(repo, ["init", "-q", "-b", "main", str(repo)])
    _git_run(repo, ["config", "user.name", "CORRECTION12 Test"])
    _git_run(repo, ["config", "user.email", "cor12@test.local"])
    _git_run(repo, ["config", "commit.gpgsign", "false"])
    _git_run(repo, ["config", "core.quotePath", "false"])


def _git_commit(repo: Path, message: str) -> str:
    """Commit the current working tree and return the new HEAD."""
    _git_run(repo, ["add", "-A"])
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(repo),
        capture_output=True,
        check=False,
    )
    if staged.stdout == b"":
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            check=False,
        )
        return head.stdout.decode("utf-8").strip()
    _git_run(repo, ["commit", "-q", "-m", message])
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        check=False,
    )
    return head.stdout.decode("utf-8").strip()


def _safe_write(repo: Path, rel: str, content: str) -> bool:
    """Write a fixture path; report whether its basename stayed verbatim."""
    path = repo / rel
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except (OSError, ValueError):
        return False
    return path.name == rel.split("/")[-1]


def _safe_delete(repo: Path, rel: str) -> None:
    path = repo / rel
    if path.exists():
        path.unlink()


def _safe_rename(repo: Path, src: str, dst: str) -> None:
    src_path = repo / src
    dst_path = repo / dst
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.rename(dst_path)


def commit_fixture_base(repo: Path) -> tuple[str, bool]:
    """Create the baseline commit and return ``(hash, trailing_ok)``."""
    _safe_write(repo, "modified.py", "# v1\n")
    _safe_write(repo, "renamed.py", "# to be renamed\n")
    _safe_write(repo, "deleted.py", "# to be deleted\n")
    _safe_write(repo, "README.md", "# README\n")
    _safe_write(repo, "with space.py", "# space v1\n")
    _safe_write(repo, " leading.py", "# leading v1\n")
    trailing_ok = _safe_write(repo, "trailing.py ", "# trailing v1\n")
    _safe_write(repo, "файл.py", "# non-ascii v1\n")
    return _git_commit(repo, "base"), trailing_ok


def commit_fixture_subject(
    repo: Path,
    trailing_ok: bool,
) -> tuple[str, bool]:
    """Create the adversarial subject commit and return its capabilities."""
    _safe_write(repo, "modified.py", "# v2\n")
    _safe_rename(repo, "renamed.py", "renamed_dest.py")
    _safe_delete(repo, "deleted.py")
    _safe_write(repo, "new.txt", "new content\n")
    _safe_write(repo, "added.py", "# added in subject\n")
    _safe_write(repo, "with space.py", "# space v2\n")
    _safe_write(repo, " leading.py", "# leading v2\n")
    if trailing_ok:
        _safe_write(repo, "trailing.py ", "# trailing v2\n")
    _safe_write(repo, "файл.py", "# non-ascii v2\n")
    newline_ok = _safe_write(repo, "line\nbreak.py", "# newline v2\n")
    return _git_commit(repo, "subject"), newline_ok


def _synthetic_skipped_record(reason: str) -> dict[str, object]:
    """Return a deterministic synthetic ``SKIPPED`` record."""
    from scripts.verifiers_audit.gate_classification import _skipped_record

    return _skipped_record(reason)


def hash_canonical_artifact_set() -> dict[str, str]:
    """Return SHA-256 hashes for every canonical audit01 artifact present."""
    relative_paths = (
        Path(".factory/gate-summary.json"),
        Path("docs/reports/verifier-core-migration-audit01.json"),
        Path("docs/reports/verifier-core-migration-audit01.md"),
    )
    hashes: dict[str, str] = {}
    for relative_path in relative_paths:
        path = REPO_ROOT / relative_path
        if path.exists():
            hashes[relative_path.as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()

    shard_root = (
        REPO_ROOT / "docs" / "reports" / "verifier-core-migration-audit01"
    )
    for path in sorted(shard_root.glob("*.json")):
        relative_shard_path = path.relative_to(REPO_ROOT).as_posix()
        hashes[relative_shard_path] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return hashes
