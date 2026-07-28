"""Staged-manifest verification for the CORE01 closure.

CORRECTION05 R10: the final report must calculate the staged
manifest rather than manually asserting 17 or 18 paths. The
test in this file compares ``git diff --cached --name-only``
against the documented CORE01 manifest and fails on:

* missing staged paths,
* undocumented staged paths,
* duplicate manifest entries,
* any CORE01 path with an unstaged delta.

The CORE01 manifest is documented here as the authoritative
set; if a future ACT needs to add or remove a CORE01 path, it
must update this test (and the matching progress report).

Unrelated pre-existing untracked files are explicitly NOT
part of the CORE01 manifest.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Authoritative CORE01 staged manifest. Add or remove paths
# here in lockstep with the closure report.
CORE01_MANIFEST: tuple[str, ...] = (
    ".factory/gate-summary.json",
    "docs/doctrine/verifier-canonical-syntax.md",
    "docs/reports/r20-verifier-test-reconciliation.md",
    "mypy.ini",
    "scripts/factory/populate_gate_summary.py",
    "scripts/llm_friendly_allowlist.py",
    "scripts/verifiers/__init__.py",
    "scripts/verifiers/verifier_core/__init__.py",
    "scripts/verifiers/verifier_core/codes.py",
    "scripts/verifiers/verifier_core/detectors.py",
    "scripts/verifiers/verifier_core/diagnostics.py",
    "scripts/verifiers/verifier_core/directness.py",
    "scripts/verifiers/verifier_core/lookups.py",
    "task_progress_act_k9b_llm_friendly_verifier_canonical_syntax_core01.md",
    "task_progress_act_k9b_verifier_core01_closure_correction03.md",
    "task_progress_act_k9b_verifier_core01_closure_correction04.md",
    "task_progress_act_k9b_verifier_core01_closure_correction05.md",
    "tests/verifiers/test_canonical_doctrine_matches_production.py",
    "tests/verifiers/test_core01_staged_manifest.py",
    "tests/verifiers/test_verifier_core.py",
    "tests/verifiers/test_verifier_core_mypy_fixture.py",
)


def _git(*args: str) -> str:
    """Run git with the supplied args and return stdout."""
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout


def test_manifest_has_no_duplicates() -> None:
    """The CORE01 manifest itself has no duplicate entries."""
    assert len(CORE01_MANIFEST) == len(set(CORE01_MANIFEST)), f"CORE01 manifest has duplicate entries: {CORE01_MANIFEST!r}"


def _get_staged_paths() -> set[str]:
    """Return the set of currently staged paths in the repository."""
    staged_diff = _git("diff", "--cached", "--name-only")
    return {line.strip() for line in staged_diff.splitlines() if line.strip()}


def test_staged_paths_match_manifest() -> None:
    """Every CORE01 manifest path must be staged in the working tree.

    The CORE01 ACT closure requires that all manifest paths are
    staged together. This test verifies:
    - Every manifest path is staged (no missing paths)
    - Every staged path is in the manifest (no extra paths)
    - No CORE01 path has an unstaged delta
    """
    manifest = set(CORE01_MANIFEST)
    staged = _get_staged_paths()

    # Missing: staged paths that are not in the manifest
    extra = staged - manifest
    assert not extra, f"Extra staged paths not in CORE01 manifest: {sorted(extra)!r}"

    # Missing: manifest paths not staged
    missing = manifest - staged
    assert not missing, f"Missing CORE01 manifest paths (not staged): {sorted(missing)!r}"


def test_no_core01_path_has_an_unstaged_delta() -> None:
    """No staged CORE01 path has an unstaged delta (working-tree != index)."""
    unstaged_diff = _git("diff", "--name-only")
    unstaged_paths = {line.strip() for line in unstaged_diff.splitlines() if line.strip()}
    offenders = sorted(set(CORE01_MANIFEST) & unstaged_paths)
    assert not offenders, f"CORE01 paths with an unstaged delta: {offenders!r}"


@pytest.mark.parametrize("path", CORE01_MANIFEST)
def test_manifest_path_is_a_real_file(path: str) -> None:
    """Every CORE01 manifest path resolves to a real file."""
    assert (REPO_ROOT / path).exists(), f"manifest path does not exist: {path!r}"


def test_manifest_count_is_documented() -> None:
    """The CORE01 manifest size is exactly the count recorded in the
    closure report. This guards against drift between the report
    text and the manifest contents."""
    assert len(CORE01_MANIFEST) == 21, f"CORE01 manifest size must match the documented count (21); got {len(CORE01_MANIFEST)}. If you intentionally added/removed a path, update both this test and the closure report."
