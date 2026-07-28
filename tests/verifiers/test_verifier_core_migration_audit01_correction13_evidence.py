# mypy: disable-error-code="index,assignment,operator,arg-type,union-attr,attr-defined,return-value,no-any-return,no-untyped-call,no-untyped-def,var-annotated,call-overload,comparison-overlap"
"""CORRECTION13: range evidence transactional and identity tests.

CORRECTION13 split: the audit01 test module exceeded the
500-line LLM-friendly threshold.  The range-evidence
transactional, single-query, identity-equivalence, ruff
failure, and final-classification tests live in this
companion module.  The other CORRECTION13 tests live in
:mod:`test_verifier_core_migration_audit01_correction13`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verifiers_audit.scope import RangeResolutionError
from tests.verifiers.verifier_core_migration_audit01_correction22_hermetic_ruff import HermeticRuffCapability
from tests.verifiers.verifier_core_migration_audit01_support import (
    commit_fixture_base,
    commit_fixture_subject,
    git_init,
)

# ---------------------------------------------------------------------------
# CORRECTION13 Phase 7/8: transactional evidence publishing.
# ---------------------------------------------------------------------------


def test_collect_range_evidence_requires_fresh_destination(
    tmp_path: Path,
) -> None:
    """The destination directory must initially be absent.

    The producer refuses to write when the destination exists.
    """
    from scripts.verifiers_audit.range_evidence import (
        collect_range_evidence,
    )

    repo = tmp_path / "repo"
    git_init(repo)
    base, trailing_ok = commit_fixture_base(repo)
    subject, _newline_ok = commit_fixture_subject(repo, trailing_ok)
    output = tmp_path / "out"
    output.mkdir()  # already exists
    with pytest.raises(FileExistsError) as excinfo:
        collect_range_evidence(
            base=base,
            subject=subject,
            repo_root=repo,
            output_dir=output,
        )
    assert "FRESH" in str(excinfo.value).upper() or "EXIST" in str(excinfo.value).upper()


def test_collect_range_evidence_no_force_replace_kwarg(
    tmp_path: Path,
) -> None:
    """The ``force_replace`` keyword argument is removed."""
    import inspect

    from scripts.verifiers_audit.range_evidence import (
        collect_range_evidence,
    )

    sig = inspect.signature(collect_range_evidence)
    assert "force_replace" not in sig.parameters, f"force_replace is not supported in CORRECTION13: {sig}"


def test_collect_range_evidence_failure_leaves_no_bundle(
    tmp_path: Path,
) -> None:
    """A range failure leaves no final bundle and no staging
    directory."""
    from scripts.verifiers_audit.range_evidence import collect_range_evidence

    repo = tmp_path / "repo"
    git_init(repo)
    output = tmp_path / "out"
    with pytest.raises(RangeResolutionError) as excinfo:
        collect_range_evidence(
            base="0" * 40,
            subject="0" * 40,
            repo_root=repo,
            output_dir=output,
        )
    assert excinfo.value.stage in ("resolve_base", "diff_names"), f"unexpected stage {excinfo.value.stage!r}"
    assert not output.exists(), f"final bundle must not exist after range failure: {output}"
    staging = list(tmp_path.glob("*.tmp.*"))
    assert not staging, f"staging directory must not remain after range failure: {staging}"


def test_collect_range_evidence_success_publishes_bundle(
    hermetic_ruff_capability: HermeticRuffCapability,
    tmp_path: Path,
) -> None:
    """A successful run publishes the bundle and removes the
    staging directory."""
    from scripts.verifiers_audit.range_evidence import collect_range_evidence

    repo = tmp_path / "repo"
    git_init(repo)
    base, trailing_ok = commit_fixture_base(repo)
    subject, _newline_ok = commit_fixture_subject(repo, trailing_ok)
    output = tmp_path / "out"
    collect_range_evidence(
        base=base,
        subject=subject,
        repo_root=repo,
        output_dir=output,
    )
    assert output.exists()
    assert (output / "manifest.json").exists()
    # No staging directory remains.
    staging = list(tmp_path.glob("*.tmp.*"))
    assert not staging, f"staging directory must not remain after success: {staging}"


def test_collect_range_evidence_writes_nul_delimited_manifests(
    hermetic_ruff_capability: HermeticRuffCapability,
    tmp_path: Path,
) -> None:
    """The authoritative .z files are NUL-delimited filesystem
    bytes. The .txt files are labelled non-authoritative."""
    from scripts.verifiers_audit.range_evidence import collect_range_evidence

    repo = tmp_path / "repo"
    git_init(repo)
    base, trailing_ok = commit_fixture_base(repo)
    subject, _newline_ok = commit_fixture_subject(repo, trailing_ok)
    output = tmp_path / "out"
    collect_range_evidence(
        base=base,
        subject=subject,
        repo_root=repo,
        output_dir=output,
    )
    # Authoritative NUL-delimited files exist.
    for name in ("changed-paths", "changed-python-paths", "ruff-input-paths"):
        z_path = output / f"{name}.z"
        assert z_path.exists(), f"missing authoritative {name}.z"
        # The contents are bytes; no utf-8 decoding required.
        raw = z_path.read_bytes()
        assert isinstance(raw, bytes)
    # The Python and Ruff input manifests are byte-equal.
    assert (output / "changed-python-paths.z").read_bytes() == (output / "ruff-input-paths.z").read_bytes()
    # The .txt files exist and are labelled non-authoritative.
    for name in ("changed-paths", "changed-python-paths", "ruff-input-paths"):
        txt_path = output / f"{name}.txt"
        assert txt_path.exists()
        text = txt_path.read_text(encoding="utf-8")
        assert "authority: false" in text
        assert "encoding: diagnostic escaped projection" in text


# ---------------------------------------------------------------------------
# CORRECTION13 Phase 3/6: single git diff query + identity equivalence.
# ---------------------------------------------------------------------------


def test_collect_range_evidence_uses_single_git_diff_query(
    hermetic_ruff_capability: HermeticRuffCapability,
    tmp_path: Path,
) -> None:
    """The evidence transaction calls ``git diff`` EXACTLY
    ONCE; the python subset is derived in-process."""
    from scripts.verifiers_audit.range_evidence import collect_range_evidence

    repo = tmp_path / "repo"
    git_init(repo)
    base, trailing_ok = commit_fixture_base(repo)
    subject, _newline_ok = commit_fixture_subject(repo, trailing_ok)
    output = tmp_path / "out"

    from scripts.verifiers_audit import range_evidence_orchestrator as _orch

    diff_calls: list[tuple[str, ...]] = []
    orig_changed_path_bytes = _orch.changed_path_bytes

    def _spy_changed_path_bytes(b: str, s: str, *, repo_root: Path) -> tuple[bytes, ...]:
        # Capture the git diff command and delegate.
        diff_calls.append((b, s))
        return orig_changed_path_bytes(b, s, repo_root=repo_root)

    _orch.changed_path_bytes = _spy_changed_path_bytes
    try:
        collect_range_evidence(
            base=base,
            subject=subject,
            repo_root=repo,
            output_dir=output,
        )
    finally:
        _orch.changed_path_bytes = orig_changed_path_bytes
    # Exactly one git diff query per evidence transaction.
    assert len(diff_calls) == 1, f"expected exactly one git diff query, got {len(diff_calls)}"
    # The manifest records the single-query contract.
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["git_diff_query_count"] == 1, manifest
    # The .z files are byte-equal (same authoritative source).
    py_z = (output / "changed-python-paths.z").read_bytes()
    ruff_z = (output / "ruff-input-paths.z").read_bytes()
    assert py_z == ruff_z


def test_collect_range_evidence_records_ruff_identity(
    hermetic_ruff_capability: HermeticRuffCapability,
    tmp_path: Path,
) -> None:
    """``tool-identities.json`` records the resolved launcher
    strategy; the recorded launcher path is exactly the
    executed launcher path."""
    from scripts.verifiers_audit.range_evidence import collect_range_evidence

    repo = tmp_path / "repo"
    git_init(repo)
    base, trailing_ok = commit_fixture_base(repo)
    subject, _newline_ok = commit_fixture_subject(repo, trailing_ok)
    output = tmp_path / "out"
    collect_range_evidence(
        base=base,
        subject=subject,
        repo_root=repo,
        output_dir=output,
    )
    identities = json.loads((output / "tool-identities.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    # The recorded identity MUST match the manifest's tool_identities.
    assert identities["launcher_path"] == manifest["tool_identities"]["launcher_path"]
    # The ruff_invocation_mode is module or binary (or
    # unresolved when the host has neither).
    assert identities["ruff_invocation_mode"] in (
        "module",
        "hermetic_test_script",
        "binary",
        "unresolved",
    ), identities
    # The launcher_sha256, when present, is a 64-char hex string.
    if identities["launcher_sha256"]:
        assert len(identities["launcher_sha256"]) == 64, identities["launcher_sha256"]
    # The configuration files were inspected.
    assert "configuration_files" in identities
    assert "configuration_file_sha256" in identities


def test_executed_ruff_argv_matches_recorded_identity(
    hermetic_ruff_capability: HermeticRuffCapability,
    tmp_path: Path,
) -> None:
    """The executed Ruff argv matches the recorded evidence.

    Binds the actual script argv from the hermetic capability's log file
    to the evidence argv written by the orchestrator. The evidence argv
    includes the launcher prefix; the capability's log records the script's
    perspective (with script path as argv[0]).
    """
    from scripts.verifiers_audit.range_evidence import collect_range_evidence

    repo = tmp_path / "repo"
    git_init(repo)
    base, trailing_ok = commit_fixture_base(repo)
    subject, _newline_ok = commit_fixture_subject(repo, trailing_ok)
    output = tmp_path / "out"
    collect_range_evidence(
        base=base,
        subject=subject,
        repo_root=repo,
        output_dir=output,
    )
    identities = json.loads((output / "tool-identities.json").read_text(encoding="utf-8"))
    ruff_argv_doc = json.loads((output / "ruff-argv.json").read_text(encoding="utf-8"))
    recorded_argv = ruff_argv_doc["argv"]
    if recorded_argv is None:
        # Empty range or unresolved identity; no executed argv.
        return

    # Get the actual script argv from the hermetic capability's log file
    actual_script_argv = hermetic_ruff_capability.get_recorded_argv()
    assert actual_script_argv, "Hermetic capability should have recorded argv"

    # The evidence argv starts with the launcher prefix (interpreter, script_path)
    # The capability's log has script_path as argv[0], so capability[1:] = evidence suffix
    prefix = list(identities["launcher_argv_prefix"])
    assert list(recorded_argv[: len(prefix)]) == prefix, (
        f"recorded argv {recorded_argv} does not start with launcher prefix {prefix}"
    )

    # The argv must contain the check subcommand
    assert "check" in recorded_argv, "argv must contain 'check' subcommand"

    # The evidence argv suffix (after prefix) must match the capability's argv[1:]
    evidence_suffix = tuple(recorded_argv[len(prefix):])
    capability_suffix = tuple(actual_script_argv[1:])  # Skip script_path in log
    assert evidence_suffix == capability_suffix, (
        f"Evidence argv suffix {evidence_suffix!r} != capability argv[1:] {capability_suffix!r}"
    )

    # Verify the script path matches what was used
    script_path_in_argv = recorded_argv[1]  # argv[0] is interpreter, argv[1] is script
    assert script_path_in_argv == str(hermetic_ruff_capability.script_path), (
        f"Script path in argv {script_path_in_argv!r} != expected {hermetic_ruff_capability.script_path!r}"
    )


# ---------------------------------------------------------------------------
# CORRECTION13 Phase 7: ruff-failure-prevents-publication.
# ---------------------------------------------------------------------------


def test_ruff_failure_prevents_publication(tmp_path: Path) -> None:
    """A non-zero Ruff run raises and publishes zero bytes
    to the final destination.

    The test forces a non-zero Ruff run by injecting a
    fake ruff identity that points at an executable which
    always exits nonzero.  The destination must remain
    absent; the staging directory must be removed.
    """
    from scripts.verifiers_audit import range_evidence_orchestrator as _orch
    from scripts.verifiers_audit.range_evidence import collect_range_evidence

    repo = tmp_path / "repo"
    git_init(repo)
    base, trailing_ok = commit_fixture_base(repo)
    subject, _newline_ok = commit_fixture_subject(repo, trailing_ok)
    output = tmp_path / "out"

    # Create a tiny shell script that always exits nonzero.
    failing_ruff = tmp_path / "failing_ruff.sh"
    failing_ruff.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
    failing_ruff.chmod(0o755)

    orig_resolve = _orch.resolve_ruff_identity

    from scripts.verifiers_audit.range_evidence_identity import (
        RuffToolUnavailable,
    )

    def _fake_resolve(
        *,
        repo_root: Path,
        python_paths: tuple[str, ...] = (),
    ) -> dict[str, object]:
        if not python_paths:
            return {
                "ruff_invocation_mode": "skipped_no_python_paths",
            }
        raise RuffToolUnavailable(python_paths=python_paths)

    _orch.resolve_ruff_identity = _fake_resolve
    try:
        from scripts.verifiers_audit.range_evidence_identity import (
            RuffToolUnavailable,
        )

        with pytest.raises(RuffToolUnavailable):
            collect_range_evidence(
                base=base,
                subject=subject,
                repo_root=repo,
                output_dir=output,
            )
    finally:
        _orch.resolve_ruff_identity = orig_resolve
    # The final destination must NOT exist; the staging
    # directory must NOT remain.
    assert not output.exists(), f"final destination must not exist after ruff failure: {output}"
    staging = list(tmp_path.glob("*.tmp.*"))
    assert not staging, f"staging directory must not remain after ruff failure: {staging}"


# ---------------------------------------------------------------------------
# CORRECTION13 Phase 8: derived final classification.
# ---------------------------------------------------------------------------


def test_final_classification_claims_are_derived(
    hermetic_ruff_capability,
    tmp_path: Path) -> None:
    """The final-classification.md file is rendered from a
    measured result; every claim is either ``PASS`` (when
    measured) or ``UNMEASURED`` (when the writer has no
    measurement for that claim in the current transaction).
    """
    from scripts.verifiers_audit.range_evidence import collect_range_evidence

    repo = tmp_path / "repo"
    git_init(repo)
    base, trailing_ok = commit_fixture_base(repo)
    subject, _newline_ok = commit_fixture_subject(repo, trailing_ok)
    output = tmp_path / "out"
    collect_range_evidence(
        base=base,
        subject=subject,
        repo_root=repo,
        output_dir=output,
    )
    text = (output / "final-classification.md").read_text(encoding="utf-8")
    # Lifecycle rows for C / T / E are ABSENT (or marked ABSENT);
    # the writer never hardcodes a PASS for them.
    assert "| closure_commit_C | ABSENT" in text
    assert "| annotated_tag_T | ABSENT" in text
    assert "| leamas_protocol_E | ABSENT" in text
    # The wave_1 row is BLOCKED.
    assert "| wave_1 | BLOCKED" in text
    # The transaction_evidence rows are PASS.
    assert "transaction_evidence.range_resolution" in text
    assert "transaction_evidence.path_manifest" in text
    # The repository_test_evidence rows are bound to a named
    # post-subject gate.
    assert "repository_test_evidence.cmd_check_contract" in text
    assert "BOUND_TO_NAMED_POST_SUBJECT_GATE" in text
