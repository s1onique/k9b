"""CORRECTION16: detached range evidence topology resolver.

The :mod:`range_evidence_orchestrator` module grew large
during the C16 uplift.  The topology-derivation helpers
are extracted into this module so the orchestrator file
remains under the LLM-friendly line limit.

The functions here are the canonical ``derive_repository_topology``
and the related ``_resolve_git_oid`` / ``_assert_topology_evidence``
helpers.  Every Git invocation goes through the seam - the
caller MUST pass the injected :class:`GitRunner`.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import os

from scripts.verifiers_audit.range_evidence_helpers import GitRunner
from scripts.verifiers_audit.scope import RangeResolutionError
from scripts.verifiers_audit.typed_results import (
    ExecutedCommand,
    RepositoryTopology,
    TransactionGitCommand,
)

CORRECTION16_PLAN_PATH = (
    "docs/closure-plans/ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01-CORRECTION16.json"
)
"""CORRECTION16: the canonical plan path relative to the repo root."""

CORRECTION16_F16_REF = "F16"
CORRECTION16_S16_REF = "S16"

CORRECTION18_PLAN_PATH = (
    "docs/closure-plans/ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01-CORRECTION18.json"
)
"""CORRECTION18: the canonical plan path relative to the repo root."""

CORRECTION18_F18_REF = "F18"
CORRECTION18_S18_REF = "S18"


def _resolve_git_oid(
    *,
    git_runner: GitRunner,
    ref: str,
    suffix: str,
    repo_root,
    name: str,
) -> tuple[ExecutedCommand, str]:
    """Run a single ``git rev-parse`` invocation through the seam.

    CORRECTION16: the function is the canonical helper used
    by the topology / range resolvers.  The returned tuple
    is ``(ExecutedCommand, decoded-oid)``.  The decoded oid
    is always taken from the captured stdout bytes.
    """
    argv: tuple[str, ...] = ("git", "rev-parse", f"{ref}{suffix}")
    command = git_runner.run(argv, cwd=repo_root, name=name)
    if command.status == "failed":
        raise RangeResolutionError(
            base=ref,
            subject=ref,
            argv=argv,
            returncode=command.returncode,
            stderr=os.fsdecode(command.stderr) if command.stderr else "",
            stage=name,  # type: ignore[arg-type]  # mypy: extended literal
        )
    return command, os.fsdecode(command.stdout).strip()


def derive_repository_topology(
    *,
    git_runner: GitRunner,
    repo_root,
    f16_ref: str = CORRECTION16_F16_REF,
    s16_ref: str = CORRECTION16_S16_REF,
    plan_path: str = CORRECTION16_PLAN_PATH,
) -> tuple[tuple[TransactionGitCommand, ...], RepositoryTopology]:
    """Derive the F16 / S16 topology from the Git transcript.

    CORRECTION16: the function runs the seven topology
    queries through the seam and returns BOTH the typed
    tuple of :class:`TransactionGitCommand` records AND the
    :class:`RepositoryTopology` derived from the captured
    stdout bytes.  No caller-supplied environment variable
    is read - the transcript is the SOLE authority.
    """
    records: list[TransactionGitCommand] = []

    f16_commit, F16_full = _resolve_git_oid(
        git_runner=git_runner,
        ref=f16_ref,
        suffix="^{commit}",
        repo_root=repo_root,
        name="git-rev-parse-f16-commit",
    )
    records.append(
        TransactionGitCommand(command=f16_commit, kind="topology")
    )

    f16_tree_cmd, F16_tree = _resolve_git_oid(
        git_runner=git_runner,
        ref=f16_ref,
        suffix="^{tree}",
        repo_root=repo_root,
        name="git-rev-parse-f16-tree",
    )
    records.append(
        TransactionGitCommand(command=f16_tree_cmd, kind="topology")
    )

    f16_parent_cmd, parent_F16 = _resolve_git_oid(
        git_runner=git_runner,
        ref=f16_ref,
        suffix="^",
        repo_root=repo_root,
        name="git-rev-parse-f16-parent",
    )
    records.append(
        TransactionGitCommand(command=f16_parent_cmd, kind="topology")
    )

    plan_path_argv = (
        "git",
        "rev-parse",
        f"{f16_ref}:{plan_path}",
    )
    plan_path_cmd = git_runner.run(
        plan_path_argv, cwd=repo_root, name="git-rev-parse-f16-plan-blob"
    )
    if plan_path_cmd.status == "failed":
        raise RangeResolutionError(
            base=f16_ref,
            subject=f16_ref,
            argv=plan_path_argv,
            returncode=plan_path_cmd.returncode,
            stderr=os.fsdecode(plan_path_cmd.stderr)
            if plan_path_cmd.stderr else "",
            stage="git-rev-parse-f16-plan-blob",
        )
    plan_blob = os.fsdecode(plan_path_cmd.stdout).strip()
    records.append(
        TransactionGitCommand(command=plan_path_cmd, kind="topology")
    )

    s16_commit, S16_full = _resolve_git_oid(
        git_runner=git_runner,
        ref=s16_ref,
        suffix="^{commit}",
        repo_root=repo_root,
        name="git-rev-parse-s16-commit",
    )
    records.append(
        TransactionGitCommand(command=s16_commit, kind="topology")
    )

    s16_tree_cmd, S16_tree = _resolve_git_oid(
        git_runner=git_runner,
        ref=s16_ref,
        suffix="^{tree}",
        repo_root=repo_root,
        name="git-rev-parse-s16-tree",
    )
    records.append(
        TransactionGitCommand(command=s16_tree_cmd, kind="topology")
    )

    s16_parent_cmd, parent_S16 = _resolve_git_oid(
        git_runner=git_runner,
        ref=s16_ref,
        suffix="^",
        repo_root=repo_root,
        name="git-rev-parse-s16-parent",
    )
    records.append(
        TransactionGitCommand(command=s16_parent_cmd, kind="topology")
    )

    topology = RepositoryTopology(
        F16=F16_full,
        F16_tree=F16_tree,
        plan_blob=plan_blob,
        S16=S16_full,
        S16_tree=S16_tree,
        parent_F16=parent_F16,
        parent_S16=parent_S16,
        plan_path=plan_path,
    )
    return tuple(records), topology


def assert_topology_evidence(
    *,
    git_records: tuple[TransactionGitCommand, ...],
    topology: RepositoryTopology,
) -> None:
    """Assert the topology was derived from the transcript (CORRECTION16)."""
    if not git_records:
        raise ValueError("derive_repository_topology returned no records")
    expected_kinds = {"topology"}
    for record in git_records:
        if record.kind not in expected_kinds:
            raise ValueError(
                f"unexpected kind {record.kind!r} in topology records"
            )
    if topology.parent_S16 != topology.F16:
        raise ValueError(
            f"parent_S16={topology.parent_S16!r} != F16={topology.F16!r}"
        )


__all__ = [
    "CORRECTION16_F16_REF",
    "CORRECTION16_PLAN_PATH",
    "CORRECTION16_S16_REF",
    "CORRECTION18_F18_REF",
    "CORRECTION18_PLAN_PATH",
    "CORRECTION18_S18_REF",
    "assert_topology_evidence",
    "derive_repository_topology",
]
