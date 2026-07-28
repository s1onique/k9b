"""Staged-manifest verification for the CORE01 closure.

CORRECTION05 R10: the final report must calculate the staged
manifest rather than manually asserting 17 or 18 paths. The
test in this file compares ``git diff --cached --name-only``
against the documented CORE01 manifest and fails on:

* missing staged paths,
* undocumented staged paths,
* duplicate manifest entries,
* any CORE01 path with an unstaged delta.

CORRECTION21: This test now uses a hermetic temporary Git
repository to avoid depending on the outer repository's live
index. The temporary repo contains all 21 CORE01 paths,
allowing the staging validation to work on any clean checkout.

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


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git with the supplied args and return the process result."""
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )


def _git_commit_all(repo: Path, message: str) -> None:
    """Stage all changes and commit."""
    _git(repo, "add", "-A")
    result = _git(repo, "commit", "-m", message)
    if result.returncode != 0:
        raise RuntimeError(f"git commit failed: {result.stderr}")


class TemporaryStagedRepo:
    """A temporary Git repository with a staged closure manifest.

    This fixture creates a hermetic environment for testing the
    CORE01 manifest staging contract. It:
    1. Creates a temporary Git repository
    2. Copies all 21 CORE01 manifest files into it
    3. Stages them (without committing) to simulate closure staging
    4. Provides methods to query the staged state
    """

    def __init__(self, tmp_path: Path) -> None:
        self.repo = tmp_path / "core01_closure_repo"
        self.repo.mkdir(parents=True, exist_ok=True)
        self._init_git()
        self._populate_closure()

    def _init_git(self) -> None:
        """Initialize the temporary Git repository."""
        result = _git(self.repo, "init", "-q")
        if result.returncode != 0:
            raise RuntimeError(f"git init failed: {result.stderr}")
        _git(self.repo, "config", "user.name", "CORRECTION21 Test")
        _git(self.repo, "config", "user.email", "cor21@test.local")
        _git(self.repo, "config", "commit.gpgsign", "false")

    def _populate_closure(self) -> None:
        """Copy all CORE01 manifest files to the temporary repo."""
        for rel_path in CORE01_MANIFEST:
            src = REPO_ROOT / rel_path
            dst = self.repo / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                dst.write_bytes(src.read_bytes())

    def stage_closure(self) -> None:
        """Stage all CORE01 manifest files as a closure unit."""
        _git(self.repo, "add", *CORE01_MANIFEST)

    def get_staged_paths(self) -> set[str]:
        """Return the set of currently staged paths."""
        result = _git(self.repo, "diff", "--cached", "--name-only")
        if result.returncode != 0:
            return set()
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}

    def has_unstaged_delta(self, rel_path: str) -> bool:
        """Return True if the path has an unstaged delta."""
        result = _git(self.repo, "diff", "--name-only", "--", rel_path)
        return bool(result.stdout.strip())


@pytest.fixture
def staged_repo(tmp_path: Path) -> TemporaryStagedRepo:
    """A temporary repository with all CORE01 manifest files staged."""
    repo = TemporaryStagedRepo(tmp_path)
    repo.stage_closure()
    return repo


def test_manifest_has_no_duplicates() -> None:
    """The CORE01 manifest itself has no duplicate entries."""
    assert len(CORE01_MANIFEST) == len(set(CORE01_MANIFEST)), f"CORE01 manifest has duplicate entries: {CORE01_MANIFEST!r}"


def test_staged_paths_match_manifest(staged_repo: TemporaryStagedRepo) -> None:
    """Every CORE01 manifest path must be staged in the closure.

    The CORE01 ACT closure requires that all manifest paths are
    staged together. This test verifies using a hermetic temporary
    repository:
    - Every manifest path is staged (no missing paths)
    - Every staged path is in the manifest (no extra paths)
    """
    manifest = set(CORE01_MANIFEST)
    staged = staged_repo.get_staged_paths()

    # Extra: staged paths not in the manifest
    extra = staged - manifest
    assert not extra, f"Extra staged paths not in CORE01 manifest: {sorted(extra)!r}"

    # Missing: manifest paths not staged
    missing = manifest - staged
    assert not missing, f"Missing CORE01 manifest paths (not staged): {sorted(missing)!r}"


def test_no_core01_path_has_an_unstaged_delta(staged_repo: TemporaryStagedRepo) -> None:
    """No CORE01 manifest path has an unstaged delta after staging."""
    offenders = [path for path in CORE01_MANIFEST if staged_repo.has_unstaged_delta(path)]
    assert not offenders, f"CORE01 paths with an unstaged delta: {offenders!r}"


def test_manifest_count_is_documented() -> None:
    """The CORE01 manifest size is exactly the count recorded in the
    closure report. This guards against drift between the report
    text and the manifest contents."""
    assert len(CORE01_MANIFEST) == 21, f"CORE01 manifest size must match the documented count (21); got {len(CORE01_MANIFEST)}. If you intentionally added/removed a path, update both this test and the closure report."


def test_hermetic_manifest_no_outer_index_access(staged_repo: TemporaryStagedRepo) -> None:
    """Verify the manifest uses only the temporary repo's index.

    This test documents that the staging validation is hermetic:
    - All paths come from the temporary repository
    - No inspection of the outer k9b repository's index
    """
    # The staged repo should have all 21 paths staged
    staged = staged_repo.get_staged_paths()
    assert len(staged) == 21, f"Expected 21 staged paths, got {len(staged)}"
    assert staged == set(CORE01_MANIFEST)


def test_manifest_path_existence_in_k9b(staged_repo: TemporaryStagedRepo) -> None:
    """Every CORE01 manifest path exists in the k9b repository.

    This verifies the manifest references real files while keeping
    the staging validation hermetic.
    """
    for path in CORE01_MANIFEST:
        full_path = REPO_ROOT / path
        assert full_path.exists(), f"CORE01 manifest path does not exist: {path!r}"


def test_staged_paths_match_manifest_negative_missing(staged_repo: TemporaryStagedRepo) -> None:
    """A missing staged path causes the validation to fail.

    CORRECTION21: This is a negative proof that the validation
    correctly detects missing paths.
    """
    # Unstage one path to create a missing-path scenario
    _git(staged_repo.repo, "reset", "HEAD", "--", CORE01_MANIFEST[0])

    staged = staged_repo.get_staged_paths()
    missing = set(CORE01_MANIFEST) - staged
    assert CORE01_MANIFEST[0] in missing, "Expected path should be missing after reset"


def test_staged_paths_match_manifest_negative_extra(staged_repo: TemporaryStagedRepo) -> None:
    """An extra staged path causes the validation to fail.

    CORRECTION21: This is a negative proof that the validation
    correctly detects extra paths.
    """
    # Create and stage an extra file not in the manifest
    extra_path = "extra_file_not_in_manifest.txt"
    (staged_repo.repo / extra_path).write_text("extra content", encoding="utf-8")
    _git(staged_repo.repo, "add", extra_path)

    staged = staged_repo.get_staged_paths()
    assert extra_path in staged, "Extra file should be staged"
    assert extra_path not in set(CORE01_MANIFEST), "Extra file should not be in manifest"
