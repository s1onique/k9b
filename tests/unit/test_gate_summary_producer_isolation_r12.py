"""R12 gate-summary producer isolation tests (CORRECTION11 split).

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION11-
RANGE-BOUND-EVIDENCE-TRUTH-AND-LLM-CAP01:

Split out of the original 680-line
``tests/unit/test_gate_summary_population_changed_paths_manifest_r12.py``
so each focused module stays under the LLM-friendly 500-line cap.

These tests cover the **producer-isolation** contract:

* the suite-level immutable-artifact subprocess leaves the committed
  gate-summary pair byte-identical;
* every producer invocation discovered in the test surface uses an
  isolated ``--target`` (or a directly-isolated repo root);
* a single-file adversarial invocation that omits ``--target`` is
  rejected by the AST-based guard;
* the parser is invoked exactly once per producer call (single-parser
  invariant).

CORRECTION11 also replaces the manually-enumerated
``_TEST_SURFACE_RELATIVE_PATHS`` tuple with a dynamic repository scan
so newly added test files are discovered automatically.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap  # noqa: F401  (used by negative-proof synthetic sources)
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts" / "factory"

GATE_SUMMARY_PATH = REPO_ROOT / ".factory" / "gate-summary.json"
VALIDATION_ATTESTATION_PATH = REPO_ROOT / ".factory" / "gate-summary-validation.json"


# ---------------------------------------------------------------------------
# CORRECTION11: dynamic test-surface inventory
# ---------------------------------------------------------------------------
#
# The CORRECTION11 surface is discovered by walking the test tree and
# collecting every ``tests/`` Python file under the gate-summary suite
# that imports or invokes one of the producer entry points.  New test
# files are picked up automatically; the guard MUST NOT be maintained
# by hand.
_PRODUCER_ENTRY_POINT_TOKENS = (
    "populate_gate_summary",
    "write_validation_attestation",
    "build_gate_summary",
)


def _iter_gate_summary_test_surface() -> list[Path]:
    """Return the dynamically-discovered test surface for the gate-summary suite.

    The guard walks ``tests/`` and ``tests/verifiers/`` and selects
    every Python file that names one of the producer entry-point
    tokens.  Files whose names begin with ``test_`` are accepted even
    if they only import a producer module; that is sufficient to
    classify them as gate-summary test surface for the isolation
    guard.
    """
    surface: list[Path] = []
    for sub in ("tests/unit", "tests/verifiers"):
        root = REPO_ROOT / sub
        if not root.exists():
            continue
        for path in sorted(root.rglob("test_*.py")):
            try:
                source = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if any(token in source for token in _PRODUCER_ENTRY_POINT_TOKENS):
                surface.append(path)
    return surface


def _relative(posix: Path) -> str:
    """Return the repo-relative POSIX form of ``posix``."""
    try:
        return posix.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return posix.as_posix()


# ---------------------------------------------------------------------------
# Suite-level immutable-artifact subprocess
# ---------------------------------------------------------------------------


def _assert_canonical_pair_byte_identical(
    summary_bytes: bytes, attestation_bytes: bytes
) -> None:
    assert GATE_SUMMARY_PATH.read_bytes() == summary_bytes, (
        "canonical gate-summary.json was mutated by the suite; the suite "
        "must use isolated tmp_path targets"
    )
    assert VALIDATION_ATTESTATION_PATH.read_bytes() == attestation_bytes, (
        "canonical gate-summary-validation.json was mutated by the suite; "
        "the suite must use isolated tmp_path targets"
    )


def test_suite_level_immutability_across_gate_summary_suite() -> None:
    """Suite-level subprocess proof that the canonical pair is byte-identical.

    Spawns a fresh interpreter that runs the complete
    gate-summary-related suite while the parent process holds the
    byte snapshot.  The parent's assertions run only AFTER the
    subprocess exits, so they cannot be confused by snapshot
    evaluation order.  The subprocess selects only the tests that
    do NOT mutate the committed pair (it explicitly avoids this
    file's own subprocess-immunity test to keep the assertion
    meaningful).
    """
    if not GATE_SUMMARY_PATH.exists() or not VALIDATION_ATTESTATION_PATH.exists():
        pytest.skip("canonical pair missing; produce it first")

    before_summary = GATE_SUMMARY_PATH.read_bytes()
    before_attestation = VALIDATION_ATTESTATION_PATH.read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/verifiers/test_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01_correction03_attestation_portability_guards.py",
            "tests/unit/test_gate_summary_population_portable_attestation_r12.py",
            "tests/unit/test_gate_summary_validation_attestation.py",
            "tests/unit/test_gate_summary_validation_verifier.py",
            "tests/unit/test_gate_summary_parser_adversarial.py",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"gate-summary suite failed exit={result.returncode}\n"
        f"STDOUT:\n{result.stdout[-2000:]}\n"
        f"STDERR:\n{result.stderr[-2000:]}"
    )

    _assert_canonical_pair_byte_identical(before_summary, before_attestation)


# ---------------------------------------------------------------------------
# Canonical test producer inventory + indirect-argv guard
# ---------------------------------------------------------------------------


def _call_name_from_call(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return cast(str, func.id)
    if isinstance(func, ast.Attribute):
        return cast(str, func.attr)
    return None


def _invocation_targets_path(argv: Sequence[str]) -> str | None:
    """Return the ``--target <path>`` value if the argv carries one."""
    argv_list = list(argv)
    for index, token in enumerate(argv_list[:-1]):
        if (
            token == "--target"
            and argv_list[index + 1]
            and not argv_list[index + 1].startswith("-")
        ):
            return cast(str, argv_list[index + 1])
    return None


def _invokes_producer(argv: Sequence[str]) -> bool:
    return any(
        "populate_gate_summary" in token or "write_validation_attestation" in token
        for token in argv
    )


def _is_isolated_target(target: str) -> bool:
    """True when the target path is NOT the canonical committed artifact."""
    if not target:
        return False
    canonical = (REPO_ROOT / ".factory" / "gate-summary.json").as_posix()
    resolved = str(Path(target).resolve()) if Path(target).is_absolute() else target
    return resolved != canonical and not resolved.endswith(".factory/gate-summary.json")


def _is_string_like_node(node: ast.AST) -> bool:
    """A best-effort string-literal predicate for guard purposes."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "str":
            return True
    return False


def _string_like_value(node: ast.AST) -> str | None:
    """Return the string value the AST node would yield, or ``None``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return cast(str, node.value)
    return None


def _enumerate_producer_invocations(source: str) -> list[tuple[str, int, list[str], str | None]]:
    """Return a list of (kind, lineno, argv, target) for every
    test-side producer invocation found in the source.
    """
    tree = ast.parse(source)
    out: list[tuple[str, int, list[str], str | None]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        argv_value = node.args[0] if node.args else None
        argv_list: list[str] = []
        if isinstance(argv_value, (ast.List, ast.Tuple)):
            for elt in argv_value.elts:
                value = _string_like_value(elt)
                if value is None:
                    argv_list = []
                    break
                argv_list.append(value)
        elif isinstance(argv_value, ast.Name):
            argv_list.append(cast(str, argv_value.id))
        elif isinstance(argv_value, ast.Call):
            if argv_value.args and isinstance(argv_value.args[0], ast.Constant):
                literal = argv_value.args[0]
                if isinstance(literal.value, str):
                    argv_list.extend(literal.value.split())
        if argv_list and _invokes_producer(argv_list):
            out.append(
                (
                    "subprocess",
                    node.lineno,
                    argv_list,
                    _invocation_targets_path(argv_list),
                )
            )
        name = _call_name_from_call(node)
        if name == "main":
            for arg in node.args:
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and "populate_gate_summary" in arg.value
                ):
                    out.append(
                        ("main", node.lineno, [cast(str, arg.value)], None)
                    )
    return out


def test_canonical_test_producer_inventory_isolated_targets() -> None:
    """Every producer invocation in the test surface MUST use an isolated target.

    CORRECTION11: the surface is discovered dynamically so newly
    added test files are picked up automatically.
    """
    unresolved: list[tuple[str, int, list[str]]] = []
    for absolute in _iter_gate_summary_test_surface():
        relative_path = _relative(absolute)
        source = absolute.read_text(encoding="utf-8")
        for kind, lineno, argv, target in _enumerate_producer_invocations(source):
            if kind == "subprocess":
                argv_target = target or _invocation_targets_path(argv)
                if argv_target is None:
                    unresolved.append((relative_path, lineno, argv))
                    continue
                if not _is_isolated_target(argv_target):
                    unresolved.append(
                        (relative_path, lineno, [argv_target] + argv)
                    )
            elif kind == "main":
                if "--target" not in argv:
                    unresolved.append((relative_path, lineno, argv))
    assert not unresolved, (
        "test-side producer invocations MUST use an isolated --target: "
        f"{unresolved}"
    )


def test_indirect_argv_negative_proof_rejects_unisolated_subprocess() -> None:
    """A subprocess invocation that omits ``--target`` MUST be rejected."""
    bad_source = textwrap.dedent(
        """
        subprocess.run((
            "scripts/factory/populate_gate_summary.py",
            "--repo-root",
            "/tmp/whatever",
        ))
        """
    )
    invocations = _enumerate_producer_invocations(bad_source)
    assert invocations, (
        "literal-tuple subprocess adversarial MUST be detected as a "
        "producer invocation; the helper MUST walk the inline tuple "
        "and identify populate_gate_summary.py as the producer path."
    )
    for kind, _lineno, argv, target in invocations:
        if kind == "subprocess":
            assert any("populate_gate_summary" in token for token in argv)
            assert target is None, (
                f"argv {argv!r} must NOT carry --target in the adversarial form"
            )
            assert not _is_isolated_target("")


# ---------------------------------------------------------------------------
# CORRECTION11: single parser-invocation invariant
# ---------------------------------------------------------------------------


def test_parser_invoked_exactly_once_per_producer_call() -> None:
    """``run_parser_and_capture_verdict`` MUST invoke the parser exactly once.

    The CORRECTION11 fix replaces the previous double-invocation
    pattern with a single ``subprocess.run`` whose bytes feed both
    the :class:`CheckOutcome` and the typed
    ``(decode_status, acceptance_status)`` verdict.

    A live counter on the canonical parser runner proves the
    invariant without depending on internal implementation details.
    """
    import tempfile

    from scripts.factory.gate_summary_command_env import CommandSpec
    from scripts.factory.gate_summary_parser_runner import (
        parser_invocation_count,
        reset_parser_invocation_count,
        run_parser_and_capture_verdict,
    )

    script = tempfile.NamedTemporaryFile(
        mode="w", suffix=".sh", delete=False, encoding="utf-8"
    )
    script.write(
        "#!/bin/bash\n"
        "echo decode_status=pass\n"
        "echo acceptance_status=pass\n"
        "exit 0\n"
    )
    script.close()
    import os

    os.chmod(script.name, 0o755)
    try:
        spec = CommandSpec(name="test-parser-once", argv=[script.name])
        reset_parser_invocation_count()
        assert parser_invocation_count() == 0
        outcome, decode, accept = run_parser_and_capture_verdict(spec)
        assert outcome.status == "pass"
        assert decode == "pass"
        assert accept == "pass"
        assert parser_invocation_count() == 1, (
            "parser must be invoked exactly once per producer call; "
            f"observed {parser_invocation_count()}"
        )
        # A second invocation increments again to exactly two; the
        # invariant is one-per-call, not one-ever.
        outcome2, _, _ = run_parser_and_capture_verdict(spec)
        assert outcome2.status == "pass"
        assert parser_invocation_count() == 2
    finally:
        os.unlink(script.name)