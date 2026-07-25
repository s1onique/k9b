"""CORRECTION16: typed dataclass and lifecycle tests.

The tests in this module validate the CORRECTION16
hardenings:

* the :func:`resolve_test_inventory` helper resolves the
  test-inventory glob in Python before argv construction;
* the :class:`RepositoryGateName` ``Literal`` is the
  closed set of semantic gate names;
* the :class:`GitCommandKind` ``Literal`` is the closed
  set of Git command classifications;
* the :class:`RepositoryTopology` dataclass records the
  transcript-derived F16 / S16 topology;
* the :class:`TransactionSummary` dataclass records the
  typed cardinality of the Git transcript;
* the :class:`RuffEquivalenceProof` dataclass records the
  explicit-vs-canonical Ruff equivalence proof.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import hashlib

import pytest

from scripts.verifiers_audit.range_evidence_classification import (
    LifecycleStage,
    build_final_classification,
    derive_act_local,
    derive_audit_check,
    derive_bundle_completeness,
    derive_bundle_root_hash,
    derive_bundle_root_validated,
    derive_diff_check,
    derive_publication_status,
    derive_ruff_equivalence,
    derive_topology_resolution,
    derive_transaction_summary,
    derive_worktree_clean,
)
from scripts.verifiers_audit.range_evidence_gates import (
    AUDIT01_TEST_GLOB_PATTERN,
    argv_has_literal_glob,
    assert_argv_has_no_literal_glob,
    build_required_gates,
    resolve_test_inventory,
)
from scripts.verifiers_audit.typed_results import (
    BundleValidationResult,
    EvidenceTransactionResult,
    ExecutedCommand,
    GitCommandKind,
    RepositoryGateResult,
    RepositoryTopology,
    RuffEquivalenceProof,
    TransactionGitCommand,
    TransactionSummary,
)


def _executed(
    *,
    name: str = "git-rev-parse-base",
    argv: tuple[str, ...] = ("git", "rev-parse", "--verify", "BASE^{commit}"),
    stdout: bytes = b"abc123\n",
    stderr: bytes = b"",
    returncode: int = 0,
    cwd: str = "/repo",
    status: str = "passed",
) -> ExecutedCommand:
    return ExecutedCommand(
        name=name,
        argv=argv,
        cwd=cwd,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        status=status,  # type: ignore[arg-type]
    )


def _gate(
    name: str,
    *,
    argv: tuple[str, ...] = ("git", "diff", "--check"),
    stdout: bytes = b"",
    status: str = "passed",
) -> RepositoryGateResult:
    return RepositoryGateResult(
        name=name,  # type: ignore[arg-type]
        command=_executed(
            name=name,
            argv=argv,
            stdout=stdout,
            status=status,
        ),
    )


def _summary(
    *,
    topology: int = 7,
    range_git: int = 3,
    gate: int = 2,
    unrecorded: int = 0,
    hidden: int = 0,
) -> TransactionSummary:
    return TransactionSummary(
        topology_git_commands=topology,
        range_git_commands=range_git,
        gate_git_commands=gate,
        total_git_commands=topology + range_git + gate,
        unrecorded_git_commands=unrecorded,
        hidden_shell_git_invocations=hidden,
    )


def _topology(
    *,
    F16: str = "f16f16f16f16f16f16f16f16f16f16f16f16f16f16",
    S16: str = "s16s16s16s16s16s16s16s16s16s16s16s16s16s16",
    parent_F16: str = "p15p15p15p15p15p15p15p15p15p15p15p15p15p15",
    parent_S16: str | None = None,
) -> RepositoryTopology:
    if parent_S16 is None:
        parent_S16 = F16
    return RepositoryTopology(
        F16=F16,
        F16_tree="f16tree0000000000000000000000000000000000",
        plan_blob="f16plan0000000000000000000000000000000000",
        S16=S16,
        S16_tree="s16tree0000000000000000000000000000000000",
        parent_F16=parent_F16,
        parent_S16=parent_S16,
        plan_path="docs/closure-plans/ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01-CORRECTION16.json",
    )


def _proof(
    *,
    explicit_rc: int = 0,
    canonical_rc: int = 0,
    equivalent: bool = True,
    ruff_version: str = "0.6.0",
) -> RuffEquivalenceProof:
    return RuffEquivalenceProof(
        explicit_returncode=explicit_rc,
        canonical_returncode=canonical_rc,
        explicit_diagnostics_sha256="digest-explicit",
        canonical_diagnostics_sha256="digest-explicit",
        ruff_version=ruff_version,
        input_path_tuple_sha256="digest-inputs",
        config_path="pyproject.toml",
        config_sha256="digest-config",
        equivalent=equivalent,
    )


def _evidence(
    *,
    base: str = "b" * 40,
    subject: str = "s" * 40,
    summary: TransactionSummary | None = None,
    topology: RepositoryTopology | None = None,
    proof: RuffEquivalenceProof | None = None,
    git_commands: tuple[ExecutedCommand, ...] = (),
    ruff_result: ExecutedCommand | None = None,
    all_gates_pass: bool = True,
) -> EvidenceTransactionResult:
    if summary is None:
        summary = _summary()
    if topology is None:
        topology = _topology()
    if proof is None:
        proof = _proof()
    return EvidenceTransactionResult(
        base_oid=base,
        subject_oid=subject,
        git_commands=git_commands,
        ruff_result=ruff_result,
        publication_status="ready_to_publish",
        authoritative_hashes={},
        transaction_summary=summary,
        repository_topology=topology,
        ruff_equivalence=proof,
        all_gates_pass=all_gates_pass,
    )


def test_audit01_test_glob_pattern_is_canonical() -> None:
    assert AUDIT01_TEST_GLOB_PATTERN == (
        "tests/verifiers/test_verifier_core_migration_audit01*.py"
    )


def test_resolve_test_inventory_returns_sorted_paths(tmp_path) -> None:
    (tmp_path / "tests" / "verifiers").mkdir(parents=True)
    a = tmp_path / "tests" / "verifiers" / "test_verifier_core_migration_audit01_a.py"
    b = tmp_path / "tests" / "verifiers" / "test_verifier_core_migration_audit01_b.py"
    c = tmp_path / "tests" / "verifiers" / "test_verifier_core_migration_audit01_c.py"
    a.write_text("# a")
    b.write_text("# b")
    c.write_text("# c")
    out = resolve_test_inventory(repo_root=tmp_path)
    assert out == (
        "tests/verifiers/test_verifier_core_migration_audit01_a.py",
        "tests/verifiers/test_verifier_core_migration_audit01_b.py",
        "tests/verifiers/test_verifier_core_migration_audit01_c.py",
    )


def test_resolve_test_inventory_skips_symlinks(tmp_path) -> None:
    (tmp_path / "tests" / "verifiers").mkdir(parents=True)
    a = tmp_path / "tests" / "verifiers" / "test_verifier_core_migration_audit01_a.py"
    a.write_text("# a")
    link = tmp_path / "tests" / "verifiers" / "test_verifier_core_migration_audit01_link.py"
    try:
        link.symlink_to(a)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported on this platform")
    out = resolve_test_inventory(repo_root=tmp_path)
    assert "tests/verifiers/test_verifier_core_migration_audit01_a.py" in out
    assert "tests/verifiers/test_verifier_core_migration_audit01_link.py" not in out


def test_argv_has_literal_glob_detects_glob_tokens() -> None:
    assert argv_has_literal_glob(
        ("tests/verifiers/test_verifier_core_migration_audit01*.py",)
    )
    assert argv_has_literal_glob(("foo?.py",))
    assert argv_has_literal_glob(("foo[abc].py",))
    assert not argv_has_literal_glob(("foo.py",))
    assert not argv_has_literal_glob(())  # type: ignore[arg-type]


def test_assert_argv_has_no_literal_glob_raises_on_glob() -> None:
    gate = _gate(
        "audit01-pytest",
        argv=(
            "python",
            "-m",
            "pytest",
            "tests/verifiers/test_verifier_core_migration_audit01*.py",
        ),
    )
    with pytest.raises(ValueError):
        assert_argv_has_no_literal_glob((gate,))


def test_assert_argv_has_no_literal_glob_accepts_clean_argv() -> None:
    gate = _gate(
        "audit01-pytest",
        argv=("python", "-m", "pytest", "tests/verifiers/test_a.py"),
    )
    assert_argv_has_no_literal_glob((gate,)) is None


def test_build_required_gates_contains_no_glob_tokens(tmp_path) -> None:
    (tmp_path / "tests" / "verifiers").mkdir(parents=True)
    (tmp_path / "tests" / "verifiers" / "test_a.py").write_text("# a")
    gates = build_required_gates(repo_root=tmp_path)
    argv_seq = [g.argv for g in gates]
    assert not any(argv_has_literal_glob(a) for a in argv_seq)


def test_build_required_gates_worktree_clean_uses_git_seam(tmp_path) -> None:
    gates = build_required_gates(repo_root=tmp_path)
    worktree = next(g for g in gates if g.name == "worktree-clean")
    assert worktree.argv[0] == "git"
    assert "status" in worktree.argv
    assert "--porcelain=v1" in worktree.argv


def test_build_required_gates_act_local_supports_base_subject(tmp_path) -> None:
    gates = build_required_gates(
        repo_root=tmp_path, base="F16", subject="S16"
    )
    act_local = next(g for g in gates if g.name == "act-local")
    assert "--base" in act_local.argv
    assert "F16" in act_local.argv
    assert "--subject" in act_local.argv
    assert "S16" in act_local.argv


def test_derive_act_local_reports_unmeasured_when_gate_absent() -> None:
    claim = derive_act_local(())
    assert claim.value == "UNMEASURED"
    assert claim.status == "UNMEASURED"


def test_derive_act_local_reports_pass_when_passed() -> None:
    claim = derive_act_local((_gate("act-local"),))
    assert claim.value == "PASS"
    assert claim.status == "PASS"


def test_derive_worktree_clean_reports_failed_on_non_empty_stdout() -> None:
    # The ``run_required_gates`` helper overrides the
    # status to ``failed`` when stdout is non-empty.  The
    # test simulates the post-override state directly.
    claim = derive_worktree_clean(
        (
            _gate(
                "worktree-clean",
                stdout=b" M foo.py",
                status="failed",
            ),
        )
    )
    assert claim.value == "FAILED"
    assert claim.status == "FAILED"


def test_derive_worktree_clean_reports_pass_on_empty_stdout() -> None:
    claim = derive_worktree_clean(
        (_gate("worktree-clean", stdout=b"", status="passed"),)
    )
    assert claim.value == "PASS"


def test_derive_transaction_summary_reports_pass_when_complete() -> None:
    claim = derive_transaction_summary(_evidence(summary=_summary()))
    assert claim.value == "PASS"


def test_derive_transaction_summary_reports_failed_when_unrecorded() -> None:
    claim = derive_transaction_summary(
        _evidence(summary=_summary(unrecorded=1))
    )
    assert claim.value == "FAILED"


def test_derive_ruff_equivalence_reports_pass_when_equivalent() -> None:
    claim = derive_ruff_equivalence(_evidence(proof=_proof(equivalent=True)))
    assert claim.value == "PASS"


def test_derive_ruff_equivalence_reports_failed_when_inequivalent() -> None:
    claim = derive_ruff_equivalence(
        _evidence(proof=_proof(equivalent=False))
    )
    assert claim.value == "FAILED"


def test_derive_topology_resolution_reports_pass_when_consistent() -> None:
    claim = derive_topology_resolution(_evidence())
    assert claim.value == "PASS"


def test_derive_topology_resolution_reports_failed_when_inconsistent() -> None:
    topology = _topology(parent_S16="not_equal")
    claim = derive_topology_resolution(_evidence(topology=topology))
    assert claim.value == "FAILED"


def test_derive_publication_status_pre_root_is_ready() -> None:
    claim = derive_publication_status(
        _evidence(), lifecycle_stage="pre_root_writes"
    )
    assert claim.value == "READY_TO_PUBLISH"


def test_derive_publication_status_published_renamed_is_published() -> None:
    claim = derive_publication_status(
        _evidence(), lifecycle_stage="published_renamed"
    )
    assert claim.value == "PUBLISHED"


def test_derive_bundle_root_hash_pre_root_is_unmeasured() -> None:
    claim = derive_bundle_root_hash(
        {}, lifecycle_stage="pre_root_writes"
    )
    assert claim.value == "UNMEASURED"


def test_derive_bundle_root_hash_root_writes_is_pass() -> None:
    digest = hashlib.sha256(b"x").hexdigest()
    claim = derive_bundle_root_hash(
        {"bundle-root.json": digest}, lifecycle_stage="root_writes"
    )
    assert claim.value == digest
    assert claim.status == "PASS"


def test_derive_bundle_root_validated_pre_root_is_pending() -> None:
    claim = derive_bundle_root_validated(
        {}, lifecycle_stage="pre_root_writes"
    )
    assert claim.value == "PENDING_EXTERNAL_RESULT"
    assert claim.status == "PENDING_EXTERNAL_RESULT"


def test_derive_bundle_root_validated_published_renamed_is_pass() -> None:
    digest = hashlib.sha256(b"x").hexdigest()
    claim = derive_bundle_root_validated(
        {"bundle-root.json": digest}, lifecycle_stage="published_renamed"
    )
    assert claim.value == "PASS"


def test_derive_diff_check_reports_pass_when_passed() -> None:
    claim = derive_diff_check((_gate("diff-check"),))
    assert claim.value == "PASS"


def test_derive_audit_check_reports_pass_when_passed() -> None:
    claim = derive_audit_check((_gate("audit-check"),))
    assert claim.value == "PASS"


def test_derive_bundle_completeness_reports_pass_when_valid() -> None:
    validation = BundleValidationResult(
        declared_artifacts=("a",),
        observed_artifacts=("a",),
        missing_artifacts=(),
        extra_artifacts=(),
        rejected_entries=(),
    )
    claim = derive_bundle_completeness(validation)
    assert claim.value == "PASS"


def test_build_final_classification_renders_lifecycle_stage_marker() -> None:
    text = build_final_classification(
        evidence=_evidence(),
        lifecycle_stage="pre_root_writes",
    )
    assert "## Lifecycle stage: pre_root_writes" in text


def test_build_final_classification_includes_topology_summary() -> None:
    text = build_final_classification(
        evidence=_evidence(),
        lifecycle_stage="root_writes",
    )
    assert "topology_git_commands" in text
    assert "range_git_commands" in text
    assert "gate_git_commands" in text


def test_build_final_classification_includes_ruff_equivalence() -> None:
    text = build_final_classification(
        evidence=_evidence(),
        lifecycle_stage="root_writes",
    )
    assert "explicit_diagnostics_sha256" in text
    assert "canonical_diagnostics_sha256" in text


def test_evidence_transaction_result_requires_new_fields() -> None:
    evidence = _evidence()
    assert hasattr(evidence, "transaction_summary")
    assert hasattr(evidence, "repository_topology")
    assert hasattr(evidence, "ruff_equivalence")
    assert hasattr(evidence, "all_gates_pass")


def test_repository_topology_is_frozen() -> None:
    topology = _topology()
    with pytest.raises(Exception):
        topology.F16 = "x"  # type: ignore[misc]


def test_transaction_summary_is_frozen() -> None:
    summary = _summary()
    with pytest.raises(Exception):
        summary.topology_git_commands = 999  # type: ignore[misc]


def test_ruff_equivalence_proof_is_frozen() -> None:
    proof = _proof()
    with pytest.raises(Exception):
        proof.equivalent = False  # type: ignore[misc]


def test_git_command_kind_is_literal() -> None:
    import typing

    args = typing.get_args(GitCommandKind)
    assert "topology" in args
    assert "range" in args
    assert "gate" in args
    assert "other" in args


def test_transaction_git_command_is_frozen() -> None:
    record = TransactionGitCommand(
        command=_executed(), kind="topology"
    )
    with pytest.raises(Exception):
        record.kind = "range"  # type: ignore[misc]


def test_lifecycle_stage_is_literal() -> None:
    import typing

    args = typing.get_args(LifecycleStage)
    assert "pre_root_writes" in args
    assert "root_writes" in args
    assert "published_renamed" in args
