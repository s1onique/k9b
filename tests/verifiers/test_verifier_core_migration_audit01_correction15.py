"""CORRECTION15: typed-dataclass and claim-derivation tests.

This module tests the typed result dataclasses introduced
in :mod:`scripts.verifiers_audit.typed_results` and the
named claim-derivation functions introduced in
:mod:`scripts.verifiers_audit.range_evidence_classification`.

CORRECTION16: the tests use the ``F16`` / ``S16`` keyword
arguments (the canonical CORRECTION16 names); the
``F15`` / ``S15`` aliases are preserved as properties only.

The module re-uses the audit01 family split (no top-level
fixtures) so the
``canonical_audit_artifacts_remain_unchanged`` autouse
fixture continues to protect the canonical artifacts.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
from dataclasses import FrozenInstanceError

import pytest

from scripts.verifiers_audit.range_evidence_classification import (
    build_final_classification,
    derive_audit_check,
    derive_bundle_completeness,
    derive_bundle_root_hash,
    derive_git_diff_cardinality,
    derive_publication_status,
    derive_range_resolution,
    derive_ruff_invocation,
)
from scripts.verifiers_audit.typed_results import (
    BundleValidationResult,
    ClosureTopology,
    EvidenceTransactionResult,
    ExecutedCommand,
    RepositoryGateResult,
)


def _executed(
    *,
    name: str = "git-rev-parse-base",
    argv: tuple[str, ...] = ("git", "rev-parse", "--verify", "BASE^{commit}"),
    stdout: bytes = b"abc123\n",
    stderr: bytes = b"",
    returncode: int = 0,
    cwd: str = "/repo",
) -> ExecutedCommand:
    return ExecutedCommand(
        name=name,
        argv=argv,
        cwd=cwd,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        status="passed" if returncode == 0 else "failed",
    )


def test_executed_command_is_frozen() -> None:
    cmd = _executed()
    with pytest.raises(FrozenInstanceError):
        cmd.argv = ("x",)  # type: ignore[misc]


def test_executed_command_sha256_is_derived_from_bytes() -> None:
    cmd = _executed(stdout=b"hello\n", stderr=b"")
    import hashlib

    assert cmd.stdout_sha256 == hashlib.sha256(b"hello\n").hexdigest()
    assert cmd.stderr_sha256 == hashlib.sha256(b"").hexdigest()


def test_executed_command_preserves_raw_bytes() -> None:
    raw = b"with embedded NUL \x00 and trailing newline\n"
    cmd = _executed(stdout=raw)
    assert cmd.stdout == raw


def test_repository_gate_result_is_frozen() -> None:
    gate = RepositoryGateResult(
        name="audit-check",
        command=_executed(name="audit-check"),
    )
    with pytest.raises(FrozenInstanceError):
        gate.name = "act-local"  # type: ignore[misc]


def test_repository_gate_name_is_literal() -> None:
    cmd = _executed(name="audit-check")
    gate = RepositoryGateResult(name="audit-check", command=cmd)
    assert gate.name == "audit-check"
    assert gate.name in {
        "audit01-pytest",
        "audit01-ruff",
        "audit01-mypy",
        "audit-check",
        "act-local",
        "diff-check",
        "worktree-clean",
    }


def test_bundle_validation_result_is_valid() -> None:
    validation = BundleValidationResult(
        declared_artifacts=("a.json", "b.json"),
        observed_artifacts=("a.json", "b.json"),
        missing_artifacts=(),
        extra_artifacts=(),
    )
    assert validation.is_valid


def test_bundle_validation_result_is_invalid_when_missing() -> None:
    validation = BundleValidationResult(
        declared_artifacts=("a.json", "b.json"),
        observed_artifacts=("a.json",),
        missing_artifacts=("b.json",),
        extra_artifacts=(),
    )
    assert not validation.is_valid


def test_closure_topology_accepts_f16_identity() -> None:
    topo = ClosureTopology(
        F16="f16-hash",
        F16_tree="f16-tree",
        plan_blob="plan-blob",
        S16="s16-hash",
        S16_tree="s16-tree",
        parent_F16="s15-hash",
        parent_S16="f16-hash",
    )
    assert topo.F16 == "f16-hash"
    assert topo.S16 == "s16-hash"
    assert topo.parent_S16 == "f16-hash"


def test_closure_topology_f15_aliases() -> None:
    topo = ClosureTopology(
        F16="f16-hash",
        F16_tree="f16-tree",
        plan_blob="plan-blob",
        S16="s16-hash",
        S16_tree="s16-tree",
        parent_F16="s15-hash",
        parent_S16="f16-hash",
    )
    # CORRECTION14 backwards-compat aliases.
    assert topo.F15 == "f16-hash"
    assert topo.F15_tree == "f16-tree"
    assert topo.S15 == "s16-hash"
    assert topo.S15_tree == "s16-tree"
    assert topo.parent_F15 == "s15-hash"
    assert topo.parent_S15 == "f16-hash"


def test_derive_audit_check_pass() -> None:
    gate = RepositoryGateResult(
        name="audit-check", command=_executed(name="audit-check")
    )
    claim = derive_audit_check((gate,))
    assert claim.status == "PASS"
    assert claim.value == "PASS"


def test_derive_audit_check_failed() -> None:
    gate = RepositoryGateResult(
        name="audit-check",
        command=_executed(
            name="audit-check",
            returncode=2,
            argv=("python", "audit.py", "--check"),
        ),
    )
    claim = derive_audit_check((gate,))
    assert claim.status == "FAILED"


def test_derive_audit_check_unmeasured() -> None:
    claim = derive_audit_check(())
    assert claim.status == "UNMEASURED"


def test_derive_git_diff_cardinality_pass() -> None:
    """CORRECTION16: the count is 1 git-diff + 5 rev-parse (topology+range)."""
    evidence = EvidenceTransactionResult(
        base_oid="a" * 40,
        subject_oid="b" * 40,
        git_commands=(
            _executed(name="git-rev-parse-f16-commit"),
            _executed(name="git-rev-parse-f16-tree"),
            _executed(name="git-rev-parse-f16-parent"),
            _executed(name="git-rev-parse-f16-plan-blob"),
            _executed(name="git-rev-parse-s16-commit"),
            _executed(name="git-rev-parse-s16-tree"),
            _executed(name="git-rev-parse-s16-parent"),
            _executed(name="git-rev-parse-base"),
            _executed(name="git-rev-parse-subject"),
            _executed(
                name="git-diff-factory",
                argv=("git", "diff", "--name-only", "-z", "a" * 40, "b" * 40),
            ),
        ),
        ruff_result=None,
        publication_status="ready_to_publish",
        authoritative_hashes={},
    )
    claim = derive_git_diff_cardinality(evidence)
    assert claim.status == "PASS"
    assert "1 git-diff" in claim.derivation
    assert "9 rev-parse" in claim.derivation


def test_derive_git_diff_cardinality_failed() -> None:
    evidence = EvidenceTransactionResult(
        base_oid="a" * 40,
        subject_oid="b" * 40,
        git_commands=(_executed(), _executed()),
        ruff_result=None,
        publication_status="ready_to_publish",
        authoritative_hashes={},
    )
    claim = derive_git_diff_cardinality(evidence)
    assert claim.status == "FAILED"


def test_derive_ruff_invocation_skipped() -> None:
    evidence = EvidenceTransactionResult(
        base_oid="a" * 40,
        subject_oid="b" * 40,
        git_commands=(),
        ruff_result=None,
        publication_status="ready_to_publish",
        authoritative_hashes={},
    )
    claim = derive_ruff_invocation(evidence)
    assert claim.status == "UNMEASURED"


def test_derive_ruff_invocation_pass() -> None:
    evidence = EvidenceTransactionResult(
        base_oid="a" * 40,
        subject_oid="b" * 40,
        git_commands=(),
        ruff_result=_executed(name="ruff-check", returncode=0),
        publication_status="ready_to_publish",
        authoritative_hashes={},
    )
    claim = derive_ruff_invocation(evidence)
    assert claim.status == "PASS"


def test_derive_range_resolution_pass() -> None:
    evidence = EvidenceTransactionResult(
        base_oid="a" * 40,
        subject_oid="b" * 40,
        git_commands=(),
        ruff_result=None,
        publication_status="ready_to_publish",
        authoritative_hashes={},
    )
    claim = derive_range_resolution(evidence)
    assert claim.status == "PASS"


def test_derive_bundle_completeness_pass() -> None:
    validation = BundleValidationResult(
        declared_artifacts=("a", "b"),
        observed_artifacts=("a", "b"),
        missing_artifacts=(),
        extra_artifacts=(),
    )
    claim = derive_bundle_completeness(validation)
    assert claim.status == "PASS"


def test_derive_publication_status_ready() -> None:
    evidence = EvidenceTransactionResult(
        base_oid="a" * 40,
        subject_oid="b" * 40,
        git_commands=(),
        ruff_result=None,
        publication_status="ready_to_publish",
        authoritative_hashes={},
    )
    claim = derive_publication_status(evidence)
    assert claim.value == "READY_TO_PUBLISH"
    assert claim.status == "PASS"


def test_derive_bundle_root_hash_present() -> None:
    # CORRECTION16: the bundle-root hash is PASS only at
    # ``root_writes`` / ``published_renamed`` lifecycle
    # stages.  Pre-root is UNMEASURED.
    claim = derive_bundle_root_hash(
        {"bundle-root.json": "abc123"}, lifecycle_stage="root_writes"
    )
    assert claim.status == "PASS"
    assert claim.value == "abc123"


def test_final_classification_contains_no_literal_pass_constant() -> None:
    """The renderer MUST NOT contain literal ``PASS`` constants.

    The source guard asserts that the renderer file has no
    ``_render_pass(True)`` or ``hardcoded_unmeasured_PASS_claims = 0``
    literal constants.
    """
    import inspect

    from scripts.verifiers_audit import range_evidence_classification

    source = inspect.getsource(range_evidence_classification)
    forbidden = [
        '_render_pass(True)',
        'hardcoded_unmeasured_PASS_claims = 0',
        'post_publication_bundle_mutations = 0',
    ]
    for token in forbidden:
        assert token not in source, (
            f"classification module contains forbidden literal: {token!r}"
        )


def test_final_classification_renders_named_derivations() -> None:
    """Every row in the final-classification.md carries a
    named derivation function and a value that is derived
    (not hardcoded).
    """
    gate = RepositoryGateResult(
        name="audit-check", command=_executed(name="audit-check")
    )
    validation = BundleValidationResult(
        declared_artifacts=("a", "b"),
        observed_artifacts=("a", "b"),
        missing_artifacts=(),
        extra_artifacts=(),
    )
    evidence = EvidenceTransactionResult(
        base_oid="a" * 40,
        subject_oid="b" * 40,
        git_commands=(
            _executed(),
            _executed(name="git-rev-parse-subject"),
            _executed(name="git-diff-factory", argv=("git", "diff")),
        ),
        ruff_result=_executed(name="ruff-check"),
        publication_status="ready_to_publish",
        authoritative_hashes={"bundle-root.json": "abc"},
    )
    topo = ClosureTopology(
        F16="f16", F16_tree="f16t", plan_blob="pb",
        S16=None, S16_tree=None, parent_F16="s15", parent_S16=None,
    )
    text = build_final_classification(
        evidence=evidence,
        gate_results=(gate,),
        topology=topo,
        validation=validation,
        sha_map={"bundle-root.json": "abc"},
    )
    # The Derivation column is present and every row carries it.
    assert "| Derivation |" in text
    # The CORRECTION16 lifecycle row uses the closure-topology
    # constant (NOT a hardcoded "PASS" row).
    assert "CORRECTION16" in text
    assert "PARTIAL_CHECKPOINT" in text
    # No hardcoded constant "0" for hardcoded_unmeasured_PASS_claims
    # row should be rendered in the lifecycle table.
    for row in text.splitlines():
        if row.startswith("| hardcoded_unmeasured_PASS_claims "):
            pytest.fail(
                f"hardcoded PASS row in final-classification: {row}"
            )
