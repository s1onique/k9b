"""CORRECTION14/CORRECTION15: detached range evidence orchestrator.

The orchestrator is the canonical producer of the detached
evidence bundle.  It is invoked by :mod:`range_evidence`
(the CLI / library entry point).  The orchestrator:

1. asserts the output directory is initially absent;
2. resolves the full commit object IDs for ``base`` and
   ``subject`` through the injected :class:`GitRunner` (the
   SOLE production seam for Git); the OID is derived from
   the captured ``stdout`` bytes (CORRECTION15);
3. resolves the diff path tuple through the same
   :class:`GitRunner` (a single ``git diff --name-only -z
   --diff-filter=ACMRT`` call); pathnames are derived from
   the captured ``stdout`` bytes;
4. derives the Python subset in-process via
   :func:`python_path_bytes` (no extra Git call);
5. resolves the Ruff identity via
   :func:`resolve_ruff_identity` (which raises
   :class:`RuffToolUnavailable` on failure);
6. builds the executed Ruff argv from the same identity;
7. executes the seven required repository gates via
   :func:`run_required_gates` BEFORE bundle construction;
8. writes the complete bundle in ONE staging transaction;
9. atomically renames the staging directory to the final
   destination after every required artifact is present and
   validated.

CORRECTION15 guarantees:

* exactly THREE Git invocations through the seam (one
  ``rev-parse BASE``, one ``rev-parse SUBJECT``, one
  ``git diff``);
* every production Git command's raw ``stdout`` /
  ``stderr`` bytes are preserved;
* the bundle root is built from the actual directory
  enumeration result (no extras, no symlinks, no special
  files, no temp paths);
* the in-bundle publication claim is
  ``READY_TO_PUBLISH``; the post-rename publication result
  is recorded in a separate transcript outside the bundle.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import os
import shutil
from pathlib import Path
from types import MappingProxyType

from scripts.verifiers_audit.range_evidence_builders import (
    build_manifest_from_evidence,
    build_topology,
)
from scripts.verifiers_audit.range_evidence_bundle import (
    DECLARED_FINAL_ARTIFACTS,
    assert_no_temporary_absolute_paths,
    build_bundle_root,
    enumerate_bundle,
    write_bundle_root,
)
from scripts.verifiers_audit.range_evidence_classification import (
    build_final_classification,
)
from scripts.verifiers_audit.range_evidence_gates import (
    run_required_gates,
)
from scripts.verifiers_audit.range_evidence_helpers import (
    GitRunner,
    SubprocessGitRunner,
    _sha256_of,
    _write_nul,
    _write_text_projection,
    parse_nul_paths,
)
from scripts.verifiers_audit.range_evidence_identity import (
    build_ruff_argv_from_identity,
    resolve_ruff_identity,
)
from scripts.verifiers_audit.range_evidence_writer import (
    build_commands_registry,
    write_commands_file,
    write_gate_results_file,
    write_manifest_file,
    write_ruff_argv_file,
    write_ruff_scope_file,
    write_tool_identities_file,
    write_topology_file,
)
from scripts.verifiers_audit.scope import (
    RangeResolutionError,
    python_path_bytes,
)
from scripts.verifiers_audit.typed_results import (
    BundleValidationResult,
    ClosureTopology,
    EvidenceTransactionResult,
    ExecutedCommand,
    RepositoryGateResult,
)

REQUIRED_FINAL_ARTIFACTS: tuple[str, ...] = DECLARED_FINAL_ARTIFACTS
"""Re-exported for backwards compatibility with the C13/C14
test suite that imports ``REQUIRED_FINAL_ARTIFACTS`` from this
module."""


def _execute_ruff(
    argv: tuple[str, ...],
    *,
    cwd: Path,
) -> ExecutedCommand:
    """Execute the Ruff argv and return a typed :class:`ExecutedCommand`."""
    runner = SubprocessGitRunner()
    return runner.run(argv, cwd=cwd, name="ruff-check")


def _validate_bundle(staging: Path) -> BundleValidationResult:
    """Validate that the staging directory enumerates correctly.

    The function delegates to
    :func:`range_evidence_bundle.enumerate_bundle` and
    raises :class:`ValueError` when the result is not valid.
    """
    validation = enumerate_bundle(staging)
    if not validation.is_valid:
        raise ValueError(
            f"bundle staging is not valid: missing="
            f"{list(validation.missing_artifacts)} extra="
            f"{list(validation.extra_artifacts)} rejected="
            f"{list(validation.rejected_entries)}"
        )
    return validation


def _hash_set(
    paths: tuple[Path, ...],
) -> dict[str, str]:
    """Compute SHA-256 of every path in ``paths`` (relpath key)."""
    out: dict[str, str] = {}
    for path in paths:
        rel = path.name
        out[rel] = _sha256_of(path)
    return out


def collect_range_evidence(
    *,
    base: str,
    subject: str,
    repo_root: Path,
    output_dir: Path,
    topology: ClosureTopology | None = None,
    gate_results: tuple[RepositoryGateResult, ...] | None = None,
    git_runner: GitRunner | None = None,
) -> EvidenceTransactionResult:
    """Produce the detached evidence bundle for ``base..subject``.

    The orchestrator executes the three authoritative Git
    commands through ``git_runner`` (defaults to
    :class:`SubprocessGitRunner`) and derives the OIDs and
    pathnames from the captured raw bytes.  The seven
    required gates are executed via
    :func:`run_required_gates` BEFORE bundle construction
    and the typed records are written into
    ``gate-results.json``.

    ``topology`` is optional for backward compatibility
    with the C13/C14 test suite; when omitted, a placeholder
    record is used.  Production callers SHOULD supply a
    real :class:`ClosureTopology` derived from the live
    closure commit.

    ``gate_results`` is optional; when omitted, the seven
    required gates are executed by the orchestrator.  Tests
    that need a pre-computed gate set supply the records
    directly.
    """
    if topology is None:
        topology = ClosureTopology(
            F15="",
            F15_tree="",
            plan_blob="",
            S15=None,
            S15_tree=None,
            parent_F15="",
            parent_S15=None,
        )
    if output_dir.exists():
        raise FileExistsError(
            f"FRESH_DESTINATION_REQUIRED: {output_dir} already exists; "
            f"--force-replace is not supported in CORRECTION15"
        )
    if git_runner is None:
        git_runner = SubprocessGitRunner()

    git_commands: list[ExecutedCommand] = []

    # 1. git rev-parse --verify BASE^{commit}
    base_rev_argv: tuple[str, ...] = (
        "git", "rev-parse", "--verify", f"{base}^{{commit}}"
    )
    base_rev = git_runner.run(base_rev_argv, cwd=repo_root, name="git-rev-parse-base")
    git_commands.append(base_rev)
    if base_rev.status == "failed":
        raise RangeResolutionError(
            base=base,
            subject=subject,
            argv=base_rev.argv,
            returncode=base_rev.returncode,
            stderr=os.fsdecode(base_rev.stderr) if base_rev.stderr else "",
            stage="resolve_base",
        )
    base_full_oid = os.fsdecode(base_rev.stdout).strip()

    # 2. git rev-parse --verify SUBJECT^{commit}
    subject_rev_argv: tuple[str, ...] = (
        "git", "rev-parse", "--verify", f"{subject}^{{commit}}"
    )
    subject_rev = git_runner.run(
        subject_rev_argv, cwd=repo_root, name="git-rev-parse-subject"
    )
    git_commands.append(subject_rev)
    if subject_rev.status == "failed":
        raise RangeResolutionError(
            base=base,
            subject=subject,
            argv=subject_rev.argv,
            returncode=subject_rev.returncode,
            stderr=os.fsdecode(subject_rev.stderr) if subject_rev.stderr else "",
            stage="resolve_subject",
        )
    subject_full_oid = os.fsdecode(subject_rev.stdout).strip()

    # 3. git diff --name-only -z --diff-filter=ACMRT
    diff_argv: tuple[str, ...] = (
        "git",
        "diff",
        "--name-only",
        "-z",
        "--diff-filter=ACMRT",
        base_full_oid,
        subject_full_oid,
    )
    diff_result = git_runner.run(diff_argv, cwd=repo_root, name="git-diff-factory")
    git_commands.append(diff_result)
    if diff_result.status == "failed":
        raise RangeResolutionError(
            base=base,
            subject=subject,
            argv=diff_argv,
            returncode=diff_result.returncode,
            stderr=os.fsdecode(diff_result.stderr) if diff_result.stderr else "",
            stage="diff_names",
        )
    all_paths_bytes = parse_nul_paths(diff_result.stdout)
    py_paths_bytes = python_path_bytes(all_paths_bytes)
    py_paths_str = tuple(os.fsdecode(p) for p in py_paths_bytes)

    ruff_identity = resolve_ruff_identity(
        repo_root=repo_root, python_paths=py_paths_str
    )
    executed_argv = build_ruff_argv_from_identity(ruff_identity, py_paths_str)
    ruff_invocation_mode = str(ruff_identity.get("ruff_invocation_mode", ""))
    skip_ruff = (
        ruff_invocation_mode == "skipped_no_python_paths" or not executed_argv
    )

    # CORRECTION15: execute the seven required gates BEFORE
    # bundle construction.  ``gate_results`` is the typed
    # record set the bundle writer consumes.
    if gate_results is None:
        gate_results = run_required_gates(
            repo_root=repo_root,
            git_runner=(
                git_runner if isinstance(git_runner, SubprocessGitRunner)
                else SubprocessGitRunner()
            ),
            subject_python_paths=py_paths_str,
        )

    staging = output_dir.parent / (
        f"{output_dir.name}.tmp.{os.getpid()}"
    )
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    git_diff_query_count = sum(
        1 for cmd in git_commands if cmd.argv[:2] == ("git", "diff")
    )
    authoritative_hashes: dict[str, str] = {}
    try:
        changed_paths_z = staging / "changed-paths.z"
        changed_python_paths_z = staging / "changed-python-paths.z"
        ruff_input_paths_z = staging / "ruff-input-paths.z"
        _write_nul(changed_paths_z, all_paths_bytes)
        _write_nul(changed_python_paths_z, py_paths_bytes)
        _write_nul(ruff_input_paths_z, py_paths_bytes)
        authoritative_hashes["changed-paths.z"] = _sha256_of(changed_paths_z)
        authoritative_hashes["changed-python-paths.z"] = _sha256_of(
            changed_python_paths_z
        )
        authoritative_hashes["ruff-input-paths.z"] = _sha256_of(
            ruff_input_paths_z
        )

        changed_paths_txt = staging / "changed-paths.txt"
        changed_python_paths_txt = staging / "changed-python-paths.txt"
        ruff_input_paths_txt = staging / "ruff-input-paths.txt"
        _write_text_projection(changed_paths_txt, all_paths_bytes)
        _write_text_projection(changed_python_paths_txt, py_paths_bytes)
        _write_text_projection(ruff_input_paths_txt, py_paths_bytes)
        authoritative_hashes["changed-paths.txt"] = _sha256_of(changed_paths_txt)
        authoritative_hashes["changed-python-paths.txt"] = _sha256_of(
            changed_python_paths_txt
        )
        authoritative_hashes["ruff-input-paths.txt"] = _sha256_of(
            ruff_input_paths_txt
        )

        if skip_ruff:
            ruff_result: ExecutedCommand | None = ExecutedCommand(
                name="ruff-check",
                argv=(),
                cwd=str(repo_root),
                returncode=0,
                stdout=b"",
                stderr=b"",
                status="skipped",
            )
        else:
            ruff_result = _execute_ruff(
                executed_argv, cwd=repo_root
            )
            if ruff_result.status == "failed":
                raise RuntimeError(
                    f"ruff_check failed: returncode={ruff_result.returncode}"
                )

        ruff_scope_status = (
            "skipped_no_python_paths"
            if ruff_invocation_mode == "skipped_no_python_paths"
            else "ready"
        )

        ruff_scope_path = write_ruff_scope_file(
            staging,
            py_paths_str,
            executed_argv,
            ruff_scope_status,
        )
        ruff_argv_path = write_ruff_argv_file(staging, executed_argv)
        tool_identities_path = write_tool_identities_file(
            staging, ruff_identity
        )
        authoritative_hashes["ruff-scope.json"] = _sha256_of(ruff_scope_path)
        authoritative_hashes["ruff-argv.json"] = _sha256_of(ruff_argv_path)
        authoritative_hashes["tool-identities.json"] = _sha256_of(
            tool_identities_path
        )

        commands = build_commands_registry(
            base=base,
            subject=subject,
            base_full_oid=base_full_oid,
            subject_full_oid=subject_full_oid,
            git_commands=tuple(git_commands),
            ruff_result=ruff_result,
            repo_root=repo_root,
        )
        commands_path = write_commands_file(staging, commands)
        authoritative_hashes["commands.json"] = _sha256_of(commands_path)

        topology_text = build_topology(
            topology=topology,
            base_full_oid=base_full_oid,
            subject_full_oid=subject_full_oid,
            git_diff_query_count=git_diff_query_count,
            rescue_branches=(
                "rescue/audit01-correction14-f14",
                "rescue/audit01-correction14-s14",
            ),
        )
        topology_path = write_topology_file(staging, topology_text)
        authoritative_hashes["topology.txt"] = _sha256_of(topology_path)

        gate_path = write_gate_results_file(staging, gate_results)
        authoritative_hashes["gate-results.json"] = _sha256_of(gate_path)

        evidence = EvidenceTransactionResult(
            base_oid=base_full_oid,
            subject_oid=subject_full_oid,
            git_commands=tuple(git_commands),
            ruff_result=ruff_result,
            publication_status="ready_to_publish",
            authoritative_hashes=MappingProxyType(authoritative_hashes),
        )
        manifest = build_manifest_from_evidence(
            evidence=evidence,
            base=base,
            subject=subject,
            repo_root=repo_root,
            all_paths_bytes=all_paths_bytes,
            py_paths_bytes=py_paths_bytes,
            ruff_scope_status=ruff_scope_status,
            ruff_identity=ruff_identity,
            git_diff_query_count=git_diff_query_count,
            changed_paths_z=changed_paths_z,
            changed_paths_txt=changed_paths_txt,
            changed_python_paths_z=changed_python_paths_z,
            changed_python_paths_txt=changed_python_paths_txt,
            ruff_input_paths_z=ruff_input_paths_z,
            ruff_input_paths_txt=ruff_input_paths_txt,
            ruff_scope_path=ruff_scope_path,
            ruff_argv_path=ruff_argv_path,
            tool_identities_path=tool_identities_path,
            commands_path=commands_path,
            topology_path=topology_path,
            gate_path=gate_path,
        )
        manifest_path = write_manifest_file(staging, manifest)
        authoritative_hashes["manifest.json"] = _sha256_of(manifest_path)

        validation = enumerate_bundle(staging)
        classification_text = build_final_classification(
            evidence=evidence,
            gate_results=gate_results,
            topology=topology,
            validation=validation,
            sha_map=authoritative_hashes,
        )
        classification_path = staging / "final-classification.md"
        classification_path.write_text(classification_text, encoding="utf-8")
        authoritative_hashes["final-classification.md"] = _sha256_of(
            classification_path
        )

        bundle_root = build_bundle_root(
            topology=topology,
            staging=staging,
            authoritative_hashes=authoritative_hashes,
        )
        assert_no_temporary_absolute_paths(bundle_root)
        bundle_root_path = write_bundle_root(staging, bundle_root)
        authoritative_hashes["bundle-root.json"] = _sha256_of(bundle_root_path)

        _validate_bundle(staging)

        staging.rename(output_dir)

        return EvidenceTransactionResult(
            base_oid=base_full_oid,
            subject_oid=subject_full_oid,
            git_commands=tuple(git_commands),
            ruff_result=ruff_result,
            publication_status="ready_to_publish",
            authoritative_hashes=MappingProxyType(authoritative_hashes),
        )
    except BaseException:
        try:
            shutil.rmtree(staging)
        except OSError:
            pass
        raise


__all__ = [
    "REQUIRED_FINAL_ARTIFACTS",
    "collect_range_evidence",
]
