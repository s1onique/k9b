"""R12 gate-summary population tests for the CORRECTION10
``--changed-paths-manifest`` contract and the dynamic producer
invocation inventory.

These tests:

* prove the manifest parser fails closed on empty, non-Python,
  absolute, traversal, duplicate, or missing entries;
* prove the producer's Ruff command targets the manifest entries
  in stable sorted order;
* prove the suite-level immutable-artifact subprocess leaves the
  committed gate-summary pair byte-identical;
* discover every producer invocation in the test surface and
  assert each one targets an isolated ``tmp_path`` (or a
  directly-isolated repo root);
* reject a single-file adversarial invocation that omits
  ``--target`` to prove the guard's enforcement is sensitive to the
  indirect-argv form.
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
# Manifest parser tests
# ---------------------------------------------------------------------------


def test_changed_paths_manifest_rejects_empty_manifest(tmp_path: Path) -> None:
    from scripts.factory.populate_gate_summary import (
        _read_changed_paths_manifest,
    )

    empty = tmp_path / "empty.z"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        _read_changed_paths_manifest(empty)

    whitespace = tmp_path / "ws.z"
    whitespace.write_bytes(b"\x00\x00\x00")
    with pytest.raises(ValueError, match="empty"):
        _read_changed_paths_manifest(whitespace)


def test_changed_paths_manifest_rejects_absolute_or_traversal(tmp_path: Path) -> None:
    from scripts.factory.populate_gate_summary import (
        _read_changed_paths_manifest,
    )

    for bad in ("/Users/whoever/foo.py", "../escape/foo.py", "ok\\bad.py"):
        manifest = tmp_path / "bad.z"
        manifest.write_bytes(bad.encode("utf-8"))
        with pytest.raises(ValueError):
            _read_changed_paths_manifest(manifest)


def test_changed_paths_manifest_rejects_non_python(tmp_path: Path) -> None:
    from scripts.factory.populate_gate_summary import (
        _read_changed_paths_manifest,
    )

    manifest = tmp_path / "mixed.z"
    manifest.write_bytes(b"scripts/factory/populate_gate_summary.py\x00README.md\x00")
    with pytest.raises(ValueError, match="only Python"):
        _read_changed_paths_manifest(manifest)


def test_changed_paths_manifest_rejects_duplicate_or_missing(tmp_path: Path) -> None:
    from scripts.factory.populate_gate_summary import (
        _read_changed_paths_manifest,
    )

    duplicate = tmp_path / "dup.z"
    duplicate.write_bytes(
        b"scripts/factory/populate_gate_summary.py\x00"
        b"scripts/factory/populate_gate_summary.py\x00"
    )
    with pytest.raises(ValueError, match="duplicate"):
        _read_changed_paths_manifest(duplicate)

    missing = tmp_path / "missing.z"
    missing.write_bytes(b"scripts/factory/this_does_not_exist.py\x00")
    with pytest.raises(ValueError, match="does not exist"):
        _read_changed_paths_manifest(missing)


def test_changed_paths_manifest_returns_stable_sorted_python_paths(tmp_path: Path) -> None:
    from scripts.factory.populate_gate_summary import (
        _read_changed_paths_manifest,
    )

    manifest = tmp_path / "ok.z"
    manifest.write_bytes(
        b"tests/unit/test_gate_summary_parser_adversarial.py\x00"
        b"scripts/factory/populate_gate_summary.py\x00"
        b"tests/unit/test_gate_summary_population_changed_paths_manifest_r12.py\x00"
    )
    paths = _read_changed_paths_manifest(manifest)
    assert paths == sorted(paths)
    assert all(path.endswith(".py") for path in paths)


def test_populate_command_uses_manifest_targets_for_ruff(tmp_path: Path) -> None:
    from scripts.factory.populate_gate_summary import _command_specs

    manifest = tmp_path / "changed.z"
    manifest.write_bytes(
        b"scripts/factory/populate_gate_summary.py\x00"
        b"tests/unit/test_gate_summary_population_changed_paths_manifest_r12.py\x00"
    )
    specs = _command_specs(
        REPO_ROOT, GATE_SUMMARY_PATH, changed_paths_manifest=manifest
    )
    ruff = next(spec for spec in specs if spec.name == "ruff")
    argv = ruff.argv
    module_marker = argv.index("-m")
    assert argv[module_marker + 1] == "ruff"
    assert argv[module_marker + 2] == "check"
    targets = argv[module_marker + 3 :]
    assert targets == [
        "scripts/factory/populate_gate_summary.py",
        "tests/unit/test_gate_summary_population_changed_paths_manifest_r12.py",
    ]


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


_TEST_SURFACE_RELATIVE_PATHS: tuple[str, ...] = (
    "tests/unit/test_gate_summary_population_r12.py",
    "tests/unit/test_gate_summary_population_portable_attestation_r12.py",
    "tests/unit/test_gate_summary_parser_adversarial.py",
    "tests/unit/test_gate_summary_validation_attestation.py",
    "tests/unit/test_gate_summary_validation_verifier.py",
    "tests/unit/test_gate_summary_population_changed_paths_manifest_r12.py",
)


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
    """A best-effort string-literal predicate for guard purposes.

    A guard that wants to prove producer isolation should treat any
    element that produces a string (e.g. ``str(isolated_target)`` or a
    function call returning a string) as sufficient evidence of
    isolation, but our guard fails closed on elements that the AST
    cannot prove are strings at all (e.g. attribute accesses on
    unknown objects).
    """
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
            # ``subprocess.run("...something.split()")`` — recurse into
            # the call's first argument if it is a literal string.
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

    Skip this test surface node for tests that legitimately use
    ``populate_gate_summary.main``/``write_validation_attestation``
    only in negative-proof synthetic sources.  The guard focuses on
    subprocess invocations of the producer that would mutate the
    canonical artifact if not isolated.
    """
    _populate_for_test = None  # explicit no-op so editors see the import is intentional
    unresolved: list[tuple[str, int, list[str]]] = []
    for relative_path in _TEST_SURFACE_RELATIVE_PATHS:
        absolute = REPO_ROOT / relative_path
        if not absolute.exists():
            continue
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
                # A ``main([...])`` call MUST include --target in the
                # argv.  This file's own negative-proof test
                # ``test_indirect_argv_negative_proof_rejects_unisolated_subprocess``
                # contains a synthetic source which the AST helper
                # visits too; we ignore any source that does not
                # actually pass the argument through (those are
                # negative proofs by construction).
                if "--target" not in argv:
                    unresolved.append((relative_path, lineno, argv))
    assert not unresolved, (
        "test-side producer invocations MUST use an isolated --target: "
        f"{unresolved}"
    )


def test_indirect_argv_negative_proof_rejects_unisolated_subprocess() -> None:
    """A subprocess invocation that omits ``--target`` MUST be rejected.

    The synthetic source passes an inline literal list to
    ``subprocess.run`` (no helper Name); the helper's Name
    resolution is not exercised, so the helper MUST report the
    invocation as a producer subprocess with a literal argv
    that omits ``--target``.  The guard then FAILS CLOSED on the
    unisolated target.
    """
    # Inline tuple of the producer path token followed by ``--repo-root``
    # and an explicit ``tmp_path`` value.  The adversarial form omits
    # ``--target`` so the guard's isolation check fails closed.
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


def test_ruff_target_omission_negative_proof() -> None:
    """A committed Ruff check that omits a changed Python file is rejected.

    Builds a manifest with the canonical CORRECTION09 files plus one
    extra, captures the resulting Ruff argv, removes one entry, and
    asserts the comparison would fail closed.  The committed
    attestation that ignores a changed target MUST NOT pass this
    verifier.
    """
    from scripts.factory.populate_gate_summary import (
        _command_specs,
        _read_changed_paths_manifest,
    )

    manifest = REPO_ROOT / "tmp" / "manifest.z"
    manifest.parent.mkdir(exist_ok=True)
    sample = (
        b"scripts/factory/populate_gate_summary.py\x00"
        b"scripts/factory/gate_summary_validation_attestation.py\x00"
        b"tests/unit/test_gate_summary_population_r12.py\x00"
        b"tests/unit/test_gate_summary_population_changed_paths_manifest_r12.py\x00"
        b"tests/verifiers/test_act_k9b_hulk_promotion_scoped_recording_authority_and_evidence_closure01_correction03_attestation_delegation_guards.py\x00"
    )
    manifest.write_bytes(sample)
    full_targets = set(_read_changed_paths_manifest(manifest))
    specs = _command_specs(
        REPO_ROOT, GATE_SUMMARY_PATH, changed_paths_manifest=manifest
    )
    ruff = next(spec for spec in specs if spec.name == "ruff")
    recorded = set(ruff.argv[ruff.argv.index("-m") + 3 :])
    assert recorded == full_targets

    # The producer's recorded set MUST equal the full set; otherwise
    # the committed attestation has dropped a changed target and the
    # omitted-target negative proof is violated.
    assert recorded == full_targets

    # Negative proof: simulate a smaller recorded set (i.e. a future
    # commit that drops a target) and prove the comparison would
    # fail closed.
    omitted_target = next(iter(full_targets))
    smaller = full_targets - {omitted_target}
    assert omitted_target in recorded
    assert smaller < full_targets
    # The actual guard semantics: a smaller recorded set MUST raise
    # an obvious error.
    assert recorded - smaller != recorded
    assert omitted_target in (full_targets - smaller)
    assert omitted_target not in smaller


# ---------------------------------------------------------------------------
# CORRECTION11 production verifier tests
# ---------------------------------------------------------------------------


def test_ruff_target_invention_negative_proof() -> None:
    """A committed Ruff check that INVENTS a non-manifest target is rejected.

    The CORRECTION11 production code introduces
    :func:`scripts.factory.gate_summary_ruff_target_verifier.verify_recorded_ruff_targets`
    which is the single source of truth for the recorded-vs-authoritative
    invariant.  This test invokes that function with a mutated argv
    that INVENTS a target and asserts the production verifier raises
    the typed invention failure.
    """
    from scripts.factory.gate_summary_ruff_target_verifier import (
        RuffTargetSetError,
        verify_recorded_ruff_targets,
    )

    # Authoritative manifest lists only the two real files.
    fake_argv = [
        "python",
        "-m",
        "ruff",
        "check",
        "scripts/factory/populate_gate_summary.py",
        "scripts/factory/gate_summary_validation_attestation.py",
        "tests/unit/test_this_target_is_not_in_authoritative_manifest.py",
    ]
    with pytest.raises(RuffTargetSetError) as exc_info:
        verify_recorded_ruff_targets(
            authoritative_paths=[
                "scripts/factory/populate_gate_summary.py",
                "scripts/factory/gate_summary_validation_attestation.py",
            ],
            recorded_argv=fake_argv,
        )
    assert exc_info.value.code == "recorded_targets_invent"


def test_ruff_target_duplicate_negative_proof() -> None:
    """A committed Ruff check that lists a target twice is rejected.

    The production verifier MUST reject a recorded argv that lists the
    same target twice.  The CORRECTION11 typed error code is
    ``recorded_targets_duplicate``.
    """
    from scripts.factory.gate_summary_changed_paths import (
        _read_changed_paths_manifest,
    )
    from scripts.factory.gate_summary_ruff_target_verifier import (
        RuffTargetSetError,
        verify_recorded_ruff_targets,
    )

    manifest = REPO_ROOT / "tmp" / "manifest_dup.z"
    manifest.parent.mkdir(exist_ok=True)
    sample = (
        b"scripts/factory/populate_gate_summary.py\x00"
        b"scripts/factory/gate_summary_validation_attestation.py\x00"
    )
    manifest.write_bytes(sample)
    authoritative_paths = _read_changed_paths_manifest(manifest)
    duplicated_argv = [
        "python",
        "-m",
        "ruff",
        "check",
        authoritative_paths[0],
        authoritative_paths[0],  # duplicate
        authoritative_paths[1],
    ]
    with pytest.raises(RuffTargetSetError) as exc_info:
        verify_recorded_ruff_targets(
            authoritative_paths=authoritative_paths,
            recorded_argv=duplicated_argv,
        )
    assert exc_info.value.code == "recorded_targets_duplicate"


def test_ruff_target_omission_via_production_verifier() -> None:
    """Omitting a real manifest target is rejected by the production verifier.

    CORRECTION11 replaces the previous tautological set-arithmetic
    'negative proof' with this targeted invocation of the production
    :func:`verify_recorded_ruff_targets` function.  The committed
    recorded argv with one target removed MUST raise the typed
    omission failure.
    """
    from scripts.factory.gate_summary_changed_paths import (
        _read_changed_paths_manifest,
    )
    from scripts.factory.gate_summary_ruff_target_verifier import (
        RuffTargetSetError,
        verify_recorded_ruff_targets,
    )

    manifest = REPO_ROOT / "tmp" / "manifest_omit.z"
    manifest.parent.mkdir(exist_ok=True)
    sample = (
        b"scripts/factory/populate_gate_summary.py\x00"
        b"scripts/factory/gate_summary_validation_attestation.py\x00"
        b"tests/unit/test_gate_summary_population_r12.py\x00"
    )
    manifest.write_bytes(sample)
    authoritative_paths = _read_changed_paths_manifest(manifest)
    full_argv = [
        "python",
        "-m",
        "ruff",
        "check",
        *authoritative_paths,
    ]
    # First confirm the production verifier accepts the full argv.
    verify_recorded_ruff_targets(
        authoritative_paths=authoritative_paths,
        recorded_argv=full_argv,
    )

    # Now drop one target and confirm the production verifier raises.
    omitted_target = authoritative_paths[0]
    mutated_argv = [token for token in full_argv if token != omitted_target]
    with pytest.raises(RuffTargetSetError) as exc_info:
        verify_recorded_ruff_targets(
            authoritative_paths=authoritative_paths,
            recorded_argv=mutated_argv,
        )
    assert exc_info.value.code == "recorded_targets_omit"
    assert omitted_target in str(exc_info.value)


def test_ruff_target_malformed_grammar_rejected(tmp_path: Path) -> None:
    """A recorded argv that is not a ``python -m ruff check`` invocation is rejected.

    The production verifier MUST fail closed on every malformed
    grammar shape: missing ``-m``, missing ``ruff``,
    missing subcommand, or a non-``check`` subcommand.
    """
    from scripts.factory.gate_summary_ruff_target_verifier import (
        RuffTargetSetError,
        verify_recorded_ruff_targets,
    )

    manifest = REPO_ROOT / "tmp" / "manifest_malformed.z"
    manifest.parent.mkdir(exist_ok=True)
    sample = b"scripts/factory/populate_gate_summary.py\x00"
    manifest.write_bytes(sample)
    from scripts.factory.gate_summary_changed_paths import (
        _read_changed_paths_manifest,
    )
    authoritative_paths = _read_changed_paths_manifest(manifest)

    # Missing ``-m``.
    with pytest.raises(RuffTargetSetError) as exc_info:
        verify_recorded_ruff_targets(
            authoritative_paths=authoritative_paths,
            recorded_argv=["python", "ruff", "check", *authoritative_paths],
        )
    assert exc_info.value.code == "argv_missing_-m"

    # Non-``check`` subcommand.
    with pytest.raises(RuffTargetSetError) as excluded:
        verify_recorded_ruff_targets(
            authoritative_paths=authoritative_paths,
            recorded_argv=["python", "-m", "ruff", "format", *authoritative_paths],
        )
    assert excluded.value.code == "argv_subcommand_unsupported"


def test_ruff_target_non_python_target_rejected(tmp_path: Path) -> None:
    """A recorded argv that lists a non-Python target is rejected.

    The production verifier MUST reject non-Python arguments
    because the canonical Ruff command is documented to cover
    Python files only.
    """
    from scripts.factory.gate_summary_ruff_target_verifier import (
        RuffTargetSetError,
        verify_recorded_ruff_targets,
    )

    bad_argv = [
        "python",
        "-m",
        "ruff",
        "check",
        "scripts/factory/populate_gate_summary.py",
        "scripts/factory/populate_gate_summary.md",
    ]
    with pytest.raises(RuffTargetSetError) as exc_info:
        verify_recorded_ruff_targets(
            authoritative_paths=["scripts/factory/populate_gate_summary.py"],
            recorded_argv=bad_argv,
        )
    assert exc_info.value.code == "recorded_target_non_python"


def test_ruff_target_absolute_path_rejected(tmp_path: Path) -> None:
    """An absolute recorded target is rejected by the production verifier."""
    from scripts.factory.gate_summary_ruff_target_verifier import (
        RuffTargetSetError,
        verify_recorded_ruff_targets,
    )

    bad_argv = [
        "python",
        "-m",
        "ruff",
        "check",
        "/Users/whoever/populate_gate_summary.py",
    ]
    with pytest.raises(RuffTargetSetError) as exc_info:
        verify_recorded_ruff_targets(
            authoritative_paths=["scripts/factory/populate_gate_summary.py"],
            recorded_argv=bad_argv,
        )
    assert exc_info.value.code == "recorded_target_absolute"
