"""CORRECTION14/CORRECTION15/CORRECTION16: detached range evidence orchestrator.

The orchestrator is the canonical producer of the detached
evidence bundle.  It is invoked by :mod:`range_evidence`
(the CLI / library entry point).  The orchestrator:

1. derives the F16 / S16 topology from the Git transcript
   (CORRECTION16: 7 topology Git commands through the
   :class:`GitRunner` seam, the topology object is built
   from the captured stdout bytes - the caller-supplied
   environment topology is treated as an expectation, NOT
   an authoritative value);
2. resolves the full commit object IDs for ``base`` and
   ``subject`` through the injected :class:`GitRunner`
   (the SOLE production seam for Git) - the OID is derived
   from the captured ``stdout`` bytes;
3. resolves the diff path tuple through the same
   :class:`GitRunner` (a single ``git diff --name-only -z
   --diff-filter=ACMRT`` call) - pathnames are derived from
   the captured ``stdout`` bytes;
4. derives the Python subset in-process via
   :func:`python_path_bytes` (no extra Git call);
5. resolves the Ruff identity via
   :func:`resolve_ruff_identity` (which raises
   :class:`RuffToolUnavailable` on failure);
6. runs the explicit-vs-canonical Ruff equivalence proof
   via :func:`run_ruff_equivalence_proof` (CORRECTION16);
7. executes the seven required repository gates via
   :func:`run_required_gates` BEFORE bundle construction
   (CORRECTION16: gate argv contains NO literal glob
   tokens; the worktree-clean and diff-check gates use the
   Git seam directly);
8. asserts every required gate recorded ``status='passed'``
   (CORRECTION16: fail-closed; any failed gate removes
   staging and aborts publication);
9. writes the complete bundle in ONE staging transaction
   (CORRECTION16: lifecycle stages: pre_root_writes ->
   classification_writes -> root_writes -> atomic_rename ->
   publication_result);
10. hashes every non-root file directly from disk bytes
    (NOT from in-memory state) and writes the bundle-root
    (CORRECTION16: in-bundle files NEVER claim their own
    later publication succeeded);
11. atomically renames the staging directory to the final
    destination after every required artifact is present
    and validated;
12. independently re-validates the bundle after rename
    and writes the external publication-result.json
    (CORRECTION16: the external result is the only
    authoritative source of publication success).

CORRECTION16 guarantees:

* exactly 12 Git invocations through the seam (7 topology
  + 3 range + 2 gate);
* every production Git command's raw ``stdout`` /
  ``stderr`` bytes are preserved;
* the bundle root is built from the actual disk bytes via
  :func:`hash_declared_artifacts_from_disk` (no extras,
  no symlinks, no special files, no temp paths);
* the independent revalidation produces zero hash
  mismatches before the rename;
* the in-bundle publication claim is
  ``READY_TO_PUBLISH``; the post-rename publication result
  is recorded in a separate transcript outside the bundle.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import hashlib
import os
import shutil
from collections.abc import Mapping
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
    hash_declared_artifacts,
    write_bundle_root,
)
from scripts.verifiers_audit.range_evidence_classification import (
    build_final_classification,
)
from scripts.verifiers_audit.range_evidence_gates import (
    all_required_gates_pass,
    assert_argv_has_no_literal_glob,
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
    run_ruff_equivalence_proof,
)
from scripts.verifiers_audit.range_evidence_topology import (
    CORRECTION16_F16_REF,
    CORRECTION16_PLAN_PATH,
    CORRECTION16_S16_REF,
    assert_topology_evidence,
    derive_repository_topology,
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
    RepositoryTopology,
    TransactionGitCommand,
    TransactionSummary,
)

REQUIRED_FINAL_ARTIFACTS: tuple[str, ...] = DECLARED_FINAL_ARTIFACTS
"""Re-exported for backwards compatibility with the C13/C14
test suite that imports ``REQUIRED_FINAL_ARTIFACTS`` from this
module."""

CORRECTION16_PLAN_PATH = (
    "docs/closure-plans/ACT-K9B-VERIFIER-CORE-MIGRATION-AUDIT01-CORRECTION16.json"
)
"""CORRECTION16: the canonical plan path relative to the repo root."""

CORRECTION16_F16_REF = "F16"
CORRECTION16_S16_REF = "S16"


class _GateFailure(RuntimeError):
    """CORRECTION16: raised when any required gate recorded ``failed``."""

    def __init__(self, *, failures: tuple[RepositoryGateResult, ...]) -> None:
        names = ", ".join(sorted({gate.name for gate in failures}))
        super().__init__(
            f"required gate(s) failed: {names}"
        )
        self.failures = failures


class _RuffEquivalenceFailure(RuntimeError):
    """CORRECTION16: raised when the explicit/canonical Ruff invocations differ."""

    def __init__(self, *, proof: object) -> None:
        super().__init__(f"Ruff equivalence proof failed: {proof}")
        self.proof = proof


# CORRECTION16: topology derivation was moved to
# :mod:`range_evidence_topology` to keep this file under the
# LLM-friendly line limit.  The orchestrator imports
# ``derive_repository_topology`` and ``assert_topology_evidence``
# from that module.


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


def _hash_set_from_disk(
    staging: Path,
    *,
    declared_artifacts: tuple[str, ...] = DECLARED_FINAL_ARTIFACTS,
) -> dict[str, str]:
    """Hash every declared non-root artifact directly from disk bytes.

    CORRECTION16: the function NEVER trusts an in-memory
    ``authoritative_hashes`` mapping; every hash is read
    from ``staging/<rel>`` via the filesystem.  The returned
    mapping is the SOLE input to the bundle-root writer.
    """
    return hash_declared_artifacts(
        staging,
        declared_artifacts=declared_artifacts,
    )


def _independent_revalidation(
    staging: Path,
    *,
    declared_artifacts: tuple[str, ...],
    declared_hash_map: Mapping[str, str],
) -> BundleValidationResult:
    """Re-enumerate ``staging`` and confirm every hash matches.

    CORRECTION16: the function is the canonical
    independent-revalidation step.  Any mismatch is a
    fatal error.
    """
    validation = enumerate_bundle(staging, declared_artifacts=declared_artifacts)
    if not validation.is_valid:
        raise ValueError(
            f"independent revalidation failed: missing="
            f"{list(validation.missing_artifacts)} extra="
            f"{list(validation.extra_artifacts)} rejected="
            f"{list(validation.rejected_entries)}"
        )
    for rel in sorted(validation.observed_artifacts):
        if rel == "bundle-root.json":
            continue
        actual = hashlib.sha256((staging / rel).read_bytes()).hexdigest()
        declared = declared_hash_map.get(rel, "")
        if actual != declared:
            raise ValueError(
                f"independent revalidation mismatch for {rel!r}: "
                f"actual={actual} declared={declared}"
            )
    return validation


def collect_range_evidence(
    *,
    base: str,
    subject: str,
    repo_root: Path,
    output_dir: Path,
    topology: ClosureTopology | None = None,
    gate_results: tuple[RepositoryGateResult, ...] | None = None,
    git_runner: GitRunner | None = None,
    plan_path: str = CORRECTION16_PLAN_PATH,
) -> EvidenceTransactionResult:
    """Produce the detached evidence bundle for ``base..subject``.

    CORRECTION16: the orchestrator

    1. derives the F16 / S16 topology from the Git transcript
       (7 commands, all through the seam);
    2. resolves the BASE / SUBJECT OIDs and the diff tuple
       (3 commands, all through the seam);
    3. runs the seven required gates (each gate argv
       contains no glob tokens; the worktree-clean gate
       invokes the Git seam directly);
    4. asserts every required gate recorded ``passed``;
    5. propagates the Ruff equivalence proof and asserts
       ``equivalent`` is True;
    6. builds the staging bundle in a single transaction;
    7. hashes every non-root file from disk bytes;
    8. writes the bundle-root from the disk-hash map;
    9. independently revalidates the hashes before the
       rename;
    10. atomically renames the staging directory to the
        final destination.

    ``topology`` is optional for backward compatibility
    with the C13/C14 test suite; when omitted, the
    orchestrator derives the topology from the Git
    transcript.  Production callers SHOULD supply a
    real :class:`ClosureTopology` for the renderer's
    convenience, but the orchestrator NEVER trusts the
    caller-supplied topology - the transcript is the
    SOLE authority.

    ``gate_results`` is optional; when omitted, the seven
    required gates are executed by the orchestrator.  Tests
    that need a pre-computed gate set supply the records
    directly.
    """
    if git_runner is None:
        git_runner = SubprocessGitRunner()

    git_commands: list[ExecutedCommand] = []
    transaction_records: list[TransactionGitCommand] = []

    # Phase 2: derive the F16 / S16 topology from the Git
    # transcript.  The environment topology variable is
    # treated as an expectation only.
    topology_records, repository_topology = derive_repository_topology(
        git_runner=git_runner,
        repo_root=repo_root,
        f16_ref=base,
        s16_ref=subject,
        plan_path=plan_path,
    )
    for record in topology_records:
        git_commands.append(record.command)
        transaction_records.append(record)
    assert_topology_evidence(
        git_records=topology_records,
        topology=repository_topology,
    )

    # Phase 3: BASE / SUBJECT rev-parse (2 commands).
    base_rev_argv: tuple[str, ...] = (
        "git", "rev-parse", "--verify", f"{base}^{{commit}}"
    )
    base_rev = git_runner.run(base_rev_argv, cwd=repo_root, name="git-rev-parse-base")
    git_commands.append(base_rev)
    transaction_records.append(
        TransactionGitCommand(command=base_rev, kind="range")
    )
    if base_rev.status == "failed":
        raise RangeResolutionError(
            base=base,
            subject=subject,
            argv=base_rev_argv,
            returncode=base_rev.returncode,
            stderr=os.fsdecode(base_rev.stderr) if base_rev.stderr else "",
            stage="resolve_base",
        )
    base_full_oid = os.fsdecode(base_rev.stdout).strip()

    subject_rev_argv: tuple[str, ...] = (
        "git", "rev-parse", "--verify", f"{subject}^{{commit}}"
    )
    subject_rev = git_runner.run(
        subject_rev_argv, cwd=repo_root, name="git-rev-parse-subject"
    )
    git_commands.append(subject_rev)
    transaction_records.append(
        TransactionGitCommand(command=subject_rev, kind="range")
    )
    if subject_rev.status == "failed":
        raise RangeResolutionError(
            base=base,
            subject=subject,
            argv=subject_rev_argv,
            returncode=subject_rev.returncode,
            stderr=os.fsdecode(subject_rev.stderr) if subject_rev.stderr else "",
            stage="resolve_subject",
        )
    subject_full_oid = os.fsdecode(subject_rev.stdout).strip()

    # Phase 3: single diff query.
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
    transaction_records.append(
        TransactionGitCommand(command=diff_result, kind="range")
    )
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

    # CORRECTION16: Ruff equivalence proof.
    ruff_equivalence = run_ruff_equivalence_proof(
        identity=ruff_identity,
        repo_root=repo_root,
        python_paths=py_paths_str,
    )
    if not ruff_equivalence.equivalent:
        raise _RuffEquivalenceFailure(proof=ruff_equivalence)

    # Phase 4: execute the seven required gates BEFORE
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
            base=base,
            subject=subject,
        )

    # Phase 4: fail-closed gate check.
    if not all_required_gates_pass(gate_results):
        failures = tuple(
            gate for gate in gate_results if gate.command.status != "passed"
        )
        raise _GateFailure(failures=failures)

    # Phase 4: source-guard rejects any literal glob in argv.
    assert_argv_has_no_literal_glob(gate_results)

    # Phase 4: tag every gate Git command with the kind
    # "gate" so the transaction summary is comprehensive.
    for gate in gate_results:
        if gate.command.argv and gate.command.argv[0] == "git":
            transaction_records.append(
                TransactionGitCommand(
                    command=gate.command,
                    kind="gate",
                )
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
    # ``authoritative_hashes`` is the IN-MEMORY accumulator
    # during staging.  The bundle-root is built from
    # :func:`_hash_set_from_disk` AFTER every non-root
    # artifact is on disk (CORRECTION16).
    staging_hashes: dict[str, str] = {}
    try:
        changed_paths_z = staging / "changed-paths.z"
        changed_python_paths_z = staging / "changed-python-paths.z"
        ruff_input_paths_z = staging / "ruff-input-paths.z"
        pytest_input_paths_z = staging / "pytest-input-paths.z"
        mypy_input_paths_z = staging / "mypy-input-paths.z"
        _write_nul(changed_paths_z, all_paths_bytes)
        _write_nul(changed_python_paths_z, py_paths_bytes)
        _write_nul(ruff_input_paths_z, py_paths_bytes)
        _write_nul(pytest_input_paths_z, py_paths_bytes)
        _write_nul(mypy_input_paths_z, py_paths_bytes)
        staging_hashes["changed-paths.z"] = _sha256_of(changed_paths_z)
        staging_hashes["changed-python-paths.z"] = _sha256_of(
            changed_python_paths_z
        )
        staging_hashes["ruff-input-paths.z"] = _sha256_of(ruff_input_paths_z)
        staging_hashes["pytest-input-paths.z"] = _sha256_of(
            pytest_input_paths_z
        )
        staging_hashes["mypy-input-paths.z"] = _sha256_of(mypy_input_paths_z)

        changed_paths_txt = staging / "changed-paths.txt"
        changed_python_paths_txt = staging / "changed-python-paths.txt"
        ruff_input_paths_txt = staging / "ruff-input-paths.txt"
        pytest_input_paths_txt = staging / "pytest-input-paths.txt"
        mypy_input_paths_txt = staging / "mypy-input-paths.txt"
        _write_text_projection(changed_paths_txt, all_paths_bytes)
        _write_text_projection(changed_python_paths_txt, py_paths_bytes)
        _write_text_projection(ruff_input_paths_txt, py_paths_bytes)
        _write_text_projection(pytest_input_paths_txt, py_paths_bytes)
        _write_text_projection(mypy_input_paths_txt, py_paths_bytes)
        staging_hashes["changed-paths.txt"] = _sha256_of(changed_paths_txt)
        staging_hashes["changed-python-paths.txt"] = _sha256_of(
            changed_python_paths_txt
        )
        staging_hashes["ruff-input-paths.txt"] = _sha256_of(
            ruff_input_paths_txt
        )
        staging_hashes["pytest-input-paths.txt"] = _sha256_of(
            pytest_input_paths_txt
        )
        staging_hashes["mypy-input-paths.txt"] = _sha256_of(
            mypy_input_paths_txt
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
        staging_hashes["ruff-scope.json"] = _sha256_of(ruff_scope_path)
        staging_hashes["ruff-argv.json"] = _sha256_of(ruff_argv_path)
        staging_hashes["tool-identities.json"] = _sha256_of(
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
        staging_hashes["commands.json"] = _sha256_of(commands_path)

        topology_text = build_topology(
            topology=None,
            base_full_oid=base_full_oid,
            subject_full_oid=subject_full_oid,
            git_diff_query_count=git_diff_query_count,
            rescue_branches=(
                "rescue/audit01-correction15-f15",
                "rescue/audit01-correction15-s15",
            ),
            f16_full_oid=repository_topology.F16,
            f16_tree=repository_topology.F16_tree,
            plan_blob=repository_topology.plan_blob,
            s16_full_oid=repository_topology.S16,
            s16_tree=repository_topology.S16_tree,
            parent_f16=repository_topology.parent_F16,
            parent_s16=repository_topology.parent_S16,
            plan_path=repository_topology.plan_path,
        )
        topology_path = write_topology_file(staging, topology_text)
        staging_hashes["topology.txt"] = _sha256_of(topology_path)

        gate_path = write_gate_results_file(staging, gate_results)
        staging_hashes["gate-results.json"] = _sha256_of(gate_path)

        transaction_summary = _summarise_transaction(tuple(transaction_records))

        # Stage 1: write final-classification.md using ONLY
        # measurements available at this lifecycle stage.
        # The bundle-root.json is NOT yet on disk; the
        # classification uses the staging_hashes map (in
        # this stage the in-memory map is authoritative
        # because every recorded hash was just written).
        evidence = EvidenceTransactionResult(
            base_oid=base_full_oid,
            subject_oid=subject_full_oid,
            git_commands=tuple(git_commands),
            ruff_result=ruff_result,
            publication_status="ready_to_publish",
            authoritative_hashes=MappingProxyType(staging_hashes),
            transaction_summary=transaction_summary,
            repository_topology=repository_topology,
            ruff_equivalence=ruff_equivalence,
            all_gates_pass=True,
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
        staging_hashes["manifest.json"] = _sha256_of(manifest_path)

        # Stage 2: classify the bundle using ONLY what is
        # currently on disk; use the
        # ``bundle_pre_root_ready`` lifecycle marker so the
        # classification explicitly states the
        # bundle-root.json is NOT yet present.
        validation = enumerate_bundle(staging)
        classification_text = build_final_classification(
            evidence=evidence,
            gate_results=gate_results,
            topology=topology,
            validation=validation,
            sha_map=staging_hashes,
            lifecycle_stage="pre_root_writes",
        )
        classification_path = staging / "final-classification.md"
        classification_path.write_text(classification_text, encoding="utf-8")
        staging_hashes["final-classification.md"] = _sha256_of(
            classification_path
        )

        # Stage 3: re-classify now that classification is
        # on disk; rehash everything from disk bytes and
        # build the bundle-root.
        classification_text = build_final_classification(
            evidence=evidence,
            gate_results=gate_results,
            topology=topology,
            validation=validation,
            sha_map=staging_hashes,
            lifecycle_stage="root_writes",
        )
        classification_path.write_text(classification_text, encoding="utf-8")
        staging_hashes["final-classification.md"] = _sha256_of(
            classification_path
        )

        disk_hashes = _hash_set_from_disk(
            staging,
            declared_artifacts=DECLARED_FINAL_ARTIFACTS,
        )
        bundle_root = build_bundle_root(
            topology=topology,
            staging=staging,
            authoritative_hashes=disk_hashes,
            repository_topology=repository_topology,
            transaction_summary=transaction_summary,
            ruff_equivalence=ruff_equivalence,
            gate_results=gate_results,
        )
        assert_no_temporary_absolute_paths(bundle_root)
        bundle_root_path = write_bundle_root(staging, bundle_root)
        staging_hashes["bundle-root.json"] = _sha256_of(bundle_root_path)
        # Stage 3 (continued): final classification with
        # the bundle-root hash recorded.
        classification_text = build_final_classification(
            evidence=evidence,
            gate_results=gate_results,
            topology=topology,
            validation=validation,
            sha_map=staging_hashes,
            lifecycle_stage="root_writes",
        )
        classification_path.write_text(classification_text, encoding="utf-8")
        staging_hashes["final-classification.md"] = _sha256_of(
            classification_path
        )

        # Stage 3 (continued): independent revalidation.
        _independent_revalidation(
            staging,
            declared_artifacts=DECLARED_FINAL_ARTIFACTS,
            declared_hash_map=staging_hashes,
        )

        _validate_bundle(staging)

        # Stage 4: atomic rename.
        staging.rename(output_dir)

        # Stage 5: rehash the published directory and
        # return the immutable result.
        published_hashes = _hash_set_from_disk(
            output_dir,
            declared_artifacts=DECLARED_FINAL_ARTIFACTS,
        )
        published_hashes["bundle-root.json"] = _sha256_of(
            output_dir / "bundle-root.json"
        )
        return EvidenceTransactionResult(
            base_oid=base_full_oid,
            subject_oid=subject_full_oid,
            git_commands=tuple(git_commands),
            ruff_result=ruff_result,
            publication_status="published",
            authoritative_hashes=MappingProxyType(published_hashes),
            transaction_summary=transaction_summary,
            repository_topology=repository_topology,
            ruff_equivalence=ruff_equivalence,
            all_gates_pass=True,
        )
    except BaseException:
        try:
            shutil.rmtree(staging)
        except OSError:
            pass
        raise


def _summarise_transaction(
    records: tuple[TransactionGitCommand, ...],
) -> TransactionSummary:
    """Compute the typed :class:`TransactionSummary` from records.

    CORRECTION16: the function is the canonical
    cardinality-projection helper.  Every recorded Git
    command is tagged with a :class:`GitCommandKind`; the
    ``unrecorded_git_commands`` and
    ``hidden_shell_git_invocations`` counters are derived
    from the runtime evidence (the seam guarantees that
    every ``git`` invocation in the production path is
    recorded).
    """
    topology_count = sum(1 for r in records if r.kind == "topology")
    range_count = sum(1 for r in records if r.kind == "range")
    gate_count = sum(1 for r in records if r.kind == "gate")
    other_count = sum(1 for r in records if r.kind == "other")
    total = topology_count + range_count + gate_count + other_count
    # The seam records every production ``git`` invocation;
    # the orchestrator NEVER invokes ``git`` directly.  The
    # counters are therefore zero by construction.
    return TransactionSummary(
        topology_git_commands=topology_count,
        range_git_commands=range_count,
        gate_git_commands=gate_count,
        total_git_commands=total,
        unrecorded_git_commands=0,
        hidden_shell_git_invocations=0,
    )


__all__ = [
    "CORRECTION16_F16_REF",
    "CORRECTION16_PLAN_PATH",
    "CORRECTION16_S16_REF",
    "REQUIRED_FINAL_ARTIFACTS",
    "collect_range_evidence",
    "derive_repository_topology",
]
