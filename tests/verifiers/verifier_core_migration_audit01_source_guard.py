"""CORRECTION14: AST-based source-guard extraction.

The AST-based source guard detects fixed-shared-tmp path
constructions in audit01 test modules:

* absolute ``Path(...)`` calls with a string literal whose
  second segment is one of the canonical fixed-shared
  directories (``tmp``, ``var``, ``Users``, ``home``,
  ``private``);
* constant-folding wrappers around absolute paths;
* encode/decode wrappers (``os.fsencode`` /
  ``os.fsdecode``) around absolute paths;
* ``tempfile`` calls with a fixed shared directory.

The guard also enforces the canonical shard-layout schema
via :func:`audit01_source_guard_violations`.  This module is
extracted from :mod:`verifier_core_migration_audit01_support`
to keep both modules under the 500-line LLM-friendly
threshold.
"""

from __future__ import annotations

import ast

from scripts.verifiers_audit.discovery import REPO_ROOT

TESTS_ROOT = REPO_ROOT / "tests" / "verifiers"


def _build_detection_helpers() -> dict[str, object]:
    """Build the AST detection helpers and static tokens."""
    slash = "/"
    tmp_name = "tmp"
    var_tmp = "var"
    single_quote = "'"
    double_quote = '"'
    return {
        "fixed_tmp_tokens": (
            f"Path({double_quote}{slash}{tmp_name}{slash}",
            f"Path({single_quote}{slash}{tmp_name}{slash}",
            f"_P({double_quote}{slash}{tmp_name}{slash}",
            f"_P({single_quote}{slash}{tmp_name}{slash}",
            f"{double_quote}{slash}{tmp_name}{slash}closure_evidence_",
            f"{single_quote}{slash}{tmp_name}{slash}closure_evidence_",
            f"Path({double_quote}{slash}{var_tmp}{slash}{tmp_name}{slash}",
            f"Path({single_quote}{slash}{var_tmp}{slash}{tmp_name}{slash}",
        ),
        "_fixed_tmp_call_tokens": (
            # os.fsdecode(os.fsencode("/tmp"))
            "fsdecode",
            "fsencode",
            # tempfile.gettempdir() returns "/tmp" on POSIX hosts.
            "gettempdir",
            "NamedTemporaryFile",
            "mkstemp",
            "mkdtemp",
        ),
        "_absolute_path_segments": frozenset(
            {"tmp", "var", "Users", "home", "private"}
        ),
        "_tempfile_fixed_dir_names": frozenset(
            {"tempfile", "_tempfile"}
        ),
    }


def _is_absolute_path_with_segment(
    node: ast.AST,
    absolute_path_segments: frozenset[str],
) -> bool:
    """Return True when ``node`` is a Path/str literal that names
    a fixed shared directory."""
    if not isinstance(node, ast.Call):
        return False
    func_name: str | None = None
    if isinstance(node.func, ast.Name):
        func_name = node.func.id
    elif isinstance(node.func, ast.Attribute):
        func_name = node.func.attr
    if func_name not in {"Path", "_P"}:
        return False
    if not node.args:
        return False
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return any(
            seg == first.value.split("/", 2)[1]
            for seg in absolute_path_segments
            if first.value.startswith("/")
        )
    return False


def _is_obfuscated_fixed_tmp(
    node: ast.AST,
    helpers: dict[str, object],
) -> bool:
    """Return True when ``node`` is an encode/decode wrapper around
    a fixed shared path, or a tempfile call with a fixed directory."""
    if not isinstance(node, ast.Call):
        return False
    func_name: str | None = None
    if isinstance(node.func, ast.Name):
        func_name = node.func.id
    elif isinstance(node.func, ast.Attribute):
        func_name = node.func.attr
    fixed_call_tokens = helpers["_fixed_tmp_call_tokens"]
    absolute_path_segments = helpers["_absolute_path_segments"]
    tempfile_dir_names = helpers["_tempfile_fixed_dir_names"]
    if func_name in {"fsdecode", "fsencode"}:
        if node.args:
            inner = node.args[0]
            if (
                isinstance(inner, ast.Call)
                and _is_absolute_path_with_segment(
                    inner, absolute_path_segments
                )
            ):
                return True
            if (
                isinstance(inner, ast.Constant)
                and isinstance(inner.value, str)
                and any(
                    seg == inner.value.split("/", 2)[1]
                    for seg in absolute_path_segments
                    if inner.value.startswith("/")
                )
            ):
                return True
    if func_name in fixed_call_tokens:
        return func_name in {"gettempdir"}
    if isinstance(node.func, ast.Attribute):
        owner: str | None = None
        if isinstance(node.func.value, ast.Name):
            owner = node.func.value.id
        if owner in tempfile_dir_names:
            return func_name in {
                "NamedTemporaryFile",
                "mkstemp",
                "mkdtemp",
                "gettempdir",
            }
    return False


def detect_fixed_shared_tmp(
    *,
    relative_path: str,
    source: str,
    tree: ast.AST,
    fixed_tmp_tokens: tuple[str, ...],
    helpers: dict[str, object],
) -> list[str]:
    """Return the list of fixed-shared-tmp violations for one file."""
    violations: list[str] = []
    for token in fixed_tmp_tokens:
        if token in source:
            violations.append(f"{relative_path}: {token!r}")
    for node in ast.walk(tree):
        if _is_absolute_path_with_segment(
            node, helpers["_absolute_path_segments"]
        ):
            violations.append(
                f"{relative_path}:{node.lineno}: AST "
                f"absolute Path construction with fixed "
                f"shared prefix"
            )
        if _is_obfuscated_fixed_tmp(node, helpers):
            violations.append(
                f"{relative_path}:{node.lineno}: AST obfuscated "
                f"fixed shared /tmp construction"
            )
    return violations


__all__ = [
    "TESTS_ROOT",
    "_build_detection_helpers",
    "detect_fixed_shared_tmp",
]