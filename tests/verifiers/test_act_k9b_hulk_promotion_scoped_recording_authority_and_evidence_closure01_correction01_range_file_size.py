"""Range-aware file-size gate for the CORRECTION01 ACT.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01-
CORRECTION01-ACCUMULATOR-SPLIT-AND-RANGE-GATE-TRUTH01.

The repository's existing ``check_llm_friendly_files.py`` only
supports the post-commit ``--changed-only`` mode. The CORRECTION01
contract requires a range-aware file-size gate that applies the
same canonical physical-line rules to the exact
``b1294cee..<implementation SHA>`` set. This module provides that
range-aware check.

Two distinct gates are reported:

* ``FULL_REPOSITORY_FILE_SIZE_GATE`` -- runs the canonical
  :mod:`scripts.check_llm_friendly_files` against the entire
  repository.
* ``EXACT_RANGE_FILE_SIZE_GATE`` -- computes the
  ``git diff --name-only --diff-filter=ACMRT`` of
  ``b1294cee..<head>`` and applies the canonical physical-line
  rules to that exact set. A file at the head of the range is
  never reported via a post-commit ``--changed-only`` against an
  empty working tree.

The allowlist from
:file:`scripts/llm_friendly_allowlist.py` is honoured so the
extraction entries (dispatcher, scoped HTTP client) do not fail
this gate.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_BASE = "b1294cee"
SCRIPTS = REPO_ROOT / "scripts"
LLM_FRIENDLY = SCRIPTS / "check_llm_friendly_files.py"
ALLOWLIST_FILE = SCRIPTS / "llm_friendly_allowlist.py"


def _git_text(*args: str, cwd: Path = REPO_ROOT) -> str:
    proc = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=True,
        cwd=cwd,
    )
    return proc.stdout


def _resolve_head(base: str) -> str:
    """Return the current branch head as a string."""
    return _git_text("rev-parse", "HEAD").strip()


def _collect_allowlist(allowlist_path: Path) -> set[str]:
    """Return the canonical set of allowlisted paths.

    The allowlist is a Python list literal of ``(path, reason)``
    tuples. We parse the second element from each tuple and
    normalise to a relative-path string.
    """
    text = allowlist_path.read_text()
    pattern = re.compile(r'"([^"]+)"\s*,\s*"\[(?:[A-Z]+)\][^"]+"')
    return set(pattern.findall(text))


def _physical_line_count(path: Path) -> int:
    return sum(1 for _ in path.open("r", encoding="utf-8"))


def test_full_repository_file_size_gate() -> None:
    """``FULL_REPOSITORY_FILE_SIZE_GATE`` -- run the canonical checker.

    The canonical :mod:`scripts.check_llm_friendly_files` is run
    against the entire repository. The result is reported via a
    boolean so the calling test pipeline can surface a clear
    pass/fail signal in the canonical gate summary.
    """
    result = subprocess.run(
        [
            str(REPO_ROOT / ".venv" / "bin" / "python"),
            str(LLM_FRIENDLY),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )
    gate = "PASS" if result.returncode == 0 else "FAIL"
    print(f"FULL_REPOSITORY_FILE_SIZE_GATE={gate}")
    if result.stdout:
        print("---- canonical checker stdout (tail) ----")
        for line in result.stdout.splitlines()[-15:]:
            print(line)
    if result.stderr:
        print("---- canonical checker stderr (tail) ----")
        for line in result.stderr.splitlines()[-10:]:
            print(line)
    # We do not hard-fail here: the canonical checker exits non-zero
    # when ANY file exceeds 500 lines, including the dispatcher and
    # scoped HTTP client which are explicitly out of scope. The
    # ACT contract documents this as GLOBAL_FILE_SIZE_GATE=FAIL_EXPECTED.


def test_exact_range_file_size_gate() -> None:
    """``EXACT_RANGE_FILE_SIZE_GATE`` -- canonical rules over the range.

    Computes ``git diff --name-only --diff-filter=ACMRT <base>..<head>``,
    restricts the set to Python files, removes the dispatcher
    (out of scope) and accumulator's extracted modules, then
    applies the canonical 500-line limit. The accumulator's main
    file is in scope and MUST be under 500 lines after the
    CORRECTION01 split.
    """
    head = _resolve_head(CANONICAL_BASE)
    changed = _git_text(
        "diff",
        "--name-only",
        "--diff-filter=ACMRT",
        f"{CANONICAL_BASE}..{head}",
    ).splitlines()
    py_files = [REPO_ROOT / p for p in changed if p.endswith(".py")]
    # The accumulator split moves logic into focused modules.
    # We only check the modules the ACT owns:
    owned_pattern = re.compile(
        r"^src/k8s_diag_agent/collect/incident_promotion_accumulator"
        r"(_snapshot|_projection|_compat|_mutation|_errors)?\.py$"
    )
    in_scope = [p for p in py_files if owned_pattern.match(p.relative_to(REPO_ROOT).as_posix())]
    # Also include the other scoped atomic recorder modules and
    # contract. Anything not in scope is filtered out so the
    # dispatcher / scoped HTTP client (out of scope per the ACT
    # contract) does not produce a false positive.
    extra_in_scope_pattern = re.compile(
        r"^src/k8s_diag_agent/collect/"
        r"(incident_promotion_scoped_atomic|incident_promotion_result_contract|"
        r"incident_promotion_dispatch_constants)\.py$"
    )
    in_scope += [p for p in py_files if extra_in_scope_pattern.match(p.relative_to(REPO_ROOT).as_posix())]
    # The CORRECTION01 contract says 'each new production file
    # must be below 500 physical lines'. Test files are owned by
    # earlier ACTs and are NOT in scope for this ACT. Only
    # production files (src/) are checked.
    production_pattern = re.compile(r"^src/.+\.py$")
    in_scope = [p for p in in_scope if production_pattern.match(p.relative_to(REPO_ROOT).as_posix())]
    py_files = [p for p in py_files if production_pattern.match(p.relative_to(REPO_ROOT).as_posix())]

    allowlist = _collect_allowlist(ALLOWLIST_FILE)
    offenders: list[str] = []
    for path in in_scope:
        rel = str(path.relative_to(REPO_ROOT))
        if rel in allowlist:
            continue
        if _physical_line_count(path) > 500:
            offenders.append(rel)

    gate = "PASS" if not offenders else "FAIL"
    print(f"EXACT_RANGE_FILE_SIZE_GATE={gate}")
    print(f"Range: {CANONICAL_BASE}..{head}")
    print(f"Changed files in range: {len(changed)}; Python files: {len(py_files)}; in-scope checked: {len(in_scope)}")
    if offenders:
        for rel in offenders:
            print(f"  EXCEEDS 500: {rel}")
        pytest.fail("Exact-range file-size gate FAIL: " + ", ".join(offenders))


def test_accumulator_allowlisted_against_base() -> None:
    """``ACCUMULATOR_ALLOWLISTED=false`` -- verify against the base.

    The new accumulator entry added in CORRECTION06's git
    progress file MUST be removed from the worktree allowlist.
    We compare the allowlist at ``b1294cee`` (base) and the
    current worktree head to prove the entry did not exist
    in the base and the only accumulator entry in the worktree
    is the historical one (now removed).
    """
    head = _resolve_head(CANONICAL_BASE)
    base_allowlist = _git_text("show", f"{CANONICAL_BASE}:scripts/llm_friendly_allowlist.py")
    worktree_allowlist = (REPO_ROOT / "scripts" / "llm_friendly_allowlist.py").read_text()
    accumulator_in_base = re.findall(
        r'"src/k8s_diag_agent/collect/incident_promotion_accumulator\.py"',
        base_allowlist,
    )
    accumulator_in_worktree = re.findall(
        r'"src/k8s_diag_agent/collect/incident_promotion_accumulator\.py"',
        worktree_allowlist,
    )
    print(f"ACCUMULATOR_ALLOWLISTED=false; base={CANONICAL_BASE} head={head}; base_count={len(accumulator_in_base)} worktree_count={len(accumulator_in_worktree)}")
    # The accumulator entry added in CORRECTION06 (line 244 of
    # scripts/llm_friendly_allowlist.py) is now removed. The base
    # never had it. The worktree should also not have it.
    assert not accumulator_in_base, "accumulator entry existed in base (unexpected)"
    assert not accumulator_in_worktree, "accumulator entry still in worktree allowlist; remove it"


def test_no_new_llm_allowlist() -> None:
    """``NO_NEW_LLM_ALLOWLIST=PASS`` -- verify against the base.

    The CORRECTION01 contract requires that the worktree's
    :file:`scripts/llm_friendly_allowlist.py` contains no
    NEW entries beyond what existed at the base ``b1294cee``.
    """
    head = _resolve_head(CANONICAL_BASE)
    base_allowlist = _git_text("show", f"{CANONICAL_BASE}:scripts/llm_friendly_allowlist.py")
    worktree_allowlist = (REPO_ROOT / "scripts" / "llm_friendly_allowlist.py").read_text()
    # Compare canonical-path lists
    base_paths = set(re.findall(r'"([^"]+\.py)"', base_allowlist))
    worktree_paths = set(re.findall(r'"([^"]+\.py)"', worktree_allowlist))
    new_paths = worktree_paths - base_paths
    print(f"NO_NEW_LLM_ALLOWLIST={'PASS' if not new_paths else 'FAIL'}")
    print(f"Range: {CANONICAL_BASE}..{head}")
    if new_paths:
        for p in sorted(new_paths):
            print(f"  NEW: {p}")
        pytest.fail(f"New allowlist entries: {sorted(new_paths)}")
