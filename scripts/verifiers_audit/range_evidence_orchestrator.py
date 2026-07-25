"""CORRECTION14: detached range evidence orchestrator.

The orchestrator is the canonical producer of the detached
evidence bundle.  It is invoked by :mod:`range_evidence`
(the CLI / library entry point).  The orchestrator:

1. asserts the output directory is initially absent;
2. resolves the full commit object IDs for ``base`` and
   ``subject`` via :func:`_resolve_full_commit` and the
   injected :class:`GitRunner` (one rev-parse per side);
3. calls :func:`changed_path_bytes` EXACTLY ONCE and records
   the executed transcript;
4. derives the Python subset in-process via
   :func:`python_path_bytes`;
5. resolves the Ruff identity via
   :func:`resolve_ruff_identity` (which raises
   :class:`RuffToolUnavailable` on failure);
6. builds the executed Ruff argv from the same identity;
7. writes the complete bundle in ONE staging transaction;
8. atomically renames the staging directory to the final
   destination after every required artifact is present.

The orchestrator is extracted from :mod:`range_evidence` to
keep both modules under the 500-line LLM-friendly threshold.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from types import MappingProxyType

from scripts.verifiers_audit.range_evidence_builders import (
    build_bundle_root,
    build_manifest_from_evidence,
    build_topology,
)
from scripts.verifiers_audit.range_evidence_classification import (
    build_final_classification,
)
from scripts.verifiers_audit.range_evidence_helpers import (
    GitRunner,
    SubprocessGitRunner,
    _resolve_full_commit,
    _sha256_of,
    _write_nul,
    _write_text_projection,
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
    changed_path_bytes,
    python_path_bytes,
)
from scripts.verifiers_audit.typed_results import (
    ClosureTopology,
    CommandResult,
    EvidenceTransactionResult,
)

REQUIRED_FINAL_ARTIFACTS: tuple[str, ...] = (
    "manifest.json",
    "topology.txt",
    "gate-results.json",
    "changed-paths.z",
    "changed-python-paths.z",
    "ruff-input-paths.z",
    "ruff-scope.json",
    "ruff-argv.json",
    "tool-identities.json",
    "commands.json",
    "final-classification.md",
    "bundle-root.json",
)


def _execute_ruff(
    argv: tuple[str, ...],
    *,
    cwd: Path,
) -> CommandResult:
    """Execute the Ruff argv and return a typed :class:`CommandResult`."""
    proc = subprocess.run(
        list(argv),
        cwd=str(cwd),
        capture_output=True,
        check=False,
    )
    stdout_sha = hashlib.sha256(proc.stdout).hexdigest()
    stderr_sha = hashlib.sha256(proc.stderr).hexdigest()
    status = "passed" if proc.returncode == 0 else "failed"
    return CommandResult(
        argv=tuple(argv),
        returncode=proc.returncode,
        stdout_sha256=stdout_sha,
        stderr_sha256=stderr_sha,
        status=status,  # type: ignore[arg-type]
    )


def _validate_bundle(staging: Path) -> None:
    """Validate that every required artifact is present in ``staging``."""
    missing = [
        name for name in REQUIRED_FINAL_ARTIFACTS
        if not (staging / name).exists()
    ]
    if missing:
        raise FileNotFoundError(
            f"bundle staging incomplete; missing: {missing}"
        )


def collect_range_evidence(
    *,
    base: str,
    subject: str,
    repo_root: Path,
    output_dir: Path,
    topology: ClosureTopology | None = None,
    gate_results: tuple[CommandResult, ...] = (),
    git_runner: GitRunner | None = None,
) -> EvidenceTransactionResult:
    """Produce the detached evidence bundle for ``base..subject``.

    See :mod:`range_evidence_orchestrator` for the full
    orchestration contract.  This function returns the
    typed :class:`EvidenceTransactionResult`.

    ``topology`` is optional for backward compatibility with
    the CORRECTION13 test suite; when omitted, a placeholder
    record with empty ``F14`` / ``F14_tree`` / ``plan_blob`` /
    ``parent_F14`` fields is used.  Production callers
    SHOULD supply a real :class:`ClosureTopology` derived
    from the live closure commit.
    """
    if topology is None:
        topology = ClosureTopology(
            F14="",
            F14_tree="",
            plan_blob="",
            S14=None,
            S14_tree=None,
            parent_F14="",
            parent_S14=None,
        )
    if output_dir.exists():
        raise FileExistsError(
            f"FRESH_DESTINATION_REQUIRED: {output_dir} already exists; "
            f"--force-replace is not supported in CORRECTION13/CORRECTION14"
        )

    if git_runner is None:
        git_runner = SubprocessGitRunner()

    git_commands: list[CommandResult] = []

    base_rev_argv: tuple[str, ...] = (
        "git", "rev-parse", "--verify", f"{base}^{{commit}}"
    )
    base_rev = git_runner.run(base_rev_argv, cwd=repo_root)
    git_commands.append(base_rev)
    base_full_oid = _resolve_full_commit(
        base,
        repo_root=repo_root,
        stage="resolve_base",
        base=base,
        subject=subject,
    )
    if base_rev.status == "failed":
        from scripts.verifiers_audit.scope import RangeResolutionError

        raise RangeResolutionError(
            base=base,
            subject=subject,
            argv=base_rev.argv,
            returncode=base_rev.returncode,
            stderr=base_rev.stderr_sha256,
            stage="resolve_base",
        )

    subject_full_oid = _resolve_full_commit(
        subject,
        repo_root=repo_root,
        stage="resolve_subject",
        base=base,
        subject=subject,
    )
    subject_rev_argv: tuple[str, ...] = (
        "git", "rev-parse", "--verify", f"{subject}^{{commit}}"
    )
    subject_rev = git_runner.run(subject_rev_argv, cwd=repo_root)
    git_commands.append(subject_rev)
    if subject_rev.status == "failed":
        from scripts.verifiers_audit.scope import RangeResolutionError

        raise RangeResolutionError(
            base=base,
            subject=subject,
            argv=subject_rev.argv,
            returncode=subject_rev.returncode,
            stderr=subject_rev.stderr_sha256,
            stage="resolve_subject",
        )

    diff_argv: tuple[str, ...] = (
        "git",
        "diff",
        "--name-only",
        "-z",
        "--diff-filter=ACMRT",
        base_full_oid,
        subject_full_oid,
    )
    diff_result = git_runner.run(diff_argv, cwd=repo_root)
    git_commands.append(diff_result)
    if diff_result.status == "failed":
        from scripts.verifiers_audit.scope import RangeResolutionError

        raise RangeResolutionError(
            base=base,
            subject=subject,
            argv=diff_argv,
            returncode=diff_result.returncode,
            stderr=diff_result.stderr_sha256,
            stage="diff_names",
        )
    all_paths_bytes = changed_path_bytes(
        base_full_oid, subject_full_oid, repo_root=repo_root
    )
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

    staging = output_dir.parent / (
        f"{output_dir.name}.tmp.{os.getpid()}"
    )
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    git_diff_query_count = sum(
        r.argv[:2] == ("git", "diff") for r in git_commands
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

        if skip_ruff:
            ruff_result: CommandResult | None = CommandResult(
                argv=(),
                returncode=0,
                stdout_sha256=hashlib.sha256(b"").hexdigest(),
                stderr_sha256=hashlib.sha256(b"").hexdigest(),
                status="skipped",
            )
        else:
            ruff_result = _execute_ruff(
                executed_argv, cwd=repo_root
            )
            if ruff_result.status == "failed":
                raise subprocess.CalledProcessError(
                    ruff_result.returncode, list(ruff_result.argv)
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
                "rescue/audit01-correction13-f13",
                "rescue/audit01-correction13-s13",
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
            output_dir=output_dir,
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

        classification_text = build_final_classification(
            evidence=evidence,
            gate_results=gate_results,
            topology=topology,
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
        bundle_root_path = staging / "bundle-root.json"
        import json as _json

        bundle_root_path.write_text(
            _json.dumps(bundle_root, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        _validate_bundle(staging)

        staging.rename(output_dir)

        published_evidence = EvidenceTransactionResult(
            base_oid=base_full_oid,
            subject_oid=subject_full_oid,
            git_commands=tuple(git_commands),
            ruff_result=ruff_result,
            publication_status="published",
            authoritative_hashes=MappingProxyType(authoritative_hashes),
        )
        return published_evidence
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