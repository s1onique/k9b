# mypy: disable-error-code="index,assignment,operator,arg-type,union-attr,attr-defined,return-value,no-any-return,no-untyped-call,no-untyped-def,var-annotated,call-overload,comparison-overlap"
"""CORRECTION14: typed evidence-result dataclass tests.

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
    RepositoryGateResult,
)


def test_command_result_is_frozen() -> None:
    """The :class:`CommandResult` dataclass is frozen."""
    result = CommandResult(
        argv=("git", "rev-parse", "HEAD"),
        returncode=0,
        stdout_sha256="a" * 64,
        stderr_sha256="b" * 64,
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
    gate = RepositoryGateResult(
        name="pytest",
        argv=("pytest",),
        returncode=0,
        stdout_sha256="a" * 64,
        stderr_sha256="b" * 64,
    )
    with pytest.raises(Exception):
        gate.returncode = 1  # type: ignore[misc]