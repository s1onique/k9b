"""R12 gate summary population fail-closed tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from scripts.factory.build_gate_summary import CheckOutcome, GateSummary
from scripts.factory.parse_gate_summary import parse_gate_summary
from scripts.factory.populate_gate_summary import (
    REQUIRED_CHECK_NAMES,
    CommandSpec,
    _command_specs,
    _env,
    build_gate_summary,
)


def _populate_for_test(
    target: Path, failing: set[str] | None = None
) -> GateSummary:
    """Replicate the production populate flow's final write: collect checks via
    ``build_gate_summary``, then attach ``extras.required_check_names`` so the
    parser will treat the artifact as a real, pass-able summary.
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


def test_recursion_guard_exits_nonzero() -> None:
    """K9B_GATE_POPULATION_CHILD=1 causes populate_gate_summary.main to exit 2.

    The guard prevents a child populate process from spawning a grandchild
    populate process when verify_all.sh is itself launched from the
    targeted-repository-gate check.
    """
    env = os.environ.copy()
    env["K9B_GATE_POPULATION_CHILD"] = "1"
    proc = subprocess.run(
        [sys.executable, "scripts/factory/populate_gate_summary.py"],
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


def test_skip_gate_summary_flag_makes_verify_succeed_without_artifact() -> None:
    """verify_all.sh --act-local --skip-gate-summary must succeed even when
    .factory/gate-summary.json does NOT exist.

    This is the meaningful behavioral assertion: without the flag the
    run_gate_summary_parser_check FAILS fast and verify_all exits nonzero;
    with the flag the check is omitted so verification can complete while
    populate_gate_summary is concurrently writing the artifact.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    factory_dir = repo_root / ".factory"
    backup = None
    existing_artifact = factory_dir / "gate-summary.json"
    if existing_artifact.exists():
        backup = factory_dir / "gate-summary.json.bak"
        existing_artifact.rename(backup)

    try:
        # With --skip-gate-summary: pass even though the artifact is absent.
        skip_proc = subprocess.run(
            [
                "bash",
                "scripts/verify_all.sh",
                "--act-local",
                "--skip-gate-summary",
                "--json",
            ],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert skip_proc.returncode == 0, (
            f"exit_code={skip_proc.returncode}\nstdout={skip_proc.stdout}\n"
            f"stderr={skip_proc.stderr}"
        )
        assert '"success": true' in skip_proc.stdout
        data = json.loads(skip_proc.stdout)
        names = [c.get("name") for c in data.get("checks", [])]
        assert "gate-summary-parser" not in names, (
            "--skip-gate-summary must omit the gate-summary-parser check from "
            "the reported checks list"
        )
        skipped_ids = {s.get("id") for s in data.get("skipped_checks", [])}
        assert "gate-summary-parser" in skipped_ids, (
            "--skip-gate-summary must explicitly list the gate-summary-parser "
            "check in skipped_checks"
        )

        # Without the flag (and with the artifact absent): fail and emit the
        # diagnostic that proves the check is now wired in.
        no_skip_proc = subprocess.run(
            [
                "bash",
                "scripts/verify_all.sh",
                "--act-local",
                "--json",
            ],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert no_skip_proc.returncode != 0, (
            "Without --skip-gate-summary and with no artifact present, "
            "verify_all.sh must exit nonzero.\n"
            f"stdout={no_skip_proc.stdout}\nstderr={no_skip_proc.stderr}"
        )
        assert "gate-summary-parser" in no_skip_proc.stdout
        assert "gate-summary artifact not found" in no_skip_proc.stdout
    finally:
        if backup is not None and backup.exists():
            backup.rename(existing_artifact)


def test_parser_check_is_not_written_to_artifact(tmp_path: Path) -> None:
    """The gate-summary-parser is the self-referential validator; it must not
    appear in the artifact's ``checks`` list. It IS declared in
    ``extras.required_check_names`` so the parser subprocess records it as
    evidence of completeness.
    """
    _populate_for_test(tmp_path / "gate-summary.json")
    written = json.loads((tmp_path / "gate-summary.json").read_text(encoding="utf-8"))
    written_names = {c["name"] for c in written.get("checks", [])}
    assert "gate-summary-parser" not in written_names, (
        "gate-summary-parser must not be a member of the executed checks list"
    )
    required = set(written.get("extras", {}).get("required_check_names", []))
    assert "gate-summary-parser" in required, (
        f"required_check_names must contain 'gate-summary-parser'; got {required!r}"
    )
    assert "targeted-repository-gate" in required
    # The targeted-repository-gate check executed in production must record
    # the --skip-gate-summary flag so the artifact documents the
    # circular-dependency break in plaintext.
    targeted = next(
        c for c in written.get("checks", []) if c["name"] == "targeted-repository-gate"
    )
    assert "--skip-gate-summary" in targeted["command"], (
        f"targeted-repository-gate command must contain --skip-gate-summary; "
        f"got {targeted['command']!r}"
    )
