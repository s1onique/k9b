"""Shared history-bound verifier support.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION05
-CI-SHARD-PORTABILITY-AND-PROMOTION-REGRESSION-CLOSURE01:

History-bound verifier tests MUST go through
:func:`require_commit_available` so a shallow CI clone fails closed
with a bounded diagnostic ("CI must use full git history: enable
``actions/checkout`` with ``fetch-depth: 0``"). Abbreviated SHAs
MUST NOT be used anywhere in the verifier surface because an
abbreviated ``b1294cee`` resolves to whichever nearby commit Git
picks in the current view, which is brittle and unauditable.

The helper fails fast, with no silent auto-fetch, and produces a
machine-parseable diagnostic that names the missing commit and the
required CI configuration. The intent is that a regression in CI
checkout is recoverable from the diagnostic alone -- there is no
hidden remote fetch.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# Canonical historical base SHA MUST be referenced by its full 40-char
# form so the verifier surface is auditable and immune to abbreviation
# drift across runner checkouts. The abbreviated ``b1294cee`` is
# forbidden by the test suite below; the test guard is the parser
# itself.
CANONICAL_HISTORICAL_BASE_FULL = (
    "b1294cee7cbfc1c1b22f0c11282eaab474f8dbb8"
)


class HistoricalCommitUnavailable(RuntimeError):
    """Bounded exception for missing-history CI failures.

    Tests MUST let this exception propagate to pytest so the
    diagnostic is surfaced directly. Catch handlers should
    ``raise ... from cause`` to preserve root cause.
    """


def _git(
    *args: str, cwd: Path, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def require_commit_available(
    repo_root: Path,
    commit: str = CANONICAL_HISTORICAL_BASE_FULL,
) -> None:
    """Verify ``commit`` is available in the local git history.

    Raises :class:`HistoricalCommitUnavailable` with a bounded
    diagnostic when the commit is missing (typically because the
    repository was cloned with ``--depth 1``/``fetch-depth: 1``).
    The helper never fetches from a remote source on the caller's
    behalf -- CI is expected to be configured with full history.
    """
    if not isinstance(commit, str) or len(commit) != 40:
        raise ValueError(
            "commit MUST be a 40-char full SHA; abbreviated SHAs are "
            "forbidden in the verifier surface to avoid Git picking "
            "an arbitrary nearby commit"
        )

    shallow_proc = _git(
        "rev-parse",
        "--is-shallow-repository",
        cwd=repo_root,
        check=False,
    )
    if shallow_proc.stdout.strip() == "true":
        raise HistoricalCommitUnavailable(
            "CI_REPOSITORY_SHALLOW=true -- the verifier needs the full "
            "git history to read the canonical historical base "
            f"{commit!r}. Configure actions/checkout with "
            "fetch-depth: 0 (see .github/workflows/verify.yml) before "
            "re-running."
        )

    # ``cat-file -e <commit>`` resolves ANY object in the local
    # repository (commit / tag / tree) and is the canonical
    # "is the commit already in this clone?" check. If the
    # canonical base commit was fetch-depleted, the command exits
    # non-zero and we surface a bounded diagnostic.
    available_proc = _git(
        "cat-file",
        "-e",
        commit,
        cwd=repo_root,
        check=False,
    )
    if available_proc.returncode != 0:
        raise HistoricalCommitUnavailable(
            "HISTORICAL_BASE_PRESENT=false -- the verifier cannot "
            f"resolve {commit!r} in the local history. Configure "
            "actions/checkout with fetch-depth: 0 so the full "
            "history is cloned."
        )

    ancestor_proc = _git(
        "merge-base",
        "--is-ancestor",
        commit,
        "HEAD",
        cwd=repo_root,
        check=False,
    )
    if ancestor_proc.returncode != 0:
        raise HistoricalCommitUnavailable(
            f"HISTORICAL_BASE_IS_ANCESTOR=false -- {commit!r} is not "
            "an ancestor of HEAD. The verifier MUST refuse to compare "
            "the current tree against an unrelated commit."
        )


__all__ = [
    "CANONICAL_HISTORICAL_BASE_FULL",
    "HistoricalCommitUnavailable",
    "require_commit_available",
]
