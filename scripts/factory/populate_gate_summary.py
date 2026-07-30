"""Execute and persist the complete ACT-local evidence privacy gate summary.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01-
CORRECTION03-EXTERNAL-EVIDENCE-AND-PARSER-FAIL-CLOSED-TRUTH01:

The producer writes ``.factory/gate-summary.json`` first, then validates
the exact bytes of that artifact with the canonical parser and writes
the result to a separate sibling attestation
``.factory/gate-summary-validation.json``.  The validation attestation
is NOT included in the bytes it validates -- the parser invocation
result lives in a sibling file so a subsequent mutation of
``gate-summary.json`` is detectable as a SHA-256 mismatch.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.factory.build_gate_summary import (  # noqa: E402
    GateSummary,
    SubsystemSelfTestCount,
    make_r10_defaults,
)
from scripts.factory.gate_summary_changed_paths import (  # noqa: E402
    _changed_python_files,
    _read_changed_paths_manifest,
)
from scripts.factory.gate_summary_command_env import (  # noqa: E402
    SCRIPT_REPO,
    VENV_PYTHON,
    CommandSpec,
    Runner,
    build_child_env,
    build_child_env_with_guard,
    git_cwd,
    run_subprocess,
    source_root,
)
from scripts.factory.gate_summary_parser_runner import (  # noqa: E402
    run_parser_and_capture_verdict,
)
from scripts.factory.gate_summary_ruff_target_verifier import (  # noqa: E402
    RuffTargetSetError,
    verify_recorded_ruff_targets,
)
from scripts.factory.gate_summary_validation_attestation import (  # noqa: E402
    portable_parser_command,
    write_validation_attestation,
)
from scripts.incident_lifecycle_boundary.redaction_self_test_runner import (  # noqa: E402
    run_self_tests as verifier_run_self_tests,
)

# ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01-CORRECTION02:
# ``gate-summary-parser`` is removed from the required check
# inventory. The parser is the self-referential consumer of the
# artifact; including it in ``checks_total``/``checks_failed``
# would create a circular dependency.
#
# ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01-CORRECTION03:
# The parser invocation result lives in a SEPARATE sibling
# attestation artifact (``gate-summary-validation.json``), NOT
# inside ``gate-summary.json``.  Embedding the result inside the
# artifact would create a self-referential contract: the result
# would change the bytes that were supposedly validated.  The
# canonical contract is
# ``len(checks) == checks_total == len(required_check_names)``.
REQUIRED_CHECK_NAMES = (
    "canonical-verifier-self-test",
    "standalone-production-verifier",
    "production-mypy-positive",
    "production-mypy-negative",
    "full-gate-negative-proofs",
    "opaque-bearer-regression",
    "sanitizer-regression-matrix",
    "credential-matrix",
    "omission-boundary",
    "serializer-multi-return",
    "ruff",
    "mypy",
    "git-diff-check",
    "git-diff-cached-check",
    "llm-friendly",
    "no-new-llm-allowlist",
    "targeted-repository-gate",
)
PARSER_POSTCONDITION_NAME = "gate-summary-parser"


def _core01_mypy_manifest_complete(
    argv: list[str], expected_paths: tuple[str, ...]
) -> bool:
    """Self-test: the generated canonical mypy command includes the
    complete CORE01 manifest.

    Returns True when every expected path is present in the
    command argv (substring match against the joined command).
    A failing self-test raises ``AssertionError`` from the
    caller's :func:`_command_specs` so the producer can never
    silently drop a CORE01 path.
    """
    joined = " ".join(argv)
    return all(path in joined for path in expected_paths)


def _pytest_spec(repo_root: Path, name: str, *nodeids: str) -> CommandSpec:
    return CommandSpec(
        name=name,
        argv=[str(VENV_PYTHON), "-m", "pytest", "-q", *nodeids],
        cwd=SCRIPT_REPO,
        env=build_child_env(repo_root),
    )


def _authoritative_manifest_sha256(manifest_path: Path) -> str:
    """Compute the SHA-256 of the authoritative changed-paths manifest.

    The manifest is authoritative because the gate-summary producer
    uses it as the canonical source of the Ruff command targets.  The
    SHA-256 identity is persisted in the artifact so verifiers can
    confirm the manifest was not silently mutated between the range
    harvest and the artifact emission.
    """
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def _self_test_ruff_recorded_targets(
    *,
    authoritative_paths: list[str],
    recorded_argv: list[str],
) -> None:
    """Production verifier self-test.

    The producer MUST validate that the recorded Ruff argv it just
    generated equals the authoritative manifest before persisting the
    artifact.  Failing closed here is the production equivalent of the
    previous test-only "smaller than full" negation: the canonical
    verifier is the single source of truth and the test surface
    invokes the same function.
    """
    try:
        verify_recorded_ruff_targets(
            authoritative_paths=authoritative_paths,
            recorded_argv=recorded_argv,
        )
    except RuffTargetSetError as exc:
        raise AssertionError(
            f"producer-ruff-self-test-failed: code={exc.code} message={exc}"
        ) from exc


def _command_specs(
    repo_root: Path,
    target: Path,
    *,
    changed_paths_manifest: Path | None = None,
) -> list[CommandSpec]:
    env = build_child_env(repo_root)
    resolved_source_root = source_root(repo_root)
    if changed_paths_manifest is not None:
        changed_py = _read_changed_paths_manifest(changed_paths_manifest)
    else:
        changed_py = _changed_python_files() or ["scripts/factory/populate_gate_summary.py"]
    # CORRECTION05 R8: the canonical mypy command MUST visibly
    # include the complete CORE01 manifest:
    #   * the verifier_core package (covered by the package
    #     wildcard ``[mypy-scripts.verifiers.verifier_core.*]``
    #     in mypy.ini);
    #   * the R20 workset verifier consumer;
    #   * the surviving CORE01 test files (the contract tests,
    #     the mypy-fixture test, the production-shape test);
    #   * the existing redaction-module coverage preserved
    #     verbatim (CORE01 does NOT regress that surface).
    mypy_targets = [
        # Existing redaction-module coverage (preserved verbatim).
        "src/k8s_diag_agent/collect/incident_evidence_redaction.py",
        "src/k8s_diag_agent/collect/incident_evidence_llm_safe.py",
        "src/k8s_diag_agent/security/redaction_policy.py",
        "src/k8s_diag_agent/security/sanitizer.py",
        # CORE01 production-consumer surface.
        "scripts/verifiers/verifier_core/",
        "scripts/verifiers/incident_current_run_promotion_workset01.py",
        # CORE01 contract tests.
        "tests/verifiers/test_verifier_core.py",
        "tests/verifiers/test_canonical_doctrine_matches_production.py",
        "tests/verifiers/test_verifier_core_mypy_fixture.py",
    ]
    # The CORE01 self-test asserts the generated mypy command
    # contains every CORE01 manifest path. The check is
    # performed in :func:`_core01_mypy_manifest_complete`.
    expected_core01_mypy_paths = (
        "scripts/verifiers/verifier_core/",
        "scripts/verifiers/incident_current_run_promotion_workset01.py",
        "tests/verifiers/test_verifier_core.py",
        "tests/verifiers/test_canonical_doctrine_matches_production.py",
        "tests/verifiers/test_verifier_core_mypy_fixture.py",
    )
    core01_mypy_argv = [str(VENV_PYTHON), "-m", "mypy", *mypy_targets, "--ignore-missing-imports"]
    assert _core01_mypy_manifest_complete(core01_mypy_argv, expected_core01_mypy_paths), (
        "canonical gate mypy command is missing CORE01 manifest paths"
    )
    # The targeted-repository-gate command is the actual cycle path; it must
    # inherit the recursion guard so any nested populate launch under
    # verify_all.sh fails fast with exit code 2 rather than recursively
    # driving the gate.
    targeted_env = build_child_env_with_guard(repo_root)
    return [
        CommandSpec(
            "canonical-verifier-self-test",
            [str(VENV_PYTHON), str(SCRIPT_REPO / "scripts/incident_lifecycle_boundary/redaction_types.py"), "--self-test"],
            env=env,
        ),
        CommandSpec(
            "standalone-production-verifier",
            [str(VENV_PYTHON), str(SCRIPT_REPO / "scripts/incident_lifecycle_boundary/redaction_types.py"), "--repo-root", str(resolved_source_root)],
            env=env,
        ),
        _pytest_spec(repo_root, "production-mypy-positive", "tests/unit/test_redaction_r9_mypy_fixtures.py::TestMypyPositiveFixture"),
        _pytest_spec(repo_root, "production-mypy-negative", "tests/unit/test_redaction_r9_mypy_fixtures.py::TestMypyNegativeFixture"),
        CommandSpec(
            "full-gate-negative-proofs",
            [str(VENV_PYTHON), str(SCRIPT_REPO / "scripts/incident_lifecycle_boundary/redaction_types.py"), "--repo-root", str(resolved_source_root)]
            if os.environ.get("K9B_R12_FULL_GATE_PROOF_CHILD")
            else [
                str(VENV_PYTHON),
                str(SCRIPT_REPO / "scripts/incident_lifecycle_boundary/redaction_full_gate_negative_proofs.py"),
            ],
            env=env,
        ),
        _pytest_spec(repo_root, "opaque-bearer-regression", "tests/unit/test_redaction_r11_sanitizer_opaque_bearer.py"),
        _pytest_spec(repo_root, "sanitizer-regression-matrix", "tests/unit/test_redaction_r9_sanitizer_credential.py::test_sentinel_secret_is_absent_from_every_sanitizer_path"),
        _pytest_spec(repo_root, "credential-matrix", "tests/unit/test_redaction_r9_sanitizer_credential.py::TestCredentialMatrix"),
        _pytest_spec(repo_root, "omission-boundary", "tests/unit/test_redaction_r8_omission_branch.py"),
        _pytest_spec(repo_root, "serializer-multi-return", "tests/unit/test_redaction_r12_serializer_multi_return.py"),
        CommandSpec("ruff", [str(VENV_PYTHON), "-m", "ruff", "check", *changed_py], env=env),
        CommandSpec("mypy", [str(VENV_PYTHON), "-m", "mypy", *mypy_targets, "--ignore-missing-imports"], env=env),
        CommandSpec("git-diff-check", ["git", "diff", "--check"], cwd=git_cwd(repo_root), env=env),
        CommandSpec("git-diff-cached-check", ["git", "diff", "--cached", "--check"], cwd=git_cwd(repo_root), env=env),
        CommandSpec("llm-friendly", [str(VENV_PYTHON), str(SCRIPT_REPO / "scripts/check_llm_friendly_files.py"), "--changed-only"], env=env),
        CommandSpec("no-new-llm-allowlist", [str(VENV_PYTHON), str(SCRIPT_REPO / "scripts/verify_no_new_llm_allowlist.py")], env=env),
        CommandSpec(
            "targeted-repository-gate",
            [
                str(SCRIPT_REPO / "scripts/verify_all.sh"),
                "--act-local",
                "--skip-gate-summary",
            ]
            if repo_root == SCRIPT_REPO
            else [
                str(VENV_PYTHON),
                str(SCRIPT_REPO / "scripts/incident_lifecycle_boundary/redaction_types.py"),
                "--repo-root",
                str(resolved_source_root),
            ],
            cwd=SCRIPT_REPO,
            env=targeted_env,
        ),
        CommandSpec("gate-summary-parser", [str(VENV_PYTHON), str(SCRIPT_REPO / "scripts/factory/parse_gate_summary.py"), "--target", str(target), "--quiet"], env=env),
    ]


def build_gate_summary(
    *,
    repo_root: Path = SCRIPT_REPO,
    target: Path | None = None,
    changed_paths_manifest: Path | None = None,
    range_base: str | None = None,
    range_head: str | None = None,
    runner: Runner = run_subprocess,
) -> GateSummary:
    """Run every required check and return a populated summary.

    The gate-summary-parser check is intentionally NOT part of the written
    checks list. The parser is a self-referential validator; including it in
    ``checks_total``/``checks_failed`` would create a circular dependency
    with the parser subprocess that the canonical ``parse_gate_summary``
    executable runs.

    When ``changed_paths_manifest`` is supplied, the producer:

    1. reads the manifest as the authoritative Ruff target set;
    2. SHA-256s the manifest and records the identity in ``extras``;
    3. calls the production verifier as a self-test so the recorded
       Ruff argv cannot silently diverge from the manifest.
    """
    target = target or repo_root / ".factory" / "gate-summary.json"
    specs = _command_specs(
        repo_root,
        target,
        changed_paths_manifest=changed_paths_manifest,
    )
    checks = [
        runner(spec) for spec in specs if spec.name != "gate-summary-parser"
    ]

    # Production self-test: the recorded Ruff argv MUST equal the
    # authoritative manifest exactly.  When the manifest is supplied
    # the self-test runs unconditionally; when no manifest is
    # supplied (the legacy no-manifest path) the self-test is skipped
    # because the legacy reflected unstaged/staged diffs.
    extras: dict[str, object] = {
        "required_check_names": list(REQUIRED_CHECK_NAMES),
    }
    if changed_paths_manifest is not None:
        authoritative_paths = _read_changed_paths_manifest(changed_paths_manifest)
        ruff_spec = next(spec for spec in specs if spec.name == "ruff")
        _self_test_ruff_recorded_targets(
            authoritative_paths=authoritative_paths,
            recorded_argv=ruff_spec.argv,
        )
        extras["changed_paths_manifest_sha256"] = _authoritative_manifest_sha256(
            changed_paths_manifest
        )
        extras["changed_paths_manifest_count"] = len(authoritative_paths)
        extras["changed_paths_manifest_entries"] = sorted(authoritative_paths)
    if range_base is not None:
        extras["range_base"] = range_base
    if range_head is not None:
        extras["range_head"] = range_head

    accepted, rejected, failed = verifier_run_self_tests()[0:3]
    failed_total = sum(1 for check in checks if check.status == "fail")
    summary = GateSummary(
        schema_version=1,
        profile="act-local",
        overall_status="pass" if failed_total == 0 else "fail",
        source_status="present",
        generated_at=datetime.now(UTC).isoformat(),
        checks=checks,
        self_tests={"verifier_self_tests": SubsystemSelfTestCount(accepted, rejected, failed)},
        r10_definition_of_done=make_r10_defaults(),
        extras=extras,
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    # Recursion guard: refuse to run nested under another populate process.
    if os.environ.get("K9B_GATE_POPULATION_CHILD") == "1":
        print(
            "ERROR: populate_gate_summary.py recursion detected "
            "(K9B_GATE_POPULATION_CHILD=1). Refusing to start a nested run.",
            file=sys.stderr,
        )
        return 2

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=SCRIPT_REPO)
    parser.add_argument("--target", type=Path, default=SCRIPT_REPO / ".factory" / "gate-summary.json")
    parser.add_argument(
        "--changed-paths-manifest",
        type=Path,
        default=None,
        help=(
            "Optional NUL-delimited changed-paths manifest (output of "
            "'git diff --name-only -z <base>..<head>'). When supplied, the "
            "manifest is the authoritative source for the Ruff check; the "
            "producer fails closed on an empty, missing, non-Python, or "
            "non-repository-relative manifest."
        ),
    )
    parser.add_argument(
        "--range-base",
        default=None,
        help=(
            "Optional base SHA recorded in the artifact for verifier "
            "consumers. When supplied, the SHA is persisted verbatim in "
            "extras.range_base."
        ),
    )
    parser.add_argument(
        "--range-head",
        default=None,
        help=(
            "Optional head SHA recorded in the artifact for verifier "
            "consumers. When supplied, the SHA is persisted verbatim in "
            "extras.range_head."
        ),
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    repo_root = args.repo_root.resolve()
    target = args.target.resolve()
    summary = build_gate_summary(
        repo_root=repo_root,
        target=target,
        changed_paths_manifest=args.changed_paths_manifest,
        range_base=args.range_base,
        range_head=args.range_head,
    )
    target.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: write the canonical gate-summary artifact WITHOUT
    # any parser validation result. The artifact bytes must be
    # final before validation runs -- embedding the validation
    # outcome inside the validated artifact is a self-referential
    # contract that the parser cannot decode.  The ``extras``
    # payload built by :func:`build_gate_summary` carries the
    # authoritative manifest identity, SHA-256, and entry list,
    # so we preserve it verbatim instead of overwriting it.
    final = GateSummary(
        schema_version=summary.schema_version,
        profile=summary.profile,
        overall_status=summary.overall_status,
        source_status=summary.source_status,
        generated_at=datetime.now(UTC).isoformat(),
        checks=summary.checks,
        self_tests=summary.self_tests,
        r10_definition_of_done=summary.r10_definition_of_done,
        extras=summary.extras,
    )
    final.write(target)

    # Step 3: run the canonical parser subprocess and capture its
    # output for the validation attestation. The exit code drives
    # the producer's overall return code.  The verifier-extraction
    # helper handles the subprocess so the producer never crashes
    # on a transient parser failure.
    parser_spec = next(
        spec for spec in _command_specs(repo_root, target)
        if spec.name == PARSER_POSTCONDITION_NAME
    )
    parser_outcome, decode_status, acceptance_status = (
        run_parser_and_capture_verdict(parser_spec)
    )

    # Step 5: write the validation attestation to a SIBLING
    # artifact. The attestation is NOT included in the bytes it
    # validates. A subsequent mutation of ``gate-summary.json``
    # is detectable as a SHA-256 mismatch.
    #
    # ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION05 +
    # CORRECTION06: ``validated_path`` MUST be a portable
    # repository-relative POSIX path so the committed attestation
    # is byte-identical on every runner. The writer computes the
    # SHA from the artifact bytes itself (no caller-supplied
    # authority) and rejects out-of-repository targets and
    # non-regular files at the seam. The writer logic lives in
    # :mod:`scripts.factory.gate_summary_validation_attestation`
    # so the gate-summary producer stays under the 500-line cap.

    portable_target = target.resolve().relative_to(repo_root.resolve()).as_posix()
    # The writer reads from its own (imported) namespace; we re-bind
    # the names here for clarity at the call site.

    attestation_path = write_validation_attestation(
        repo_root=repo_root,
        target=target,
        parser_command=portable_parser_command(validated_path=portable_target),
        parser_exit_code=parser_outcome.exit_code,
        parser_duration_ms=parser_outcome.duration_ms,
        decode_status=decode_status,
        acceptance_status=acceptance_status,
        diagnostics={
            "checks_total": final.checks_total,
            "checks_failed": final.checks_failed,
            "required_check_names_count": len(REQUIRED_CHECK_NAMES),
            "extras_keys": sorted((final.extras or {}).keys()),
        },
    )

    print(f"wrote {target}")
    print(
        f"checks_total={final.checks_total} checks_failed={final.checks_failed} "
        f"overall={final.overall_status} "
        f"decode_status={decode_status} acceptance_status={acceptance_status}"
    )
    print(f"wrote {attestation_path}")
    if final.overall_status != "pass" or final.checks_failed != 0:
        return 1
    if decode_status != "pass":
        return 2
    if acceptance_status != "pass":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
