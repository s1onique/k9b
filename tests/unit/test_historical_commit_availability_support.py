"""Tests for the history-bound verifier diagnostic support.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION05:

* Abbreviated SHAs MUST be rejected at the support boundary.
* Missing commits MUST raise ``HistoricalCommitUnavailable``
  with the canonical ``fetch-depth: 0`` diagnostic.
* Full SHAs in a real repository MUST pass.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.verifiers.historical_commit_availability_support import (  # noqa: E402
    CANONICAL_HISTORICAL_BASE_FULL,
    HistoricalCommitUnavailable,
    require_commit_available,
)


def test_require_commit_available_aborts_on_abbreviated_sha(tmp_path: Path) -> None:
    """An abbreviated SHA is rejected at the helper boundary so the
    verifier surface is immune to git abbreviation drift."""
    with pytest.raises(ValueError) as exc:
        require_commit_available(tmp_path, commit="b1294cee")
    assert "abbreviated SHAs are forbidden" in str(exc.value)


def test_require_commit_available_aborts_on_short_sha(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        require_commit_available(
            tmp_path, commit="b1294cee7cbfc1c1b22f0c11282eaab474f8dbb"
        )


def test_require_commit_available_passes_for_real_commit(tmp_path: Path) -> None:
    """The historical base is the parent commit of HEAD in this
    worktree (the repository created at promotion start). It MUST
    pass the helper uneventfully."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    (repo / "README.md").write_text("hello", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    require_commit_available(repo, commit=base_sha)


def test_require_commit_available_raises_when_commit_missing(tmp_path: Path) -> None:
    """A non-existent commit SHA MUST surface the canonical diagnostic."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    with pytest.raises(HistoricalCommitUnavailable) as exc:
        require_commit_available(repo)
    diagnostic = str(exc.value)
    assert "HISTORICAL_BASE_PRESENT=false" in diagnostic
    assert "fetch-depth: 0" in diagnostic
    assert CANONICAL_HISTORICAL_BASE_FULL in diagnostic
