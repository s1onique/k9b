"""CORRECTION03 portability + delegated hash evidence-architecture proofs.

Companion to ``test_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01_correction03_attestation_delegation_guards.py``.
This file owns the negative proofs and runner-portable replay
assertions.  Splitting the responsibilities keeps the canonical
delegation proof in a small file (< 500 lines) and isolates the
runner-specific test infrastructure here.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts" / "factory"

POPULATE_FILE = SCRIPTS_ROOT / "populate_gate_summary.py"
ATTESTATION_FILE = SCRIPTS_ROOT / "gate_summary_validation_attestation.py"

GATE_SUMMARY_PATH = REPO_ROOT / ".factory" / "gate-summary.json"


def _record_ruff_replay_argv(recorded_command: str) -> list[str]:
    """Reconstruct a portable ``python -m ruff check`` invocation.

    The recorded command is historical evidence from the producer host
    and is NOT runner-portable: it may embed an absolute interpreter
    path that does not exist on the current runner.  The replay must
    re-launch the ruff module from the current interpreter so the
    semantic contract (``ruff`` status against the current source
    tree) is preserved on every host.

    Returns the argv to pass to :func:`subprocess.run` for replay.
    """

    tokens = shlex.split(recorded_command)
    if "-m" not in tokens:
        raise AssertionError("recorded ruff command MUST use the -m grammar")
    module_marker = tokens.index("-m")
    if module_marker + 1 >= len(tokens):
        raise AssertionError("recorded ruff command MUST name a module after -m")
    if tokens[module_marker + 1] != "ruff":
        raise AssertionError("recorded ruff command MUST target the ruff module")
    if module_marker + 2 >= len(tokens):
        raise AssertionError("recorded ruff command MUST include a subcommand")
    if tokens[module_marker + 2] != "check":
        raise AssertionError("recorded ruff command MUST use the check subcommand")
    if module_marker + 3 >= len(tokens):
        raise AssertionError("recorded ruff command MUST include at least one target")
    return [sys.executable, "-m", "ruff", "check", *tokens[module_marker + 3 :]]


def test_delegated_hash_negative_proofs() -> None:
    populate = POPULATE_FILE.read_text()
    attestation = ATTESTATION_FILE.read_text()
    base_producer = textwrap.dedent(
        """
        def main():
            final.write(target)
            _run(parser_spec)
            write_validation_attestation(repo_root=repo_root, target=target)
        """
    )

    fixtures = {
        "attestation_before_parser": base_producer.replace(
            "_run(parser_spec)\n    write_validation_attestation",
            "write_validation_attestation(repo_root=repo_root, target=target)\n    _run(parser_spec)\n    # writer call above is the intentionally early call\n    write_validation_attestation",
        ),
        "parser_before_final_write": base_producer.replace(
            "final.write(target)\n    _run(parser_spec)",
            "_run(parser_spec)\n    final.write(target)",
        ),
        "reader_without_target_bytes": attestation.replace(
            "data = target.read_bytes()", "data = b\"not-the-target\""
        ),
        "writer_persists_final_sha": attestation.replace(
            '"validated_sha256": computed_sha', '"validated_sha256": final_sha256'
        ),
        "writer_hashes_different_bytes": attestation.replace(
            "hashlib.sha256(artifact_bytes)", "hashlib.sha256(other_bytes)"
        ),
        "producer_duplicate_sha": populate
        + "\n\ndef duplicate_sha(target):\n    return hashlib.sha256(target.read_bytes()).hexdigest()\n",
    }

    from tests.verifiers.test_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01_correction03_attestation_delegation_guards import (
        _architecture_errors,
    )

    for name, fixture in fixtures.items():
        fixture_populate = (
            fixture
            if name in {
                "attestation_before_parser",
                "parser_before_final_write",
                "producer_duplicate_sha",
            }
            else base_producer
        )
        fixture_attestation = fixture if name in {
            "reader_without_target_bytes",
            "writer_persists_final_sha",
            "writer_hashes_different_bytes",
        } else attestation
        errors = _architecture_errors(fixture_populate, fixture_attestation)
        assert errors, f"negative fixture {name!r} was accepted"


def test_portable_parser_command_is_stable() -> None:
    from scripts.factory.gate_summary_validation_attestation import portable_parser_command

    command = portable_parser_command(validated_path=".factory/gate-summary.json")
    assert command == (
        "python scripts/factory/parse_gate_summary.py "
        "--target .factory/gate-summary.json --quiet"
    )
    assert "/Users/" not in command
    assert "/home/runner/" not in command
    assert "/private/" not in command
    assert "\\" not in command


def test_populate_subprocess_invocations_use_explicit_tmp_target() -> None:
    """AST guard: every test subprocess invocation of the producer
    MUST pass an explicit ``--target`` under ``tmp_path`` (or an
    isolated directory).  The producer's default target is the
    canonical ``.factory/gate-summary.json``; a test that omits the
    flag rewrites the committed evidence and breaks the freshness
    contract.
    """
    import ast as _ast

    for path in (
        REPO_ROOT / "tests" / "unit" / "test_gate_summary_population_r12.py",
        REPO_ROOT / "tests" / "unit" / "test_gate_summary_population_portable_attestation_r12.py",
        REPO_ROOT / "tests" / "unit" / "test_gate_summary_parser_adversarial.py",
        REPO_ROOT / "tests" / "unit" / "test_gate_summary_validation_attestation.py",
        REPO_ROOT / "tests" / "unit" / "test_gate_summary_validation_verifier.py",
    ):
        if not path.exists():
            continue
        tree = _ast.parse(path.read_text(encoding="utf-8"))
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.Call):
                continue
            if isinstance(node.func, _ast.Attribute) and node.func.attr == "run":
                if not (
                    isinstance(node.func.value, _ast.Name)
                    and node.func.value.id == "subprocess"
                ):
                    continue
                argv_list = node.args[0] if node.args else None
                if not isinstance(argv_list, _ast.List):
                    continue
                literals = [
                    elt.value
                    for elt in argv_list.elts
                    if isinstance(elt, _ast.Constant) and isinstance(elt.value, str)
                ]
                if any(
                    "populate_gate_summary" in value for value in literals
                ):
                    assert "--target" in literals, (
                        f"{path.name} invokes populate_gate_summary.py without an "
                        f"explicit --target; the default target is the committed "
                        f".factory/gate-summary.json and would mutate canonical evidence."
                    )
            if isinstance(node.func, _ast.Name) and node.func.id == "main":
                if not node.args:
                    continue
                if any(
                    isinstance(arg, _ast.Constant)
                    and isinstance(arg.value, str)
                    and "populate_gate_summary" in arg.value
                    for arg in node.args
                ):
                    assert any(
                        isinstance(arg, _ast.Constant)
                        and arg.value == "--target"
                        for arg in node.args
                    ), (
                        f"{path.name} calls populate_gate_summary.main(...) without an "
                        "explicit --target argument; the producer's default target "
                        "is the committed .factory/gate-summary.json."
                    )


def test_committed_gate_summary_ruff_status_matches_current_tree() -> None:
    """A committed ruff diagnostic must describe the current source tree.

    The recorded command is a host-specific execution transcript, not a
    portable script.  The replay reconstructs a portable ``-m ruff check``
    invocation against :data:`sys.executable` so the test produces the
    same result on every runner.
    """
    if not GATE_SUMMARY_PATH.exists():
        pytest.skip(".factory/gate-summary.json is missing")
    import json as _json
    data = _json.loads(GATE_SUMMARY_PATH.read_text(encoding="utf-8"))
    ruff_checks = [check for check in data.get("checks", []) if check.get("name") == "ruff"]
    if len(ruff_checks) != 1:
        pytest.fail("gate-summary.json must contain exactly one ruff check")
    check = ruff_checks[0]
    command = check.get("command")
    assert isinstance(command, str) and command
    argv = _record_ruff_replay_argv(command)
    result = subprocess.run(argv, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    actual_status = "pass" if result.returncode == 0 else "fail"
    assert check.get("status") == actual_status, (
        f"recorded ruff status={check.get('status')!r} but current command "
        f"returned {result.returncode}: {(result.stderr or result.stdout)[-500:]}"
    )


def json_loads_safe(text: str) -> object:
    """Local alias to keep the helper import-free in this module."""
    import json
    return json.loads(text)


@pytest.mark.parametrize(
    "recorded",
    [
        "/Users/dev/proj/.venv/bin/python -m ruff check scripts/factory/populate_gate_summary.py",
        "/home/runner/work/k9b/.venv/bin/python -m ruff check tests/verifiers/test_split_architecture.py",
        "python -m ruff check tests/verifiers/test_split_architecture.py",
    ],
)
def test_portable_ruff_replay_uses_current_interpreter(recorded: str) -> None:
    """Recorded host-specific commands must replay through ``sys.executable``."""
    argv = _record_ruff_replay_argv(recorded)
    assert argv[0] == sys.executable
    assert argv[1:4] == ["-m", "ruff", "check"]
    assert argv[4:] == shlex.split(recorded)[4:]


def test_portable_ruff_replay_preserves_target_ordering() -> None:
    recorded = "python -m ruff check tests/verifiers/a.py scripts/factory/b.py src/c.py"
    argv = _record_ruff_replay_argv(recorded)
    assert argv[4:] == [
        "tests/verifiers/a.py",
        "scripts/factory/b.py",
        "src/c.py",
    ]


@pytest.mark.parametrize(
    "bad_command",
    [
        "python scripts/factory/parse_gate_summary.py --target .factory/gate-summary.json",
        "python -m pytest tests/verifiers/test_split_architecture.py",
        "python -m ruff format scripts/factory/populate_gate_summary.py",
        "python -m ruff check",
    ],
)
def test_portable_ruff_replay_rejects_non_ruff_commands(bad_command: str) -> None:
    with pytest.raises(AssertionError):
        _record_ruff_replay_argv(bad_command)
