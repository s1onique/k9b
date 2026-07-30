"""Runtime verifier tests for the portable validation attestation.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION06:

The verifier (:func:`verify_validation_attestation`) MUST raise
``_AttestationError`` for:

* missing sibling attestation or resolved validated artifact;
* non-regular files at either path;
* SHA drift between attested and on-disk bytes;
* non-portable ``validated_path`` shapes (absolute /
  Windows / ``..`` / empty);
* non-hex SHA / non-``{pass,fail}`` typed status fields.

Successful returns NEVER carry a ``sha_matches=False`` flag;
that field was removed entirely in CORRECTION06.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.factory.gate_summary_validation_attestation import (  # noqa: E402
    _AttestationError,
    verify_validation_attestation,
)


def _build_repo_with_factory_artifact(tmp_path: Path) -> tuple[Path, Path]:
    factory = tmp_path / ".factory"
    factory.mkdir()
    artifact = factory / "gate-summary.json"
    artifact.write_text('{"schema_version": 1}', encoding="utf-8")
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    payload = {
        "schema_version": 1,
        "validated_path": ".factory/gate-summary.json",
        "validated_sha256": sha,
        "validated_at": "2026-07-30T00:00:00+00:00",
        "parser_identity": "scripts/factory/parse_gate_summary.py",
        "parser_command": "<test>",
        "parser_exit_code": 0,
        "parser_duration_ms": 0,
        "decode_status": "pass",
        "acceptance_status": "pass",
        "diagnostics": {},
    }
    attestation = factory / "gate-summary-validation.json"
    attestation.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return tmp_path, sha


def _produce_attestation_with_path(
    tmp_path: Path, validated_path_value: str
) -> tuple[Path, Path]:
    factory = tmp_path / ".factory"
    factory.mkdir()
    artifact = factory / "gate-summary.json"
    artifact.write_text("{}", encoding="utf-8")
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    payload = {
        "schema_version": 1,
        "validated_path": validated_path_value,
        "validated_sha256": sha,
        "validated_at": "2026-07-30T00:00:00+00:00",
        "parser_identity": "scripts/factory/parse_gate_summary.py",
        "parser_command": "<test>",
        "parser_exit_code": 0,
        "parser_duration_ms": 0,
        "decode_status": "pass",
        "acceptance_status": "pass",
        "diagnostics": {},
    }
    attestation = factory / "gate-summary-validation.json"
    attestation.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return tmp_path, sha


def test_verify_validation_attestation_accepts_portable_relative_path(
    tmp_path: Path,
) -> None:
    repo_root, _ = _build_repo_with_factory_artifact(tmp_path)
    result = verify_validation_attestation(
        repo_root=repo_root,
        attestation_path=repo_root / ".factory" / "gate-summary-validation.json",
    )
    assert result.decode_status == "pass"
    assert result.acceptance_status == "pass"
    assert result.parser_identity == "scripts/factory/parse_gate_summary.py"
    assert result.portable_validated_path == ".factory/gate-summary.json"


def test_verify_validation_attestation_rejects_missing_validated_artifact(
    tmp_path: Path,
) -> None:
    repo_root, _ = _build_repo_with_factory_artifact(tmp_path)
    (repo_root / ".factory" / "gate-summary.json").unlink()
    with pytest.raises(_AttestationError) as exc:
        verify_validation_attestation(
            repo_root=repo_root,
            attestation_path=repo_root / ".factory" / "gate-summary-validation.json",
        )
    assert "missing" in str(exc.value).lower()


def test_verify_validation_attestation_rejects_sha_mismatch(
    tmp_path: Path,
) -> None:
    repo_root, _ = _build_repo_with_factory_artifact(tmp_path)
    target = repo_root / ".factory" / "gate-summary.json"
    target.write_text('{"mutated": true}', encoding="utf-8")
    with pytest.raises(_AttestationError) as exc:
        verify_validation_attestation(
            repo_root=repo_root,
            attestation_path=repo_root / ".factory" / "gate-summary-validation.json",
        )
    assert "SHA mismatch" in str(exc.value)


def test_verify_validation_attestation_rejects_absolute_path(
    tmp_path: Path,
) -> None:
    repo_root, _ = _produce_attestation_with_path(
        tmp_path, "/Users/dev/proj/.factory/gate-summary.json"
    )
    with pytest.raises(_AttestationError):
        verify_validation_attestation(
            repo_root=repo_root,
            attestation_path=repo_root / ".factory" / "gate-summary-validation.json",
        )


def test_verify_validation_attestation_rejects_traversal(
    tmp_path: Path,
) -> None:
    repo_root, _ = _produce_attestation_with_path(
        tmp_path, "../escape/.factory/gate-summary.json"
    )
    with pytest.raises(_AttestationError):
        verify_validation_attestation(
            repo_root=repo_root,
            attestation_path=repo_root / ".factory" / "gate-summary-validation.json",
        )


def test_verify_validation_attestation_rejects_missing_attestation(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".factory").mkdir()
    with pytest.raises(_AttestationError) as exc:
        verify_validation_attestation(
            repo_root=repo_root,
            attestation_path=repo_root / ".factory" / "gate-summary-validation.json",
        )
    assert "missing" in str(exc.value).lower()


def test_verify_validation_attestation_rejects_bad_status_enum(
    tmp_path: Path,
) -> None:
    factory = tmp_path / ".factory"
    factory.mkdir()
    artifact = factory / "gate-summary.json"
    artifact.write_text("{}", encoding="utf-8")
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    payload = {
        "schema_version": 1,
        "validated_path": ".factory/gate-summary.json",
        "validated_sha256": sha,
        "validated_at": "2026-07-30T00:00:00+00:00",
        "parser_identity": "scripts/factory/parse_gate_summary.py",
        "parser_command": "<test>",
        "parser_exit_code": 0,
        "parser_duration_ms": 0,
        "decode_status": "maybe",
        "acceptance_status": "pass",
        "diagnostics": {},
    }
    attestation = factory / "gate-summary-validation.json"
    attestation.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    with pytest.raises(_AttestationError) as exc:
        verify_validation_attestation(
            repo_root=tmp_path, attestation_path=attestation
        )
    assert "decode_status" in str(exc.value)


def test_verify_validation_attestation_rejects_nonhex_sha(
    tmp_path: Path,
) -> None:
    factory = tmp_path / ".factory"
    factory.mkdir()
    artifact = factory / "gate-summary.json"
    artifact.write_text("{}", encoding="utf-8")
    payload = {
        "schema_version": 1,
        "validated_path": ".factory/gate-summary.json",
        "validated_sha256": "not-hex",
        "validated_at": "2026-07-30T00:00:00+00:00",
        "parser_identity": "scripts/factory/parse_gate_summary.py",
        "parser_command": "<test>",
        "parser_exit_code": 0,
        "parser_duration_ms": 0,
        "decode_status": "pass",
        "acceptance_status": "pass",
        "diagnostics": {},
    }
    attestation = factory / "gate-summary-validation.json"
    attestation.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    with pytest.raises(_AttestationError) as exc:
        verify_validation_attestation(
            repo_root=tmp_path, attestation_path=attestation
        )
    assert "validated_sha256" in str(exc.value)
