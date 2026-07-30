"""R12 gate summary population fail-closed tests."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from scripts.act_local_contract import CheckResult
from scripts.factory.build_gate_summary import CheckOutcome, GateSummary
from scripts.factory.gate_summary_command_env import build_child_env as _env
from scripts.factory.parse_gate_summary import parse_gate_summary
from scripts.factory.populate_gate_summary import (
    REQUIRED_CHECK_NAMES,
    CommandSpec,
    _command_specs,
    build_gate_summary,
)


def _populate_for_test(
    target: Path, failing: set[str] | None = None
) -> GateSummary:
    """Replicate the production populate flow's final write.

    Mirrors :func:`scripts.factory.populate_gate_summary.main` for the
    artifact bytes and the sibling ``gate-summary-validation.json``
    attestation by invoking the canonical
    :func:`scripts.factory.gate_summary_validation_attestation.write_validation_attestation`
    writer so the test surface exercises the exact same code path as
    the producer. NO test-only serializer is allowed to drift.

    The writer requires the target to resolve under ``repo_root``.
    To stay hermetic the helper computes ``repo_root`` from
    ``target`` itself (treating the deepest ``.factory`` parent as
    the repo root). This means the test artifact MUST live under a
    ``.factory/`` directory of the test's repo_root -- which is
    exactly how the production writer treats real artefacts.
    """
    summary = build_gate_summary(target=target, runner=_runner(failing))
    final = GateSummary(
        schema_version=summary.schema_version,
        profile=summary.profile,
        overall_status=summary.overall_status,
        source_status=summary.source_status,
        generated_at=summary.generated_at,
        checks=summary.checks,
        self_tests=summary.self_tests,
        r10_definition_of_done=summary.r10_definition_of_done,
        extras={"required_check_names": list(REQUIRED_CHECK_NAMES)},
    )
    final.write(target)
    # Invoke the canonical writer with ``repo_root`` derived from
    # the deepest ``.factory`` ancestor of ``target``. This keeps
    # the writer's outside-repo guard observable to the test (the
    # helper does NOT bypass the safety contract).
    from scripts.factory.gate_summary_validation_attestation import (
        write_validation_attestation,
    )

    ancestor = target.resolve().parent
    while ancestor.parent != ancestor:
        if ancestor.name == ".factory":
            break
        ancestor = ancestor.parent
    else:
        ancestor = target.resolve().parent
    repo_root = ancestor.parent
    write_validation_attestation(
        repo_root=repo_root,
        target=target,
        parser_command="<test-helper>",
        parser_exit_code=0,
        parser_duration_ms=0,
        decode_status=(
            "pass"
            if final.overall_status == "pass" and final.checks_failed == 0
            else "fail"
        ),
        acceptance_status=(
            "pass"
            if final.overall_status == "pass" and final.checks_failed == 0
            else "fail"
        ),
        diagnostics={
            "checks_total": final.checks_total,
            "checks_failed": final.checks_failed,
            "required_check_names_count": len(REQUIRED_CHECK_NAMES),
            "extras_keys": sorted((final.extras or {}).keys()),
        },
    )
    return final


def _runner(failing: set[str] | None = None) -> Callable[[CommandSpec], CheckOutcome]:
    failures = failing or set()

    def run(spec: CommandSpec) -> CheckOutcome:
        status = "fail" if spec.name in failures else "pass"
        return CheckOutcome(
            name=spec.name,
            status=status,
            duration_ms=1,
            error_message="boom" if status == "fail" else None,
            command=" ".join(spec.argv),
            exit_code=1 if status == "fail" else 0,
        )

    return run


def test_all_children_pass_artifact_passes(tmp_path: Path) -> None:
    final = _populate_for_test(tmp_path / "gate-summary.json")
    parsed = parse_gate_summary(tmp_path / "gate-summary.json")
    assert final.overall_status == "pass"
    assert final.checks_failed == 0
    assert parsed.is_pass


def test_one_child_fails_artifact_fails(tmp_path: Path) -> None:
    final = _populate_for_test(
        tmp_path / "gate-summary.json", failing={"opaque-bearer-regression"}
    )
    parsed = parse_gate_summary(tmp_path / "gate-summary.json")
    assert final.overall_status == "fail"
    assert final.checks_failed == 1
    assert not parsed.is_pass


def test_child_process_cannot_execute_fails_artifact(tmp_path: Path) -> None:
    def runner(spec: CommandSpec) -> CheckOutcome:
        if spec.name == "canonical-verifier-self-test":
            return CheckOutcome(
                name=spec.name,
                status="fail",
                duration_ms=0,
                error_message="No such file or directory",
                command="missing-binary",
                exit_code=127,
            )
        default_runner = _runner()
        return default_runner(spec)

    summary = build_gate_summary(target=tmp_path / "gate-summary.json", runner=runner)
    final = GateSummary(
        schema_version=summary.schema_version,
        profile=summary.profile,
        overall_status=summary.overall_status,
        source_status=summary.source_status,
        generated_at=summary.generated_at,
        checks=summary.checks,
        self_tests=summary.self_tests,
        r10_definition_of_done=summary.r10_definition_of_done,
        extras={"required_check_names": list(REQUIRED_CHECK_NAMES)},
    )
    final.write(tmp_path / "gate-summary.json")
    parsed = parse_gate_summary(tmp_path / "gate-summary.json")
    assert summary.overall_status == "fail"
    assert summary.checks_failed == 1
    assert not parsed.is_pass


def test_zero_executed_checks_is_not_pass(tmp_path: Path) -> None:
    """A summary with zero executed checks must not be reported as passing."""
    summary = GateSummary(
        schema_version=1,
        profile="act-local",
        overall_status="pass",
        source_status="present",
        generated_at=datetime.now(UTC).isoformat(),
        checks=[],
        self_tests={},
        r10_definition_of_done={},
    )
    summary.write(tmp_path / "gate-summary.json")
    parsed = parse_gate_summary(tmp_path / "gate-summary.json")
    assert not parsed.is_pass
    assert "checks_total=0" in str(parsed.parse_errors)


def test_recursion_guard_exits_nonzero(tmp_path: Path) -> None:
    """K9B_GATE_POPULATION_CHILD=1 causes populate_gate_summary.main to exit 2.

    The guard prevents a child populate process from spawning a grandchild
    populate process when verify_all.sh is itself launched from the
    targeted-repository-gate check.  The test MUST pin an isolated
    ``--target`` under ``tmp_path`` so the recursion-guard subprocess
    cannot mutate the committed ``.factory/gate-summary.json`` pair.
    """
    env = os.environ.copy()
    env["K9B_GATE_POPULATION_CHILD"] = "1"
    isolated_target = tmp_path / "gate-summary.json"
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/factory/populate_gate_summary.py",
            "--target",
            str(isolated_target),
        ],
        cwd=str(Path(__file__).resolve().parent.parent.parent),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 2
    assert "recursion detected" in proc.stderr


def test_env_without_guard_does_not_set_population_flag() -> None:
    """_env() must NOT mark every child as K9B_GATE_POPULATION_CHILD=1.

    The recursion guard must be scoped narrowly so legitimate populate
    invocations launched from the full-gate-negative-proofs and other test
    harnesses still run. The guard is propagated ONLY by ``_env_with_guard``
    and applied ONLY to the targeted-repository-gate spec, which is the
    actual cycle path.
    """
    env = _env(Path(__file__).resolve().parent.parent.parent)
    assert env.get("K9B_GATE_POPULATION_CHILD") != "1", (
        "_env() is used by every command spec; if it set the recursion "
        "guard globally it would prevent legitimate populate subprocess "
        "launches from the full-gate-negative-proofs harness."
    )


def test_targeted_repository_gate_command_spec_records_skip_flag(tmp_path: Path) -> None:
    """The targeted-repository-gate CommandSpec must record the
    ``--skip-gate-summary`` flag in its argv so the populate -> verify ->
    populate circular dependency is broken for every reproduce run.

    It must also propagate the recursion guard to its child environment so
    any nested populate launch under verify_all.sh fails fast with exit 2.
    """
    target = tmp_path / "gate-summary.json"
    specs = _command_specs(Path(__file__).resolve().parent.parent.parent, target)
    targeted = next(spec for spec in specs if spec.name == "targeted-repository-gate")
    assert "--skip-gate-summary" in targeted.argv, (
        f"targeted-repository-gate argv does not contain --skip-gate-summary: "
        f"{targeted.argv!r}"
    )
    assert targeted.env is not None
    assert targeted.env.get("K9B_GATE_POPULATION_CHILD") == "1", (
        "targeted-repository-gate env must propagate the recursion guard so "
        "verify_all.sh and any of its sub-checks refuse to start a fresh "
        "populate run."
    )


def test_non_targeted_command_specs_do_not_carry_recursion_guard(tmp_path: Path) -> None:
    """Only the targeted-repository-gate spec carries the recursion guard; all
    other specs (and the global ``_env`` used by the harness scripts) must
    not, so the full-gate-negative-proofs subprocess launches can run.
    """
    target = tmp_path / "gate-summary.json"
    specs = _command_specs(Path(__file__).resolve().parent.parent.parent, target)
    for spec in specs:
        if spec.name == "targeted-repository-gate":
            continue
        assert (spec.env or {}).get("K9B_GATE_POPULATION_CHILD") != "1", (
            f"{spec.name} must NOT carry the recursion guard, otherwise the "
            f"full-gate-negative-proofs subprocess launches would be blocked"
        )


def test_env_dedups_pythonpath_with_pathsep(tmp_path: Path) -> None:
    """_env() must split PYTHONPATH by os.pathsep and remove duplicates; if the
    existing PYTHONPATH already contains the same path as one of the defaults,
    the final PYTHONPATH must not contain duplicates separated by ``:``.
    """
    cwd = tmp_path
    src_dir = cwd / "src"
    src_dir.mkdir()
    repo = cwd
    repo.mkdir(exist_ok=True)  # make the directory exist
    # Build a PYTHONPATH that already contains the same path that _env()
    # would inject; this used to produce a duplicated entry in the join.
    existing = f"{src_dir}:{cwd / 'scripts' / 'src'}"
    os.environ["PYTHONPATH"] = existing
    try:
        env = _env(cwd)
    finally:
        os.environ.pop("PYTHONPATH", None)
    parts = env["PYTHONPATH"].split(os.pathsep)
    assert len(parts) == len(set(parts)), (
        f"PYTHONPATH has duplicates: {parts!r}"
    )


def test_skip_gate_summary_flag_makes_verify_succeed_without_artifact(
    tmp_path: Path,
) -> None:
    """``--skip-gate-summary`` must allow ACT-local verification to succeed
    even when the gate-summary artifact does NOT exist.

    Hermeticity: this test never touches the real tracked artifact under
    ``.factory/gate-summary.json``. Instead it injects a
    ``tmp_path`` artifact via ``run_gate_summary_parser_check`` and
    drives a controlled check registry that excludes the frontend
    vitest check, golden-case checks, and any other check that depends
    on local dependencies (Node modules, network access, provider smoke
    checks, etc.). The contract under test is the gate-summary-parser
    skip path, nothing more.

    Behavioral assertions:

    * With ``skip_gate_summary=True``: the gate-summary-parser check is
      omitted from ``checks`` and listed in ``skipped_checks``; the
      overall run succeeds because the parser is not evaluated.
    * With ``skip_gate_summary=False`` (and no artifact present): the
      gate-summary-parser check FAILS fast with the canonical
      "gate-summary artifact not found" diagnostic, and the overall run
      fails.
    """
    # The injected artifact lives ONLY in tmp_path. No real tracked
    # artifact is renamed, deleted, or otherwise mutated.
    tmp_artifact = tmp_path / "gate-summary.json"
    assert not tmp_artifact.exists(), (
        "tmp_path should not pre-create the artifact for this test"
    )

    # Import lazily so a missing dependency in unrelated tests cannot
    # break the rest of the suite. The act_local_verification module
    # uses absolute imports (``from act_local_changed_files import ...``)
    # so we must add the ``scripts/`` directory to ``sys.path`` for
    # those imports to resolve.
    import sys as _sys

    _scripts_dir = str(Path(__file__).resolve().parent.parent.parent / "scripts")
    if _scripts_dir not in _sys.path:
        _sys.path.insert(0, _scripts_dir)
    from scripts.act_local_verification import (
        run_act_local_verification,
    )

    # A controlled registry: a few deterministic PASS checks. This
    # proves the skip path is wired in WITHOUT running the frontend
    # vitest check (which would require Node modules and network
    # access) or any other unrelated ACT-local check.
    def _passing_check(name: str) -> Callable[[list[str], list[str]], CheckResult]:
        def _run(_py_files: list[str], _changed: list[str]) -> CheckResult:
            return CheckResult(
                name=name,
                command=f"<controlled-pass:{name}>",
                status="PASS",
                duration_ms=0,
                exit_code=0,
                error_message=None,
            )

        return _run

    controlled_registry: list[Callable[[list[str], list[str]], CheckResult]] = [
        _passing_check("controlled-pass-ruff"),
        _passing_check("controlled-pass-mypy"),
    ]

    # Path A: --skip-gate-summary means the parser is omitted from
    # the executed-checks list and recorded as a skipped_check.
    skip_result = run_act_local_verification(
        check_registry=controlled_registry,
        skip_gate_summary=True,
        include_gate_summary_parser=False,
        changed_files=[],
        python_files=[],
        gate_summary_artifact_path=tmp_artifact,
    )

    assert skip_result.success is True, (
        f"Expected success with --skip-gate-summary; got errors: "
        f"{[c.error_message for c in skip_result.checks if c.status != 'PASS']}"
    )

    executed_names = {c.name for c in skip_result.checks}
    assert "gate-summary-parser" not in executed_names, (
        f"--skip-gate-summary must omit the gate-summary-parser check from "
        f"the reported checks list; got {executed_names}"
    )
    skipped_ids = {s.get("id") for s in skip_result.skipped_checks}
    assert "gate-summary-parser" in skipped_ids, (
        f"--skip-gate-summary must explicitly list the gate-summary-parser "
        f"check in skipped_checks; got {skipped_ids}"
    )

    # Path B: without --skip-gate-summary and with no artifact at the
    # injected path, the parser check FAILS fast with the canonical
    # diagnostic. The real .factory/gate-summary.json is never read.
    no_skip_result = run_act_local_verification(
        check_registry=controlled_registry,
        skip_gate_summary=False,
        include_gate_summary_parser=True,
        changed_files=[],
        python_files=[],
        gate_summary_artifact_path=tmp_artifact,
    )

    assert no_skip_result.success is False, (
        "Without --skip-gate-summary and with no artifact present, "
        "the parser check must FAIL and the overall run must fail."
    )
    parser_results = [
        c for c in no_skip_result.checks
        if c.name == "gate-summary-parser"
    ]
    assert len(parser_results) == 1, (
        f"Expected exactly one gate-summary-parser check; got {parser_results}"
    )
    assert parser_results[0].status == "FAIL", (
        f"gate-summary-parser should FAIL with no artifact; "
        f"status={parser_results[0].status}"
    )
    assert "gate-summary artifact not found" in (
        parser_results[0].error_message or ""
    ), (
        f"Expected canonical diagnostic; got {parser_results[0].error_message!r}"
    )
    assert str(tmp_artifact) in (parser_results[0].error_message or ""), (
        f"Diagnostic must reference the injected path {tmp_artifact}; "
        f"got {parser_results[0].error_message!r}"
    )
