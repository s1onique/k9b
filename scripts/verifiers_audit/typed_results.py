"""CORRECTION14: typed evidence-result dataclasses.

Every claim in the final-classification.md file MUST be derived
from a typed :class:`CommandResult` /
:class:`EvidenceTransactionResult` /
:class:`RepositoryGateResult` measurement.  Hardcoded ``PASS``
rows are forbidden.  An unmeasured claim is rendered
``UNMEASURED`` or ``FAILED``; an absent row is omitted from the
output entirely (the lifecycle rows for ``C`` / ``T`` /
``leamas_protocol_E`` are still emitted with their
``ABSENT`` / ``BLOCKED`` values because they are explicit
closure-topology constants, not measurements).

The dataclasses are frozen so the renderer cannot mutate them
after construction.  Every field is hashable so the producer
can compute a deterministic bundle hash without mutable state.

Public surface:

* :class:`CommandResult` - one executed command and its
  outcome (argv, returncode, stdout/stderr SHA-256, status).
* :class:`EvidenceTransactionResult` - the entire detached
  evidence transaction (base_oid, subject_oid, git_commands,
  ruff_result, publication_status, authoritative_hashes).
* :class:`RepositoryGateResult` - one captured post-subject
  gate command (name, argv, returncode, stdout/stderr SHA-256).
* :class:`ClosureTopology` - the deterministic closure
  topology record (F14, F14_tree, plan_blob, S14, S14_tree,
  parent_F14, parent_S14).
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

CommandStatus = Literal["passed", "failed", "skipped"]
"""The terminal status of a single executed command.

* ``"passed"`` - the command exited zero AND produced the
  expected outcome (e.g. ``git diff`` returned a path tuple).
* ``"failed"`` - the command exited non-zero OR returned an
  outcome the caller has rejected (e.g. a Ruff run with
  findings when the contract required clean output).
* ``"skipped"`` - the command was not invoked because the
  preconditions for invocation were not met (empty Python
  range; non-zero exit impossible to satisfy).
"""


PublicationStatus = Literal["ready_to_publish", "published", "failed"]
"""The terminal publication status of the evidence transaction.

* ``"ready_to_publish"`` - every required artifact is present
  on disk; the staging directory is ready for rename.
* ``"published"`` - the rename succeeded; the bundle is
  immutable from this point forward.
* ``"failed"`` - any precondition failed; the staging
  directory was removed and the final destination does not
  exist.
"""


@dataclass(frozen=True)
class CommandResult:
    """CORRECTION14: one executed command and its outcome.

    * ``argv`` - the executed argv (tuple, never list).
    * ``returncode`` - the subprocess exit code.
    * ``stdout_sha256`` - SHA-256 of the captured stdout bytes.
    * ``stderr_sha256`` - SHA-256 of the captured stderr bytes.
    * ``status`` - the terminal status (``"passed"`` /
      ``"failed"`` / ``"skipped"``).

    A ``CommandResult`` is the SOLE authority for whether a
    command ``passed``.  Renderers MUST NOT emit ``PASS`` for a
    command absent from the typed result; absent commands
    render as ``UNMEASURED``.
    """

    argv: tuple[str, ...]
    returncode: int
    stdout_sha256: str
    stderr_sha256: str
    status: CommandStatus


@dataclass(frozen=True)
class EvidenceTransactionResult:
    """CORRECTION14: the entire detached evidence transaction.

    * ``base_oid`` - the resolved full object ID of BASE.
    * ``subject_oid`` - the resolved full object ID of SUBJECT.
    * ``git_commands`` - every recorded Git command result.
    * ``ruff_result`` - the Ruff result (or ``None`` when Ruff
      was not invoked - empty Python range).
    * ``publication_status`` - the terminal publication status.
    * ``authoritative_hashes`` - SHA-256 of every authoritative
      final artifact (relpath -> hex digest).
    """

    base_oid: str
    subject_oid: str
    git_commands: tuple[CommandResult, ...]
    ruff_result: CommandResult | None
    publication_status: PublicationStatus
    authoritative_hashes: Mapping[str, str]


@dataclass(frozen=True)
class RepositoryGateResult:
    """CORRECTION14: one captured post-subject gate command.

    * ``name`` - the gate's logical name (e.g. ``"ruff"``,
      ``"mypy"``, ``"pytest"``, ``"audit-check"``,
      ``"verify-act-local"``).
    * ``argv`` - the executed argv (tuple, never list).
    * ``returncode`` - the subprocess exit code.
    * ``stdout_sha256`` - SHA-256 of the captured stdout bytes.
    * ``stderr_sha256`` - SHA-256 of the captured stderr bytes.

    The gate is treated as ``passed`` when ``returncode == 0``;
    renderers MUST use the explicit ``returncode`` field and
    MUST NOT assume a successful run from the mere presence of
    the gate row.
    """

    name: str
    argv: tuple[str, ...]
    returncode: int
    stdout_sha256: str
    stderr_sha256: str


@dataclass(frozen=True)
class ClosureTopology:
    """CORRECTION14: the deterministic closure-topology record.

    * ``F14`` - the CORRECTION14 plan-freeze commit hash.
    * ``F14_tree`` - the tree hash of the F14 commit.
    * ``plan_blob`` - the SHA-256 of the plan file bytes.
    * ``S14`` - the CORRECTION14 subject commit hash (None
      when not yet authored).
    * ``S14_tree`` - the tree hash of the S14 commit (None
      when S14 is absent).
    * ``parent_F14`` - the parent of F14 (= S13).
    * ``parent_S14`` - the parent of S14 (= F14) when S14 is
      present; None otherwise.

    The dataclass is the SOLE authority for which commits
    bound the closure.  Renderers MUST consult it directly
    instead of hardcoding lifecycle strings.
    """

    F14: str
    F14_tree: str
    plan_blob: str
    S14: str | None
    S14_tree: str | None
    parent_F14: str
    parent_S14: str | None


__all__ = [
    "ClosureTopology",
    "CommandResult",
    "CommandStatus",
    "EvidenceTransactionResult",
    "PublicationStatus",
    "RepositoryGateResult",
]