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
import os
import shlex
import subprocess  # noqa: F401  (used by CommandSpec subprocess.run through _run)
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SCRIPT_REPO = Path(__file__).resolve().parent.parent.parent
VENV_PYTHON = SCRIPT_REPO / ".venv" / "bin" / "python"

sys.path.insert(0, str(SCRIPT_REPO))
from scripts.factory.build_gate_summary import (  # noqa: E402
    CheckOutcome,
    GateSummary,
    SubsystemSelfTestCount,
    make_r10_defaults,
)
from scripts.factory.gate_summary_changed_paths import (  # noqa: E402
    _changed_python_files,
    _read_changed_paths_manifest,
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


@dataclass(frozen=True)
class CommandSpec:
    """A named subprocess command in the populated gate."""

    name: str
    argv: list[str]
    expect_zero: bool = True
    cwd: Path | None = None
    env: dict[str, str] | None = None


Runner = Callable[[CommandSpec], CheckOutcome]


def _source_root(repo_root: Path) -> Path:
    """Return the verifier source root for a repository-root/worktree seam."""
    if (repo_root / "src" / "k8s_diag_agent").exists():
        return repo_root / "src"
    return repo_root


def _git_cwd(repo_root: Path) -> Path:
    """Use repo_root for git commands only when it is a git worktree."""
    return repo_root if (repo_root / ".git").exists() else SCRIPT_REPO


def _env(repo_root: Path) -> dict[str, str]:
    """Build the child-process environment used by populate's checks.

    Note: ``K9B_GATE_POPULATION_CHILD=1`` is NOT propagated here; doing so
    would prevent legitimate ``populate`` invocations launched from the
    full-gate-negative-proofs and other test harnesses. The recursion guard
    is propagated only to the ``targeted-repository-gate`` spec, since that
    is the only command that can actually trigger a populate -> verify ->
    populate cycle.
    """
    env = os.environ.copy()
    source_root = _source_root(repo_root)
    # Deduplicate PYTHONPATH entries (separated by os.pathsep) so mypy does
    # not see the same module from two roots and emit "Duplicate module"
    # errors.
    existing_paths = env.get("PYTHONPATH", "").split(os.pathsep)
    seen: set[str] = set()
    ordered: list[str] = []
    for p in (
        str(source_root),
        str(SCRIPT_REPO),
        str(SCRIPT_REPO / "src"),
        *existing_paths,
    ):
        if not p or p in seen:
            continue
        seen.add(p)
        ordered.append(p)
    env["PYTHONPATH"] = os.pathsep.join(ordered)
    # MYPYPATH is intentionally not set: the child mypy invocation uses
    # explicit file paths relative to cwd (the repo root). Setting MYPYPATH
    # to the same root causes "Duplicate module" errors.
    env.pop("MYPYPATH", None)
    env.setdefault("HOME", str(Path.home()))
    return env


def _env_with_guard(repo_root: Path) -> dict[str, str]:
    """Like ``_env`` but propagates ``K9B_GATE_POPULATION_CHILD=1``.

    Used only for the ``targeted-repository-gate`` command, which routes
    through ``verify_all.sh --act-local`` and is the actual cycle path.
    """
    env = _env(repo_root)
    env["K9B_GATE_POPULATION_CHILD"] = "1"
    return env


def _run(spec: CommandSpec) -> CheckOutcome:
    """Run a child command and derive a CheckOutcome from the subprocess result."""
    started = time.time()
    try:
        proc = subprocess.run(
            spec.argv,
            capture_output=True,
            text=True,
            cwd=str(spec.cwd or SCRIPT_REPO),
            env=spec.env,
            timeout=300,
            check=False,
        )
        exit_code = proc.returncode
        output = (proc.stderr or "") + (proc.stdout or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        exit_code = 124 if isinstance(exc, subprocess.TimeoutExpired) else 127
        output = str(exc)

    duration_ms = int((time.time() - started) * 1000)
    ok = (exit_code == 0) == spec.expect_zero
    return CheckOutcome(
        name=spec.name,
        status="pass" if ok else "fail",
        duration_ms=duration_ms,
        error_message=None if ok else output[:1000],
        command=shlex.join(spec.argv),
        exit_code=exit_code,
    )


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
        env=_env(repo_root),
    )


def _command_specs(
    repo_root: Path,
    target: Path,
    *,
    changed_paths_manifest: Path | None = None,
) -> list[CommandSpec]:
    env = _env(repo_root)
    source_root = _source_root(repo_root)
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
    targeted_env = _env_with_guard(repo_root)
    return [
        CommandSpec(
            "canonical-verifier-self-test",
            [str(VENV_PYTHON), str(SCRIPT_REPO / "scripts/incident_lifecycle_boundary/redaction_types.py"), "--self-test"],
            env=env,
        ),
        CommandSpec(
            "standalone-production-verifier",
            [str(VENV_PYTHON), str(SCRIPT_REPO / "scripts/incident_lifecycle_boundary/redaction_types.py"), "--repo-root", str(source_root)],
            env=env,
        ),
        _pytest_spec(repo_root, "production-mypy-positive", "tests/unit/test_redaction_r9_mypy_fixtures.py::TestMypyPositiveFixture"),
        _pytest_spec(repo_root, "production-mypy-negative", "tests/unit/test_redaction_r9_mypy_fixtures.py::TestMypyNegativeFixture"),
        CommandSpec(
            "full-gate-negative-proofs",
            [str(VENV_PYTHON), str(SCRIPT_REPO / "scripts/incident_lifecycle_boundary/redaction_types.py"), "--repo-root", str(source_root)]
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
        CommandSpec("git-diff-check", ["git", "diff", "--check"], cwd=_git_cwd(repo_root), env=env),
        CommandSpec("git-diff-cached-check", ["git", "diff", "--cached", "--check"], cwd=_git_cwd(repo_root), env=env),
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
                str(source_root),
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
    runner: Runner = _run,
) -> GateSummary:
    """Run every required check and return a populated summary.

    The gate-summary-parser check is intentionally NOT part of the written
    checks list. The parser is a self-referential validator; including it in
    ``checks_total``/``checks_failed`` would create a circular dependency
    with the parser subprocess that the canonical ``parse_gate_summary``
    executable runs.
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
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    repo_root = args.repo_root.resolve()
    target = args.target.resolve()
    summary = build_gate_summary(
        repo_root=repo_root,
        target=target,
        changed_paths_manifest=args.changed_paths_manifest,
    )
    target.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: write the canonical gate-summary artifact WITHOUT
    # any parser validation result. The artifact bytes must be
    # final before validation runs -- embedding the validation
    # outcome inside the validated artifact is a self-referential
    # contract that the parser cannot decode.
    final = GateSummary(
        schema_version=summary.schema_version,
        profile=summary.profile,
        overall_status=summary.overall_status,
        source_status=summary.source_status,
        generated_at=datetime.now(UTC).isoformat(),
        checks=summary.checks,
        self_tests=summary.self_tests,
        r10_definition_of_done=summary.r10_definition_of_done,
        extras={
            "required_check_names": list(REQUIRED_CHECK_NAMES),
        },
    )
    final.write(target)

    # Step 3: run the canonical parser subprocess and capture its
    # output for the validation attestation. The exit code drives
    # the producer's overall return code.
    parser_spec = next(
        spec for spec in _command_specs(repo_root, target)
        if spec.name == PARSER_POSTCONDITION_NAME
    )
    parser_outcome = _run(parser_spec)

    # Step 4: parse the validator's stdout for ``decode_status`` /
    # ``acceptance_status`` so the attestation carries the
    # typed verdict.
    decode_status = "fail"
    acceptance_status = "fail"
    stdout_text = ""
    try:
        parser_proc = subprocess.run(
            parser_spec.argv,
            capture_output=True,
            text=True,
            cwd=str(parser_spec.cwd or SCRIPT_REPO),
            env=parser_spec.env,
            timeout=120,
            check=False,
        )
        stdout_text = parser_proc.stdout or ""
        for line in stdout_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("decode_status="):
                decode_status = stripped.split("=", 1)[1].strip()
            elif stripped.startswith("acceptance_status="):
                acceptance_status = stripped.split("=", 1)[1].strip()
    except (OSError, subprocess.TimeoutExpired):
        pass

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
