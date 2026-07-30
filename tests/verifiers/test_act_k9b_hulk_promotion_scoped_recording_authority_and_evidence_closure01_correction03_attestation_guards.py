"""CORRECTION03 evidence-architecture guards.

These guards prove the delegated attestation ownership introduced by
CORRECTION06 rather than requiring the producer to duplicate byte reads or
hashing.  The checks are AST-based so a similarly named but disconnected
operation cannot satisfy the contract accidentally.
"""

from __future__ import annotations

import ast
import hashlib
import json
import shlex
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts" / "factory"

PARSE_FILE = SCRIPTS_ROOT / "parse_gate_summary.py"
POPULATE_FILE = SCRIPTS_ROOT / "populate_gate_summary.py"
ATTESTATION_FILE = SCRIPTS_ROOT / "gate_summary_validation_attestation.py"

GATE_SUMMARY_PATH = REPO_ROOT / ".factory" / "gate-summary.json"
VALIDATION_ATTESTATION_PATH = REPO_ROOT / ".factory" / "gate-summary-validation.json"


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(matches) != 1 or not isinstance(matches[0], ast.FunctionDef):
        raise AssertionError(f"expected exactly one synchronous function {name!r}")
    return matches[0]


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _calls(node: ast.AST) -> list[ast.Call]:
    return sorted(
        (item for item in ast.walk(node) if isinstance(item, ast.Call)),
        key=lambda item: (item.lineno, item.col_offset),
    )


def _is_target_read(call: ast.Call) -> bool:
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "read_bytes"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "target"
    )


def _is_final_write(call: ast.Call) -> bool:
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "write"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "final"
        and bool(call.args)
        and isinstance(call.args[0], ast.Name)
        and call.args[0].id == "target"
    )


def _is_parser_call(call: ast.Call) -> bool:
    if _call_name(call) == "_run":
        return bool(call.args) and isinstance(call.args[0], ast.Name) and call.args[0].id == "parser_spec"
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "run"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "subprocess"
        and bool(call.args)
        and isinstance(call.args[0], ast.Attribute)
        and isinstance(call.args[0].value, ast.Name)
        and call.args[0].value.id == "parser_spec"
        and call.args[0].attr == "argv"
    )


def _is_attestation_call(call: ast.Call) -> bool:
    return _call_name(call) == "write_validation_attestation"


def _sha256_call(call: ast.Call) -> ast.Call | None:
    if not (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "hexdigest"
        and isinstance(call.func.value, ast.Call)
    ):
        return None
    sha_call = call.func.value
    if not (
        isinstance(sha_call.func, ast.Attribute)
        and sha_call.func.attr == "sha256"
        and isinstance(sha_call.func.value, ast.Name)
        and sha_call.func.value.id == "hashlib"
        and len(sha_call.args) == 1
    ):
        return None
    return sha_call


def _architecture_errors(populate_text: str, attestation_text: str) -> list[str]:
    """Return structural violations for the delegated hash contract."""
    populate_tree = ast.parse(populate_text)
    attestation_tree = ast.parse(attestation_text)
    errors: list[str] = []

    main = _function(populate_tree, "main")
    main_calls = _calls(main)
    final_writes = [call for call in main_calls if _is_final_write(call)]
    parser_calls = [call for call in main_calls if _is_parser_call(call)]
    attestation_calls = [call for call in main_calls if _is_attestation_call(call)]
    if not final_writes:
        errors.append("main must call final.write(target)")
    if not parser_calls:
        errors.append("main must invoke the canonical parser")
    if not attestation_calls:
        errors.append("main must call write_validation_attestation")
    if final_writes and parser_calls and final_writes[0].lineno >= parser_calls[0].lineno:
        errors.append("parser must run after final.write(target)")
    if parser_calls and attestation_calls and parser_calls[-1].lineno >= attestation_calls[0].lineno:
        errors.append("write_validation_attestation must run after the parser")

    # The producer is orchestration only.  Byte reading and SHA ownership
    # must not be reintroduced here as a second implementation.
    if any(_is_target_read(call) for call in _calls(populate_tree)):
        errors.append("populate_gate_summary must not read target bytes")
    if any(_sha256_call(call) is not None for call in _calls(populate_tree)):
        errors.append("populate_gate_summary must not compute a second SHA-256")

    writer = _function(attestation_tree, "write_validation_attestation")
    writer_calls = _calls(writer)
    portable_calls = [
        call
        for call in writer_calls
        if _call_name(call) == "_portable_validated_path"
        and {keyword.arg for keyword in call.keywords} >= {"repo_root", "target"}
    ]
    if not portable_calls:
        errors.append("writer must own portable validated_path computation")

    reader_calls = [
        call
        for call in writer_calls
        if _call_name(call) == "_read_and_hash_target"
        and len(call.args) == 1
        and isinstance(call.args[0], ast.Name)
        and call.args[0].id == "target"
    ]
    if not reader_calls:
        errors.append("writer must delegate target bytes to _read_and_hash_target(target)")

    computed_sha_names: set[str] = set()
    for statement in ast.walk(writer):
        if not isinstance(statement, ast.Assign):
            continue
        sha_calls = [call for call in _calls(statement.value) if _sha256_call(call) is not None]
        if not sha_calls:
            continue
        sha_call = _sha256_call(sha_calls[0])
        if sha_call is None or not isinstance(sha_call.args[0], ast.Name) or sha_call.args[0].id != "artifact_bytes":
            errors.append("writer SHA-256 must be computed from artifact_bytes")
        for target in statement.targets:
            if isinstance(target, ast.Name):
                computed_sha_names.add(target.id)
    if not computed_sha_names:
        errors.append("writer must compute hashlib.sha256(artifact_bytes).hexdigest()")

    persisted_values: list[ast.expr] = []
    for node in ast.walk(writer):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "validated_sha256" and value is not None:
                persisted_values.append(value)
    if not any(isinstance(value, ast.Name) and value.id in computed_sha_names for value in persisted_values):
        errors.append("validated_sha256 must originate from the computed SHA variable")
    if any(isinstance(value, ast.Name) and value.id == "final_sha256" for value in persisted_values):
        errors.append("validated_sha256 must not persist caller-supplied final_sha256")

    reader = _function(attestation_tree, "_read_and_hash_target")
    if not any(_is_target_read(call) for call in _calls(reader)):
        errors.append("_read_and_hash_target must call target.read_bytes()")

    return errors


def _assert_architecture(populate_text: str, attestation_text: str) -> None:
    errors = _architecture_errors(populate_text, attestation_text)
    assert not errors, "delegated attestation architecture violations: " + "; ".join(errors)


# ---------------------------------------------------------------------------
# Runtime artifact contracts
# ---------------------------------------------------------------------------


def test_validation_attestation_present_when_summary_present() -> None:
    if not GATE_SUMMARY_PATH.exists():
        pytest.skip(".factory/gate-summary.json is missing")
    assert VALIDATION_ATTESTATION_PATH.exists(), (
        "populate_gate_summary MUST write the sibling validation attestation"
    )


def test_validation_attestation_sha256_binds_final_bytes() -> None:
    if not VALIDATION_ATTESTATION_PATH.exists():
        pytest.skip("validation attestation is missing")
    data = json.loads(VALIDATION_ATTESTATION_PATH.read_text(encoding="utf-8"))
    attested_sha = data.get("validated_sha256")
    assert attested_sha, "validated_sha256 missing from attestation"
    actual_sha = hashlib.sha256(GATE_SUMMARY_PATH.read_bytes()).hexdigest()
    assert attested_sha == actual_sha, f"{attested_sha} != {actual_sha}"


def test_validation_attestation_includes_decode_and_acceptance() -> None:
    if not VALIDATION_ATTESTATION_PATH.exists():
        pytest.skip("validation attestation is missing")
    data = json.loads(VALIDATION_ATTESTATION_PATH.read_text(encoding="utf-8"))
    assert data.get("decode_status") in {"pass", "fail"}
    assert data.get("acceptance_status") in {"pass", "fail"}


def test_validation_attestation_excludes_self_referential_evidence() -> None:
    if not GATE_SUMMARY_PATH.exists():
        pytest.skip(".factory/gate-summary.json is missing")
    data = json.loads(GATE_SUMMARY_PATH.read_text(encoding="utf-8"))
    extras = data.get("extras", {})
    assert not isinstance(extras, dict) or "parser_postcondition" not in extras


# ---------------------------------------------------------------------------
# Delegated ownership and ordering guards
# ---------------------------------------------------------------------------


def test_delegated_attestation_architecture_is_structurally_proven() -> None:
    _assert_architecture(POPULATE_FILE.read_text(), ATTESTATION_FILE.read_text())


def test_parser_runs_after_final_write_in_producer() -> None:
    """The exact former CI node now proves delegation and ordering via AST."""
    _assert_architecture(POPULATE_FILE.read_text(), ATTESTATION_FILE.read_text())


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


def test_committed_gate_summary_ruff_status_matches_current_tree() -> None:
    """A committed ruff diagnostic must describe the current source tree."""
    if not GATE_SUMMARY_PATH.exists():
        pytest.skip(".factory/gate-summary.json is missing")
    data = json.loads(GATE_SUMMARY_PATH.read_text(encoding="utf-8"))
    ruff_checks = [check for check in data.get("checks", []) if check.get("name") == "ruff"]
    if len(ruff_checks) != 1:
        pytest.fail("gate-summary.json must contain exactly one ruff check")
    check = ruff_checks[0]
    command = check.get("command")
    assert isinstance(command, str) and command
    argv = shlex.split(command)
    assert "ruff" in argv and "check" in argv
    result = subprocess.run(argv, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    actual_status = "pass" if result.returncode == 0 else "fail"
    assert check.get("status") == actual_status, (
        f"recorded ruff status={check.get('status')!r} but current command "
        f"returned {result.returncode}: {(result.stderr or result.stdout)[-500:]}"
    )
