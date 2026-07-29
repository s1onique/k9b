"""Fail-closed producer + path-validation tests for the validation attestation.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION06:

The writer (:func:`write_validation_attestation`) MUST fail closed:

* target outside ``repo_root`` -- raised;
* non-regular file / missing file -- raised;
* caller-supplied SHA mismatch against actual bytes -- raised.

The portable-path helpers reject host-prefixed paths
(``/Users/``, ``/home/runner/``, etc.), every Windows drive
letter (``PureWindowsPath``), UNC anchors, ``..`` traversal,
empty segments, and standalone ``.`` segments. They never
substitute a fallback path.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.factory.gate_summary_validation_attestation import (  # noqa: E402
    _AttestationError,
    _is_windows_shaped,
    _validate_portable_posix_path,
    resolve_validated_path,
    write_validation_attestation,
)

# ---------------------------------------------------------------------------
# Bounded path-prefix rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prefix",
    ["/Users/", "/home/runner/", "/home/circleci/", "/root/", "/private/"],
)
def test_forbidden_absolute_prefixes_are_rejected(prefix: str) -> None:
    with pytest.raises(_AttestationError):
        _validate_portable_posix_path(prefix + "some/where")


def test_bare_posix_absolute_path_is_rejected() -> None:
    with pytest.raises(_AttestationError):
        _validate_portable_posix_path("/etc/passwd")


def test_empty_or_invalid_path_is_rejected() -> None:
    for bad in ("", None, 123):
        with pytest.raises(_AttestationError):
            _validate_portable_posix_path(bad)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Flavour-aware path rejection (PureWindowsPath)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("letter", ["C", "D", "E", "Z", "c", "d", "e", "z"])
def test_any_windows_drive_letter_is_rejected(letter: str) -> None:
    candidate = f"{letter}:\\secrets\\gate-summary.json"
    assert _is_windows_shaped(candidate) is True
    with pytest.raises(_AttestationError):
        _validate_portable_posix_path(candidate)


def test_windows_unc_anchor_is_rejected() -> None:
    candidate = "\\\\fileserver\\share\\gate-summary.json"
    assert _is_windows_shaped(candidate) is True
    with pytest.raises(_AttestationError):
        _validate_portable_posix_path(candidate)


def test_posix_path_with_no_windows_shape_is_accepted() -> None:
    _validate_portable_posix_path(".factory/gate-summary.json")


def test_backslash_separator_is_rejected() -> None:
    with pytest.raises(_AttestationError):
        _validate_portable_posix_path("secrets\\gate-summary.json")


def test_dot_segment_is_rejected() -> None:
    with pytest.raises(_AttestationError):
        _validate_portable_posix_path("./.factory/gate-summary.json")


def test_empty_segment_is_rejected() -> None:
    with pytest.raises(_AttestationError):
        _validate_portable_posix_path(".factory//gate-summary.json")


def test_control_characters_are_rejected() -> None:
    with pytest.raises(_AttestationError):
        _validate_portable_posix_path(".factory/gate-summary\x00.json")


# ---------------------------------------------------------------------------
# resolve_validated_path path safety
# ---------------------------------------------------------------------------


def test_portable_relative_path_is_accepted(tmp_path: Path) -> None:
    factory = tmp_path / ".factory"
    factory.mkdir()
    target = factory / "gate-summary.json"
    target.write_text("{}", encoding="utf-8")
    resolved = resolve_validated_path(
        repo_root=tmp_path, validated_path=".factory/gate-summary.json"
    )
    assert resolved == target.resolve()


def test_macos_absolute_path_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(_AttestationError):
        resolve_validated_path(
            repo_root=tmp_path,
            validated_path="/Users/dev/proj/.factory/gate-summary.json",
        )


def test_linux_runner_absolute_path_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(_AttestationError):
        resolve_validated_path(
            repo_root=tmp_path,
            validated_path="/home/runner/work/.factory/gate-summary.json",
        )


def test_dotdot_path_traversal_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(_AttestationError):
        resolve_validated_path(
            repo_root=tmp_path,
            validated_path="../escape/.factory/gate-summary.json",
        )


def test_traversal_escapes_repo_root_is_rejected(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "gate-summary.json").write_text("{}", encoding="utf-8")
    with pytest.raises(_AttestationError):
        resolve_validated_path(
            repo_root=repo_root,
            validated_path=f"../{outside.name}/gate-summary.json",
        )


# ---------------------------------------------------------------------------
# Writer fails closed
# ---------------------------------------------------------------------------


def test_write_validation_attestation_rejects_target_outside_repo(
    tmp_path: Path,
) -> None:
    """Writer MUST raise when the target resolves outside repo_root."""
    factory = tmp_path / ".factory"
    factory.mkdir()
    target = factory / "gate-summary.json"
    target.write_text("{}", encoding="utf-8")
    other_repo = tmp_path / "another-repo"
    other_repo.mkdir()
    with pytest.raises(_AttestationError):
        write_validation_attestation(
            repo_root=other_repo,
            target=target,
            parser_command="<test>",
            parser_exit_code=0,
            parser_duration_ms=0,
            decode_status="pass",
            acceptance_status="pass",
        )


def test_write_validation_attestation_rejects_missing_target(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    factory = repo_root / ".factory"
    factory.mkdir()
    missing = factory / "gate-summary.json"
    with pytest.raises(_AttestationError):
        write_validation_attestation(
            repo_root=repo_root,
            target=missing,
            parser_command="<test>",
            parser_exit_code=0,
            parser_duration_ms=0,
            decode_status="pass",
            acceptance_status="pass",
        )


def test_write_validation_attestation_rejects_directory_target(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    target_dir = repo_root / ".factory"
    target_dir.mkdir()
    with pytest.raises(_AttestationError):
        write_validation_attestation(
            repo_root=repo_root,
            target=target_dir,
            parser_command="<test>",
            parser_exit_code=0,
            parser_duration_ms=0,
            decode_status="pass",
            acceptance_status="pass",
        )


def test_write_validation_attestation_rejects_stale_caller_supplied_sha(
    tmp_path: Path,
) -> None:
    """Caller-supplied ``final_sha256`` MUST match the on-disk bytes."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    factory = repo_root / ".factory"
    factory.mkdir()
    target = factory / "gate-summary.json"
    target.write_text("{}", encoding="utf-8")
    wrong_sha = "0" * 64
    assert hashlib.sha256(b"{}").hexdigest() != wrong_sha
    with pytest.raises(_AttestationError):
        write_validation_attestation(
            repo_root=repo_root,
            target=target,
            parser_command="<test>",
            parser_exit_code=0,
            parser_duration_ms=0,
            decode_status="pass",
            acceptance_status="pass",
            final_sha256=wrong_sha,
        )


def test_write_validation_attestation_accepts_consistent_caller_sha(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    factory = repo_root / ".factory"
    factory.mkdir()
    target = factory / "gate-summary.json"
    target.write_text("{}", encoding="utf-8")
    actual_sha = hashlib.sha256(b"{}").hexdigest()
    write_validation_attestation(
        repo_root=repo_root,
        target=target,
        parser_command="<test>",
        parser_exit_code=0,
        parser_duration_ms=0,
        decode_status="pass",
        acceptance_status="pass",
        final_sha256=actual_sha,
    )
    assert (factory / "gate-summary-validation.json").exists()


def test_write_validation_attestation_persists_canonical_attestation(
    tmp_path: Path,
) -> None:
    """The persisted attestation key set is canonical (no
    ``parser_postcondition`` field; precise typed fields)."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    factory = repo_root / ".factory"
    factory.mkdir()
    target = factory / "gate-summary.json"
    target.write_text("{}", encoding="utf-8")
    write_validation_attestation(
        repo_root=repo_root,
        target=target,
        parser_command="<test>",
        parser_exit_code=0,
        parser_duration_ms=0,
        decode_status="pass",
        acceptance_status="pass",
    )
    payload = json.loads(
        (factory / "gate-summary-validation.json").read_text(encoding="utf-8")
    )
    expected = {
        "schema_version",
        "validated_path",
        "validated_sha256",
        "validated_at",
        "parser_identity",
        "parser_command",
        "parser_exit_code",
        "parser_duration_ms",
        "decode_status",
        "acceptance_status",
        "diagnostics",
    }
    assert set(payload.keys()) == expected
