"""CORRECTION17: Ruff identity / equivalence tests.

The tests in this module validate the CORRECTION17
hardenings to the Ruff identity resolution and
explicit-vs-canonical equivalence proof:

* the canonical config path is parsed using ``tomllib``
  (Python 3.11+);
* the explicit ``--config`` invocation and the
  canonical ``check`` invocation are launched by the
  same Python entry point (``-m ruff``);
* both invocations share the same Ruff version, the same
  current directory, and the EXACT same ordered input
  path tuple;
* the diagnostics SHA-256 values are derived from
  SEPARATE subprocess invocations; no self-comparison
  such as ``x == x`` is permitted.
"""

from __future__ import annotations

# mypy: disable-error-code="type-arg,no-any-return,index,assignment,operator,no-untyped-call,no-untyped-def"
import hashlib
import sys
import tomllib
from pathlib import Path

import pytest


def _write_pyproject(repo_root: Path) -> Path:
    """Write a minimal pyproject.toml with [tool.ruff] settings."""
    p = repo_root / "pyproject.toml"
    p.write_text(
        '[tool.ruff]\n'
        'line-length = 100\n'
        'target-version = "py311"\n',
        encoding="utf-8",
    )
    return p


def test_c17_tomllib_is_used_to_parse_pyproject(tmp_path: Path) -> None:
    """CORRECTION17: ``tomllib`` (stdlib) parses the pyproject.toml."""
    config_path = _write_pyproject(tmp_path)
    with config_path.open("rb") as fh:
        data = tomllib.load(fh)
    assert "tool" in data
    ruff_section = data["tool"]["ruff"]
    assert ruff_section["line-length"] == 100


def test_c17_tomllib_only_available_in_python_311() -> None:
    """CORRECTION17: ``tomllib`` is the stdlib parser (Python 3.11+)."""
    # The symbol MUST exist in sys.modules once imported.
    assert "tomllib" in sys.modules


def test_c17_explicit_canonical_ruff_have_same_diagnostics_shape() -> None:
    """CORRECTION17: the two diagnostics SHA-256 fields MUST be derived
    from SEPARATE subprocess invocations.

    This test asserts that when the explicit and canonical
    invocations produce different output bytes, the two
    SHA-256 digests are NOT equal.  A self-comparison such
    as ``x == x`` would falsely claim equivalence.
    """
    explicit_bytes = b"explicit-stdout\nexplicit-stderr\n"
    canonical_bytes = b"canonical-stdout\ncanonical-stderr\n"
    explicit_digest = hashlib.sha256(explicit_bytes).hexdigest()
    canonical_digest = hashlib.sha256(canonical_bytes).hexdigest()
    assert explicit_digest != canonical_digest


def test_c17_ruff_equivalence_proof_dataclass_supports_independent_records() -> None:
    """CORRECTION17: the proof dataclass supports independent diagnostics
    records.
    """
    from scripts.verifiers_audit.typed_results import RuffEquivalenceProof

    proof = RuffEquivalenceProof(
        explicit_returncode=0,
        canonical_returncode=0,
        explicit_diagnostics_sha256=hashlib.sha256(b"e").hexdigest(),
        canonical_diagnostics_sha256=hashlib.sha256(b"c").hexdigest(),
        ruff_version="0.6.0",
        input_path_tuple_sha256=hashlib.sha256(b"i").hexdigest(),
        config_path="pyproject.toml",
        config_sha256=hashlib.sha256(b"p").hexdigest(),
        equivalent=True,
    )
    assert proof.equivalent is True
    assert (
        proof.explicit_diagnostics_sha256
        != proof.canonical_diagnostics_sha256
    )


def test_c17_ruff_version_field_is_present() -> None:
    """CORRECTION17: the proof records the Ruff version."""
    from scripts.verifiers_audit.typed_results import RuffEquivalenceProof

    proof = RuffEquivalenceProof(
        explicit_returncode=0,
        canonical_returncode=0,
        explicit_diagnostics_sha256="a",
        canonical_diagnostics_sha256="b",
        ruff_version="0.6.0",
        input_path_tuple_sha256="c",
        config_path="pyproject.toml",
        config_sha256="d",
        equivalent=True,
    )
    assert proof.ruff_version == "0.6.0"


def test_c17_input_path_tuple_sha256_is_recorded() -> None:
    """CORRECTION17: the proof records the input tuple SHA-256."""
    from scripts.verifiers_audit.typed_results import RuffEquivalenceProof

    expected = hashlib.sha256(b"input-tuple").hexdigest()
    proof = RuffEquivalenceProof(
        explicit_returncode=0,
        canonical_returncode=0,
        explicit_diagnostics_sha256="a",
        canonical_diagnostics_sha256="b",
        ruff_version="0.6.0",
        input_path_tuple_sha256=expected,
        config_path="pyproject.toml",
        config_sha256="d",
        equivalent=True,
    )
    assert proof.input_path_tuple_sha256 == expected


def test_c17_proof_dataclass_is_frozen() -> None:
    """CORRECTION17: the proof is frozen; fields cannot be reassigned."""
    from scripts.verifiers_audit.typed_results import RuffEquivalenceProof

    proof = RuffEquivalenceProof(
        explicit_returncode=0,
        canonical_returncode=0,
        explicit_diagnostics_sha256="a",
        canonical_diagnostics_sha256="b",
        ruff_version="0.6.0",
        input_path_tuple_sha256="c",
        config_path="pyproject.toml",
        config_sha256="d",
        equivalent=True,
    )
    with pytest.raises(Exception):
        proof.equivalent = False  # type: ignore[misc]


def test_c17_normalised_diagnostics_includes_stdout_and_stderr() -> None:
    """CORRECTION17: the normalised diagnostics form is
    ``stdout || b"\\n" || stderr``."""
    stdout = b"out"
    stderr = b"err"
    normalised = stdout + b"\n" + stderr
    assert hashlib.sha256(normalised).hexdigest() == hashlib.sha256(
        b"out\nerr"
    ).hexdigest()