# mypy: disable-error-code="index,assignment,operator,arg-type,union-attr,attr-defined,return-value,no-any-return,no-untyped-call,no-untyped-def,var-annotated,call-overload,comparison-overlap"
"""CORRECTION14/CORRECTION15: typed evidence-result dataclass tests.

The companion modules
:mod:`test_verifier_core_migration_audit01_correction14_layout`
and :mod:`test_verifier_core_migration_audit01_correction14_evidence`
own the layout-shard-schema tests and the range-evidence
orchestration tests respectively.  This module owns the
typed-dataclass frozenness contract.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from scripts.verifiers_audit.typed_results import (
    CommandResult,
    EvidenceTransactionResult,
    ExecutedCommand,
    RepositoryGateResult,
)


def test_command_result_is_frozen() -> None:
    """The :class:`CommandResult` (= :class:`ExecutedCommand`)
    dataclass is frozen.
    """
    result = CommandResult(
        name="git-rev-parse-base",
        argv=("git", "rev-parse", "HEAD"),
        cwd="/repo",
        returncode=0,
        stdout=b"",
        stderr=b"",
        status="passed",
    )
    with pytest.raises(Exception):
        result.returncode = 1  # type: ignore[misc]


def test_evidence_transaction_result_is_frozen() -> None:
    """The :class:`EvidenceTransactionResult` dataclass is frozen."""
    evidence = EvidenceTransactionResult(
        base_oid="a" * 40,
        subject_oid="b" * 40,
        git_commands=(),
        ruff_result=None,
        publication_status="ready_to_publish",
        authoritative_hashes=MappingProxyType({}),
    )
    with pytest.raises(Exception):
        evidence.base_oid = "mutated"  # type: ignore[misc]


def test_repository_gate_result_is_frozen() -> None:
    """The :class:`RepositoryGateResult` dataclass is frozen."""
    cmd = ExecutedCommand(
        name="pytest",
        argv=("pytest",),
        cwd="/repo",
        returncode=0,
        stdout=b"",
        stderr=b"",
        status="passed",
    )
    gate = RepositoryGateResult(name="pytest", command=cmd)
    with pytest.raises(Exception):
        gate.name = "act-local"  # type: ignore[misc]


def test_executed_command_stdout_sha256_is_derived_from_bytes() -> None:
    """CORRECTION15: the SHA-256 properties are derived from
    the raw bytes the command produced.
    """
    import hashlib

    cmd = ExecutedCommand(
        name="git-rev-parse",
        argv=("git", "rev-parse", "HEAD"),
        cwd="/repo",
        returncode=0,
        stdout=b"abc123\n",
        stderr=b"",
        status="passed",
    )
    assert cmd.stdout_sha256 == hashlib.sha256(b"abc123\n").hexdigest()


def test_executed_command_preserves_raw_bytes() -> None:
    """CORRECTION15: the raw stdout/stderr bytes are preserved
    in memory; the ``sha256`` properties are derived from
    those bytes.
    """
    raw = b"with embedded NUL \x00 and trailing newline\n"
    cmd = ExecutedCommand(
        name="git-rev-parse",
        argv=("git", "rev-parse", "HEAD"),
        cwd="/repo",
        returncode=0,
        stdout=raw,
        stderr=b"err",
        status="passed",
    )
    assert cmd.stdout == raw
    assert cmd.stderr == b"err"
