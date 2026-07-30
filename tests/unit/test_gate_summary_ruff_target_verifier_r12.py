"""R12 CORRECTION11 production verifier tests (split).

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION11-
RANGE-BOUND-EVIDENCE-TRUTH-AND-LLM-CAP01:

Split out of the original 680-line
``tests/unit/test_gate_summary_population_changed_paths_manifest_r12.py``
so each focused module stays under the LLM-friendly 500-line cap.

These tests cover the **CORRECTION11 production verifier**
(:func:`scripts.factory.gate_summary_ruff_target_verifier.verify_recorded_ruff_targets`):

* invention of a non-manifest target is rejected;
* duplicate listed targets are rejected;
* omission of a manifest target is rejected;
* malformed grammar (missing ``-m``, wrong subcommand) is rejected;
* non-Python listed targets are rejected;
* absolute listed targets are rejected.

CORRECTION11 also REMOVES the obsolete tautological omission test
(``test_ruff_target_omission_negative_proof``) whose set-arithmetic
assertions did not actually exercise the production verifier.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


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