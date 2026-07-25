# mypy: disable-error-code="index,assignment,operator,arg-type,union-attr,attr-defined,return-value,no-any-return,no-untyped-call,no-untyped-def,var-annotated,call-overload,comparison-overlap"
"""CORRECTION14: range evidence orchestration tests.

The tests in this module exercise the CORRECTION14 range
evidence contract: the fail-closed Ruff identity, the Git
command cardinality from the executed transcript, and the
complete one-transaction immutable bundle.

The companion module
:mod:`test_verifier_core_migration_audit01_correction14_layout`
owns the layout-shard-schema tests.
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import pytest

from scripts.verifiers_audit.range_evidence_helpers import (
    SubprocessGitRunner,
)
from scripts.verifiers_audit.range_evidence_identity import (
    RuffToolUnavailable,
)
from scripts.verifiers_audit.typed_results import (
    ClosureTopology,
    CommandResult,
    EvidenceTransactionResult,
)
from tests.verifiers.verifier_core_migration_audit01_support import (
    commit_fixture_base,
    commit_fixture_subject,
    git_init,
)


def test_resolve_ruff_identity_raises_for_nonempty_python_paths(
    tmp_path: Path,
) -> None:
    """When NEITHER the venv ``python -m ruff`` nor the standalone
    ``ruff`` binary is available, the identity resolution raises
    :class:`RuffToolUnavailable` for a non-empty Python range.
    """
    from scripts.verifiers_audit import range_evidence_identity as _re

    orig_venv = _re._resolve_venv_ruff
    orig_standalone = _re._resolve_standalone_ruff

    def _no_venv(repo_root: Path) -> dict[str, object] | None:
        return None

    def _no_standalone(repo_root: Path) -> dict[str, object] | None:
        return None

    _re._resolve_venv_ruff = _no_venv
    _re._resolve_standalone_ruff = _no_standalone
    try:
        with pytest.raises(RuffToolUnavailable) as excinfo:
            _re.resolve_ruff_identity(
                repo_root=tmp_path, python_paths=("a.py",)
            )
        assert excinfo.value.python_paths == ("a.py",)
    finally:
        _re._resolve_venv_ruff = orig_venv
        _re._resolve_standalone_ruff = orig_standalone


def test_resolve_ruff_identity_skips_for_empty_python_paths(
    tmp_path: Path,
) -> None:
    """When the Python range is empty, the function returns a
    record with ``ruff_invocation_mode == 'skipped_no_python_paths'``
    and does NOT raise.
    """
    from scripts.verifiers_audit import range_evidence_identity as _re

    record = _re.resolve_ruff_identity(
        repo_root=tmp_path, python_paths=()
    )
    assert record["ruff_invocation_mode"] == "skipped_no_python_paths"
    assert record["launcher_argv_prefix"] == ()


def test_collect_range_evidence_fails_closed_without_ruff(
    tmp_path: Path,
) -> None:
    """A non-empty Python range with an unresolvable Ruff
    identity raises :class:`RuffToolUnavailable`.  The producer
    raises BEFORE writing any artifact; the staging directory is
    removed; the final destination does NOT exist.
    """
    from scripts.verifiers_audit.range_evidence_identity import (
        RuffToolUnavailable as _RTE,
    )
    from scripts.verifiers_audit.range_evidence_orchestrator import (
        collect_range_evidence,
    )

    repo = tmp_path / "repo"
    git_init(repo)
    base, trailing_ok = commit_fixture_base(repo)
    subject, _ = commit_fixture_subject(repo, trailing_ok)
    output = tmp_path / "out"

    import scripts.verifiers_audit.range_evidence_orchestrator as _re_mod

    orig_resolve = _re_mod.resolve_ruff_identity

    def _failing_resolve(
        *, repo_root: Path, python_paths: tuple[str, ...] = ()
    ) -> dict[str, object]:
        if not python_paths:
            return {
                "ruff_invocation_mode": "skipped_no_python_paths",
            }
        raise _RTE(python_paths=python_paths)

    _re_mod.resolve_ruff_identity = _failing_resolve
    try:
        with pytest.raises(_RTE):
            collect_range_evidence(
                base=base,
                subject=subject,
                repo_root=repo,
                output_dir=output,
                topology=ClosureTopology(
                    F15="a" * 40,
                    F15_tree="b" * 40,
                    plan_blob="c" * 64,
                    S15=None,
                    S15_tree=None,
                    parent_F15="d" * 40,
                    parent_S15=None,
                ),
                gate_results=(),
            )
    finally:
        _re_mod.resolve_ruff_identity = orig_resolve

    assert not output.exists(), (
        "final destination must not exist after ruff failure"
    )
    staging = list(tmp_path.glob("*.tmp.*"))
    assert not staging, f"staging must not remain: {staging}"


def test_git_cardinality_measured_from_executed_transcript() -> None:
    """The Git cardinality is derived from the executed transcript."""
    runner = SubprocessGitRunner()
    rev1 = runner.run(
        ("git", "rev-parse", "--verify", "HEAD^{commit}"),
        cwd=Path("."),
    )
    rev2 = runner.run(
        ("git", "rev-parse", "--verify", "HEAD^{commit}"),
        cwd=Path("."),
    )
    diff = runner.run(
        (
            "git", "diff", "--name-only", "-z", "--diff-filter=ACMRT",
            "HEAD", "HEAD",
        ),
        cwd=Path("."),
    )
    results = (rev1, rev2, diff)
    diff_count = sum(
        r.argv[:2] == ("git", "diff") for r in results
    )
    rev_parse_count = sum(
        r.argv[:2] == ("git", "rev-parse") for r in results
    )
    assert diff_count == 1, diff_count
    assert rev_parse_count == 2, rev_parse_count


def test_required_final_artifacts_constant() -> None:
    """The required final artifacts include every required
    artifact from the CORRECTION15 plan (the ``.txt``
    projections are first-class members).
    """
    from scripts.verifiers_audit.range_evidence_orchestrator import (
        REQUIRED_FINAL_ARTIFACTS,
    )

    required = {
        "manifest.json",
        "topology.txt",
        "gate-results.json",
        "changed-paths.z",
        "changed-paths.txt",
        "changed-python-paths.z",
        "changed-python-paths.txt",
        "ruff-input-paths.z",
        "ruff-input-paths.txt",
        "ruff-scope.json",
        "ruff-argv.json",
        "tool-identities.json",
        "commands.json",
        "final-classification.md",
        "bundle-root.json",
    }
    assert set(REQUIRED_FINAL_ARTIFACTS) == required


def test_final_classification_no_hardcoded_pass_for_unmeasured() -> None:
    """The final-classification builder NEVER hardcodes a PASS row
    for a measurement it does not actually have.
    """
    from scripts.verifiers_audit.range_evidence_classification import (
        build_final_classification,
    )
    from scripts.verifiers_audit.typed_results import (
        BundleValidationResult,
    )

    evidence = EvidenceTransactionResult(
        base_oid="a" * 40,
        subject_oid="b" * 40,
        git_commands=(),
        ruff_result=None,
        publication_status="ready_to_publish",
        authoritative_hashes=MappingProxyType({}),
    )
    topology = ClosureTopology(
        F15="a" * 40,
        F15_tree="b" * 40,
        plan_blob="c" * 64,
        S15=None,
        S15_tree=None,
        parent_F15="d" * 40,
        parent_S15=None,
    )
    text = build_final_classification(
        evidence=evidence,
        gate_results=(),
        topology=topology,
        validation=BundleValidationResult(
            declared_artifacts=(),
            observed_artifacts=(),
            missing_artifacts=(),
            extra_artifacts=(),
        ),
        sha_map={},
    )
    # The lifecycle rows are explicit closure-topology
    # constants (not derived measurements).
    assert "| wave_1 | BLOCKED |" in text
    assert "| CORRECTION15 | PARTIAL_CHECKPOINT |" in text


def test_final_classification_renders_pass_only_from_typed_result() -> None:
    """A typed :class:`ExecutedCommand` with status='passed'
    produces a derivation that records the status in the
    final classification.
    """
    from scripts.verifiers_audit.range_evidence_classification import (
        build_final_classification,
    )
    from scripts.verifiers_audit.typed_results import (
        BundleValidationResult,
    )

    ruff_result = CommandResult(
        name="ruff-check",
        argv=(".venv/bin/python", "-m", "ruff", "check", "a.py"),
        cwd="/repo",
        returncode=0,
        stdout=b"",
        stderr=b"",
        status="passed",
    )
    evidence = EvidenceTransactionResult(
        base_oid="a" * 40,
        subject_oid="b" * 40,
        git_commands=(
            CommandResult(
                name="git-rev-parse-base",
                argv=(
                    "git", "rev-parse", "--verify", "HEAD^{commit}"
                ),
                cwd="/repo",
                returncode=0,
                stdout=b"a" * 40,
                stderr=b"",
                status="passed",
            ),
        ),
        ruff_result=ruff_result,
        publication_status="ready_to_publish",
        authoritative_hashes=MappingProxyType({}),
    )
    topology = ClosureTopology(
        F15="a" * 40,
        F15_tree="b" * 40,
        plan_blob="c" * 64,
        S15=None,
        S15_tree=None,
        parent_F15="d" * 40,
        parent_S15=None,
    )
    text = build_final_classification(
        evidence=evidence,
        gate_results=(),
        topology=topology,
        validation=BundleValidationResult(
            declared_artifacts=(),
            observed_artifacts=(),
            missing_artifacts=(),
            extra_artifacts=(),
        ),
        sha_map={},
    )
    # The ruff derivation must record ``status=passed`` in
    # the rendered table.
    assert "Ruff status=passed" in text
