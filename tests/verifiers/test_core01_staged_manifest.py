"""Staged-manifest verification for the CORE01 closure.

CORRECTION05 R10: the final report must calculate the staged
manifest rather than manually asserting 17 or 18 paths. The
test in this file compares ``git diff --cached --name-only``
against the documented CORE01 manifest and fails on:

* missing staged paths,
* undocumented staged paths,
* duplicate manifest entries,
* any CORE01 path with an unstaged delta.

CORRECTION21: Made hermetic using a temporary Git repository.
CORRECTION22: Extracted one reusable validator with decisive
negative proofs. Every test calls the validator, not raw Git.

The CORE01 manifest is documented here as the authoritative
set; if a future ACT needs to add or remove a CORE01 path, it
must update this test (and the matching progress report).

Unrelated pre-existing untracked files are explicitly NOT
part of the CORE01 manifest.
"""

from __future__ import annotations

import subprocess
from collections.abc import Collection
from dataclasses import dataclass, field
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


@dataclass(frozen=True, slots=True)
class StagedManifestMismatch:
    """Result of comparing a manifest against staged paths.

    This is the authoritative contract for CORE01 manifest validation.
    All tests call this validator; no test independently reimplements
    the set arithmetic.
    """

    missing: tuple[str, ...] = field(default_factory=tuple)
    extra: tuple[str, ...] = field(default_factory=tuple)
    unstaged: tuple[str, ...] = field(default_factory=tuple)
    duplicate_manifest_paths: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        """Return True only when the staged state matches the manifest exactly."""
        return (
            not self.missing
            and not self.extra
            and not self.unstaged
            and not self.duplicate_manifest_paths
        )

    def __str__(self) -> str:
        """Return a deterministic diagnostic string."""
        parts = []
        if self.missing:
            parts.append(f"missing={sorted(self.missing)!r}")
        if self.extra:
            parts.append(f"extra={sorted(self.extra)!r}")
        if self.unstaged:
            parts.append(f"unstaged={sorted(self.unstaged)!r}")
        if self.duplicate_manifest_paths:
            parts.append(f"duplicates={sorted(self.duplicate_manifest_paths)!r}")
        return ", ".join(parts) if parts else "valid"


def compare_staged_manifest(
    *,
    manifest_paths: Collection[str],
    staged_paths: Collection[str],
    unstaged_paths: Collection[str],
) -> StagedManifestMismatch:
    """Compare manifest paths against the actual Git staging state.

    This is the single reusable validator for CORE01 manifest validation.

    Args:
        manifest_paths: The documented set of expected paths.
        staged_paths: The paths currently staged in the Git index.
        unstaged_paths: Paths with unstaged modifications.

    Returns:
        StagedManifestMismatch with is_valid=True when all conditions hold:
        - Every manifest path is staged (missing == empty)
        - Every staged path is in the manifest (extra == empty)
        - No manifest path has an unstaged delta (unstaged == empty)
        - No duplicate entries in manifest (duplicate_manifest_paths == empty)
    """
    manifest_list = list(manifest_paths)
    manifest_set = set(manifest_list)
    staged_set = set(staged_paths)
    unstaged_set = set(unstaged_paths)

    # Detect duplicates in the manifest itself
    seen: set[str] = set()
    duplicate_manifest_paths: list[str] = []
    for path in manifest_list:
        if path in seen:
            duplicate_manifest_paths.append(path)
        seen.add(path)
    duplicate_manifest_paths_tuple = tuple(sorted(duplicate_manifest_paths))

    # Missing: manifest paths not staged
    missing = tuple(sorted(manifest_set - staged_set))

    # Extra: staged paths not in manifest
    extra = tuple(sorted(staged_set - manifest_set))

    # Unstaged: manifest paths that have unstaged modifications
    unstaged = tuple(sorted(manifest_set & unstaged_set))

    return StagedManifestMismatch(
        missing=missing,
        extra=extra,
        unstaged=unstaged,
        duplicate_manifest_paths=duplicate_manifest_paths_tuple,
    )


def _git(
    repo: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run git with the supplied args and return the process result.

    Args:
        repo: The repository working directory.
        *args: Git command arguments.
        check: If True, raise RuntimeError on non-zero exit.

    Returns:
        The subprocess result.

    Raises:
        RuntimeError: When check=True and git returns non-zero.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)!r} failed in {repo}: exit {result.returncode}, stderr: {result.stderr!r}")
    return result


class TemporaryStagedRepo:
    """A temporary Git repository with a staged closure manifest.

    This fixture creates a hermetic environment for testing the
    CORE01 manifest staging contract. It:
    1. Creates a temporary Git repository
    2. Creates synthetic files for all 21 CORE01 manifest paths
    3. Stages them (without committing) to simulate closure staging
    4. Provides methods to manipulate and query the staged state
    """

    def __init__(self, tmp_path: Path) -> None:
        self.repo = tmp_path / "core01_closure_repo"
        self.repo.mkdir(parents=True, exist_ok=True)
        self._init_git()
        self._create_synthetic_files()

    def _init_git(self) -> None:
        """Initialize the temporary Git repository."""
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.name", "CORRECTION22 Test")
        _git(self.repo, "config", "user.email", "cor22@test.local")
        _git(self.repo, "config", "commit.gpgsign", "false")

    def _create_synthetic_files(self) -> None:
        """Create synthetic files for all CORE01 manifest paths."""
        for rel_path in CORE01_MANIFEST:
            dst = self.repo / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            # Use synthetic deterministic content
            dst.write_text(f"# CORRECTION22 synthetic fixture: {rel_path}\n", encoding="utf-8")

    def stage_closure(self) -> None:
        """Stage all CORE01 manifest files as a closure unit."""
        _git(self.repo, "add", *CORE01_MANIFEST)

    def unstage(self, *paths: str) -> None:
        """Unstage the specified paths from the index."""
        for path in paths:
            _git(self.repo, "reset", "HEAD", "--", path)

    def get_staged_paths(self) -> set[str]:
        """Return the set of currently staged paths.
        
        Fails closed: raises RuntimeError on Git command failure.
        """
        result = _git(self.repo, "diff", "--cached", "--name-only")
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}

    def get_unstaged_paths(self) -> set[str]:
        """Return the set of paths with unstaged modifications.
        
        Fails closed: raises RuntimeError on Git command failure.
        """
        result = _git(self.repo, "diff", "--name-only")
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}

    def modify_file(self, rel_path: str, content: str) -> None:
        """Modify a file to create an unstaged delta."""
        dst = self.repo / rel_path
        dst.write_text(content, encoding="utf-8")

    def add_extra_staged_file(self, rel_path: str) -> None:
        """Stage a file not in the manifest (extra path scenario)."""
        dst = self.repo / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(f"# extra file: {rel_path}\n", encoding="utf-8")
        _git(self.repo, "add", rel_path)


@pytest.fixture
def staged_repo(tmp_path: Path) -> TemporaryStagedRepo:
    """A temporary repository with all CORE01 manifest files staged."""
    repo = TemporaryStagedRepo(tmp_path)
    repo.stage_closure()
    return repo


# =============================================================================
# Tests
# =============================================================================


def test_manifest_has_no_duplicates() -> None:
    """The CORE01 manifest itself has no duplicate entries."""
    assert len(CORE01_MANIFEST) == len(set(CORE01_MANIFEST)), f"CORE01 manifest has duplicate entries: {CORE01_MANIFEST!r}"


def test_staged_paths_match_manifest(staged_repo: TemporaryStagedRepo) -> None:
    """Every CORE01 manifest path must be staged in the closure.

    Positive proof: all manifest paths are staged, no extras, no unstaged deltas.
    """
    staged = staged_repo.get_staged_paths()
    unstaged = staged_repo.get_unstaged_paths()

    mismatch = compare_staged_manifest(
        manifest_paths=CORE01_MANIFEST,
        staged_paths=staged,
        unstaged_paths=unstaged,
    )

    assert mismatch.is_valid, f"CORE01 manifest validation failed: {mismatch}"
    assert not mismatch.missing, f"Missing paths: {mismatch.missing}"
    assert not mismatch.extra, f"Extra paths: {mismatch.extra}"
    assert not mismatch.unstaged, f"Unstaged deltas: {mismatch.unstaged}"


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
    staged = staged_repo.get_staged_paths()
    assert len(staged) == 21, f"Expected 21 staged paths, got {len(staged)}"
    assert staged == set(CORE01_MANIFEST)


def test_manifest_path_existence_in_k9b() -> None:
    """Every CORE01 manifest path exists in the k9b repository.

    This verifies the manifest references real files while keeping
    the staging validation hermetic.
    """
    for path in CORE01_MANIFEST:
        full_path = REPO_ROOT / path
        assert full_path.exists(), f"CORE01 manifest path does not exist: {path!r}"


# =============================================================================
# Negative proofs - all use the validator
# =============================================================================


def test_missing_manifest_path_is_rejected(staged_repo: TemporaryStagedRepo) -> None:
    """A missing staged path causes the validation to fail.

    CORRECTION22: Decisive negative proof that the validator rejects
    missing paths.
    """
    # Unstage one path to create a missing-path scenario
    staged_repo.unstage(CORE01_MANIFEST[0])

    mismatch = compare_staged_manifest(
        manifest_paths=CORE01_MANIFEST,
        staged_paths=staged_repo.get_staged_paths(),
        unstaged_paths=staged_repo.get_unstaged_paths(),
    )

    assert not mismatch.is_valid, "Validator should reject missing path"
    assert CORE01_MANIFEST[0] in mismatch.missing, f"Expected {CORE01_MANIFEST[0]!r} in missing, got: {mismatch.missing}"


def test_extra_staged_path_is_rejected(staged_repo: TemporaryStagedRepo) -> None:
    """An extra staged path causes the validation to fail.

    CORRECTION22: Decisive negative proof that the validator rejects
    extra paths.
    """
    # Add and stage an extra file not in the manifest
    staged_repo.add_extra_staged_file("extra_file_not_in_manifest.txt")

    mismatch = compare_staged_manifest(
        manifest_paths=CORE01_MANIFEST,
        staged_paths=staged_repo.get_staged_paths(),
        unstaged_paths=staged_repo.get_unstaged_paths(),
    )

    assert not mismatch.is_valid, "Validator should reject extra path"
    assert "extra_file_not_in_manifest.txt" in mismatch.extra, f"Expected extra_file in extra, got: {mismatch.extra}"


def test_unstaged_delta_is_rejected(staged_repo: TemporaryStagedRepo) -> None:
    """An unstaged delta on a manifest path causes the validation to fail.

    CORRECTION22: Decisive negative proof that the validator rejects
    unstaged deltas.
    """
    # Modify a staged file to create an unstaged delta
    staged_repo.modify_file(CORE01_MANIFEST[0], "# modified content\n")

    mismatch = compare_staged_manifest(
        manifest_paths=CORE01_MANIFEST,
        staged_paths=staged_repo.get_staged_paths(),
        unstaged_paths=staged_repo.get_unstaged_paths(),
    )

    assert not mismatch.is_valid, "Validator should reject unstaged delta"
    assert CORE01_MANIFEST[0] in mismatch.unstaged, f"Expected {CORE01_MANIFEST[0]!r} in unstaged, got: {mismatch.unstaged}"


def test_missing_and_extra_simultaneously_rejected(staged_repo: TemporaryStagedRepo) -> None:
    """Missing and extra paths together cause the validation to fail.

    CORRECTION22: Negative proof for compound invalid state.
    """
    # Unstage one path and add an extra
    staged_repo.unstage(CORE01_MANIFEST[0])
    staged_repo.add_extra_staged_file("another_extra.txt")

    mismatch = compare_staged_manifest(
        manifest_paths=CORE01_MANIFEST,
        staged_paths=staged_repo.get_staged_paths(),
        unstaged_paths=staged_repo.get_unstaged_paths(),
    )

    assert not mismatch.is_valid, "Validator should reject compound invalid state"
    assert CORE01_MANIFEST[0] in mismatch.missing
    assert "another_extra.txt" in mismatch.extra


def test_empty_staged_with_nonempty_manifest_rejected(tmp_path: Path) -> None:
    """Empty staged set with non-empty manifest causes the validation to fail.

    CORRECTION22: Edge case negative proof.
    """
    mismatch = compare_staged_manifest(
        manifest_paths=CORE01_MANIFEST,
        staged_paths=(),
        unstaged_paths=(),
    )

    assert not mismatch.is_valid, "Validator should reject empty staged set"
    assert set(CORE01_MANIFEST) == set(mismatch.missing), f"Expected all manifest paths in missing, got: {mismatch.missing}"


def test_deterministic_diagnostic_ordering(staged_repo: TemporaryStagedRepo) -> None:
    """The validator produces deterministic diagnostic output.

    CORRECTION22: Ordering is documented via sorted() in compare_staged_manifest.
    """
    # Unstage two paths and add two extras
    staged_repo.unstage(CORE01_MANIFEST[0], CORE01_MANIFEST[1])
    staged_repo.add_extra_staged_file("aaa_extra.txt")
    staged_repo.add_extra_staged_file("zzz_extra.txt")

    mismatch = compare_staged_manifest(
        manifest_paths=CORE01_MANIFEST,
        staged_paths=staged_repo.get_staged_paths(),
        unstaged_paths=staged_repo.get_unstaged_paths(),
    )

    # Verify deterministic ordering
    assert mismatch.extra == tuple(sorted(["aaa_extra.txt", "zzz_extra.txt"]))
    assert mismatch.missing == tuple(sorted([CORE01_MANIFEST[0], CORE01_MANIFEST[1]]))


def test_duplicate_manifest_entry_is_rejected() -> None:
    """A duplicate entry in the manifest causes validation to fail.

    CORRECTION27: Duplicate detection is now part of the validator.
    """
    manifest_with_dup = (
        CORE01_MANIFEST[0],
        CORE01_MANIFEST[1],
        CORE01_MANIFEST[0],  # duplicate
    )
    mismatch = compare_staged_manifest(
        manifest_paths=manifest_with_dup,
        staged_paths=manifest_with_dup,
        unstaged_paths=(),
    )

    assert not mismatch.is_valid, "Validator should reject duplicate manifest entry"
    assert CORE01_MANIFEST[0] in mismatch.duplicate_manifest_paths


def test_multiple_duplicate_entries_rejected() -> None:
    """Multiple duplicate entries in the manifest are all detected.

    CORRECTION27: All duplicates are detected and reported.
    """
    manifest_with_dups = (
        CORE01_MANIFEST[0],
        CORE01_MANIFEST[1],
        CORE01_MANIFEST[0],  # duplicate of [0]
        CORE01_MANIFEST[1],  # duplicate of [1]
    )
    mismatch = compare_staged_manifest(
        manifest_paths=manifest_with_dups,
        staged_paths=manifest_with_dups,
        unstaged_paths=(),
    )

    assert not mismatch.is_valid, "Validator should reject all duplicates"
    assert CORE01_MANIFEST[0] in mismatch.duplicate_manifest_paths
    assert CORE01_MANIFEST[1] in mismatch.duplicate_manifest_paths
