"""Producer + runtime verifier for the gate-summary validation attestation.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION06
-WORKFLOW-SYNTAX-AND-ATTESTATION-FAIL-CLOSED01:

This module owns BOTH halves of the portable validation-attestation
contract. They live together because the producer and the verifier
must agree on every constant (event names, field names, SHA order)
for the contract to be auditable in CI.

* :func:`write_validation_attestation` is the producer entry point
  invoked by :mod:`scripts.factory.populate_gate_summary` after it
  finishes writing the canonical artifact. The producer computes
  the SHA directly from the artifact bytes (no caller-supplied
  authority), rejects targets that resolve outside the repository
  root, and rejects directory/non-regular-file targets so the
  attestation NEVER binds to a non-existent or wrong-location
  artifact.

* :func:`verify_validation_attestation` is the runtime verifier.
  It re-resolves the portable ``validated_path`` against the
  runtime runner's ``repo_root``, fails closed on missing or
  non-regular files, and raises ``_AttestationError`` on any
  undetectable drift between the attested bytes and the bytes on
  disk. A successful return is ALWAYS accompanied by a verifiable
  SHA match.

* :func:`resolve_validated_path` rejects every host-prefixed path
  (``/Users/...``, ``/home/runner/...``, ``/private/...``,
  Windows drive prefixes ``C:\\..Z:\\``, and UNC roots
  ``\\\\server\\share\\``) at the path boundary using
  :class:`pathlib.PureWindowsPath`. The persisted
  ``validated_path`` contract is POSIX repository-relative: no
  leading slash, no backslash, no Windows drive / UNC anchor, no
  ``.`` or ``..`` segments, no empty components.

The verifier never auto-fetches artefacts from a remote source;
the attestation is always resolved relative to the
caller-supplied ``repo_root``.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, cast

# ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION06:
# Forbidden absolute-path prefixes that MUST be rejected at the
# runtime verifier so committed attestations never leak host paths.
FORBIDDEN_ABSOLUTE_PREFIXES: tuple[str, ...] = (
    "/Users/",       # macOS / developer workstation prefix
    "/home/runner/", # GitHub Actions Linux runner prefix
    "/home/circleci/",
    "/root/",
    "/private/",     # macOS /private/var/.../pytest-of-* temp prefix
)

# Bounded 64-char lowercase hex SHA-256 fingerprint.
_SHA256_HEX_LENGTH = 64
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ValidationAttestationResult:
    """Structured verification result for a sibling attestation.

    The ``sha_matches`` field is ALWAYS True on a returned
    instance. The runtime verifier raises ``_AttestationError``
    on any failure; it NEVER returns a result with
    ``sha_matches=False``.
    """

    attestation_path: Path
    validated_path: Path
    validated_sha256: str
    parser_identity: str
    decode_status: str
    acceptance_status: str
    portable_validated_path: str


class _AttestationError(ValueError):
    """Bounded, machine-parseable exception type for verifier failures."""


def _is_windows_shaped(value: str) -> bool:
    """Return True when ``value`` carries a Windows drive or UNC root.

    ``PureWindowsPath`` recognises drive letters across the entire
    alphabet (``C:\\`` through ``Z:\\``) and UNC anchors of the
    form ``\\\\server\\share``. Using the canonical parser avoids
    listing drive letters by hand and catches UNC shapes that POSIX
    runners can misinterpret as network paths.
    """
    if not value:
        return False
    # Treat the value as a Windows path regardless of slashes.
    normalised = value.replace("/", "\\")
    win_path = PureWindowsPath(normalised)
    return bool(win_path.drive) or bool(win_path.root)


def _validate_portable_posix_path(value: str) -> None:
    """Reject every shape that is NOT a portable POSIX
    repository-relative path.

    The persisted contract is:

    * non-empty;
    * no leading slash (POSIX absolute);
    * no backslash (Windows separator leaking in);
    * no Windows drive letter or UNC root (``PureWindowsPath``
      parses those even on POSIX runners);
    * no ``.`` or ``..`` segment (path traversal);
    * non-empty components;
    * every character must be printable POSIX-friendly (no NUL,
      no control bytes);
    """
    if not isinstance(value, str) or not value:
        raise _AttestationError(
            "validated_path MUST be a non-empty string"
        )
    if value.startswith("/") or value.startswith("\\"):
        raise _AttestationError(
            f"validated_path MUST be portable (repository-relative); "
            f"got absolute path {value!r}"
        )
    if "\\" in value:
        raise _AttestationError(
            f"validated_path MUST use POSIX separators only; "
            f"backslash found in {value!r}"
        )
    if any(ord(c) < 0x20 for c in value):
        raise _AttestationError(
            f"validated_path MUST be printable-only; control chars "
            f"found in {value!r}"
        )
    # Reject every Windows shape explicitly (drive letters across the
    # alphabet plus UNC anchors).
    if _is_windows_shaped(value):
        raise _AttestationError(
            f"validated_path MUST be portable (repository-relative); "
            f"Windows-shaped path rejected: {value!r}"
        )
    segments = value.split("/")
    if ".." in segments:
        raise _AttestationError(
            f"validated_path MUST NOT contain '..' path traversal; "
            f"got {value!r}"
        )
    if "" in segments:
        raise _AttestationError(
            f"validated_path MUST NOT contain empty segments; "
            f"got {value!r}"
        )
    if "." in segments:
        raise _AttestationError(
            f"validated_path MUST NOT contain '.' as a standalone "
            f"segment; got {value!r}"
        )
    # Cross-check with PurePosixPath: any segment starting with NUL
    # or similar control bytes is also rejected here.
    pure = PurePosixPath(value)
    if pure.is_absolute():
        raise _AttestationError(
            f"validated_path MUST be relative; got absolute path "
            f"{value!r}"
        )


def portable_parser_command(*, validated_path: str) -> str:
    """Return the stable parser command persisted in an attestation.

    The executed subprocess command may contain absolute interpreter and
    script paths, but committed evidence must remain portable across
    workstations and CI runners.  Validate the repository-relative target
    before rendering it as a shell-safe, POSIX command representation.
    """
    _validate_portable_posix_path(validated_path)
    return shlex.join(
        (
            "python",
            "scripts/factory/parse_gate_summary.py",
            "--target",
            validated_path,
            "--quiet",
        )
    )


def _portable_validated_path(
    *,
    repo_root: Path,
    target: Path,
) -> str:
    """Compute the canonical portable validated_path.

    Fails closed when the target does not resolve under the
    repository root. NEVER substitutes a synthetic fallback --
    substituting would silently bind the attestation to a
    wrong location and defeat the contract.
    """
    repo_root_resolved = repo_root.resolve()
    target_resolved = target.resolve()
    try:
        relative = target_resolved.relative_to(repo_root_resolved)
    except ValueError as exc:
        raise _AttestationError(
            f"validated artifact MUST resolve under repo_root "
            f"{repo_root_resolved}; got {target_resolved}"
        ) from exc
    portable = relative.as_posix()
    _validate_portable_posix_path(portable)
    return portable


def _read_and_hash_target(target: Path) -> bytes:
    """Read the target artifact bytes and SHA-256 them.

    The target MUST be a regular file: directories, missing
    files, and symlinks that resolve to anything but a regular
    file are all rejected.
    """
    try:
        if not target.exists():
            raise _AttestationError(
                f"validated artifact missing at {target}"
            )
        if not target.is_file():
            raise _AttestationError(
                f"validated artifact MUST be a regular file; "
                f"{target} is not a file"
            )
    except OSError as exc:
        raise _AttestationError(
            f"validated artifact not readable at {target}: {exc}"
        ) from exc
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise _AttestationError(
            f"validated artifact not readable at {target}: {exc}"
        ) from exc
    return data


def write_validation_attestation(
    *,
    repo_root: Path,
    target: Path,
    parser_command: str | None,
    parser_exit_code: int | None,
    parser_duration_ms: int,
    decode_status: str,
    acceptance_status: str,
    diagnostics: Mapping[str, Any] | None = None,
    final_sha256: str | None = None,
) -> Path:
    """Persist the sibling ``gate-summary-validation.json`` attestation.

    ``validated_path`` written into the attestation is the
    canonical POSIX repository-relative location of ``target``
    under ``repo_root``. Every shape that would bind the
    attestation to a wrong location is rejected at this seam:

    * ``target`` not under ``repo_root`` -- raised;
    * ``target`` not a regular file -- raised;
    * ``target`` missing -- raised;
    * ``target`` unreadable -- raised;
    * ``final_sha256`` mismatch against the actual bytes on disk
      (when caller supplies one for double-authority cross-check)
      -- raised.

    ``final_sha256`` defaults to ``None``: the canonical producer
    lets this function compute the SHA directly from the artifact
    bytes so a single authority owns the attested SHA. Callers
    that already have the SHA captured MAY pass it as a
    consistency check.
    """
    portable_path = _portable_validated_path(
        repo_root=repo_root, target=target
    )
    artifact_bytes = _read_and_hash_target(target)
    computed_sha = hashlib.sha256(artifact_bytes).hexdigest()
    canonical_parser_command = portable_parser_command(
        validated_path=portable_path
    )
    # ``parser_command`` remains a compatibility input for existing callers,
    # but it is never persisted: portable evidence has one canonical command.
    if final_sha256 is not None and final_sha256 != computed_sha:
        raise _AttestationError(
            f"caller-supplied final_sha256 does not match the actual "
            f"artifact bytes: expected {final_sha256}, computed "
            f"{computed_sha} for {target}"
        )

    attestation_path = target.parent / "gate-summary-validation.json"
    attestation = {
        "schema_version": 1,
        "validated_path": portable_path,
        "validated_sha256": computed_sha,
        "validated_at": datetime.now(UTC).isoformat(),
        "parser_identity": "scripts/factory/parse_gate_summary.py",
        "parser_command": canonical_parser_command,
        "parser_exit_code": parser_exit_code
        if parser_exit_code is not None
        else -1,
        "parser_duration_ms": parser_duration_ms,
        "decode_status": decode_status,
        "acceptance_status": acceptance_status,
        "diagnostics": dict(diagnostics) if diagnostics else {},
    }
    attestation_path.write_text(
        json.dumps(attestation, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return attestation_path


def _parse_attestation(attestation_path: Path) -> dict[str, Any]:
    try:
        raw = attestation_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _AttestationError(
            f"failed to read validation attestation at "
            f"{attestation_path}: {exc}"
        ) from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _AttestationError(
            f"validation attestation is not valid JSON: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise _AttestationError(
            "validation attestation root MUST be a JSON object"
        )
    return data


def _require_str(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise _AttestationError(
            f"validation attestation field {field!r} MUST be a non-empty string"
        )
    return value


def _require_typed_status(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if value not in {"pass", "fail"}:
        raise _AttestationError(
            f"validation attestation field {field!r} MUST be 'pass' or 'fail'; "
            f"got {value!r}"
        )
    return cast(str, value)


def resolve_validated_path(
    *,
    repo_root: Path,
    validated_path: str,
) -> Path:
    """Resolve a portable ``validated_path`` against ``repo_root``.

    Raises :class:`_AttestationError` when ``validated_path``
    carries a shape that is NOT a portable repository-relative
    POSIX path -- this includes absolute paths (POSIX or
    Windows), Windows drive letters (any letter, not just
    ``C:\\`` and ``D:\\``), UNC anchors, ``..`` traversal, and
    paths that resolve outside ``repo_root``.
    """
    _validate_portable_posix_path(validated_path)
    candidate = (repo_root / validated_path).resolve()
    repo_root_resolved = repo_root.resolve()
    try:
        candidate.relative_to(repo_root_resolved)
    except ValueError as exc:
        raise _AttestationError(
            f"validated_path resolved outside repo_root: "
            f"{candidate!r} not under {repo_root_resolved!r}"
        ) from exc
    return candidate


def verify_validation_attestation(
    *,
    repo_root: Path,
    attestation_path: Path,
) -> ValidationAttestationResult:
    """Verify the sibling gate-summary validation attestation.

    The verifier enforces, end-to-end, every invariant a portable
    validation attestation MUST satisfy. Every failure mode
    raises :class:`_AttestationError`; the function NEVER returns
    a result with ``sha_matches=False``.

    1. The sibling attestation file is present, readable, and
       syntactically valid JSON.
    2. The ``validated_path`` is portable (no absolute prefix, no
       Windows drive / UNC, no ``..`` traversal, no empty
       segments, resolves inside ``repo_root``).
    3. The resolved validated artifact is a regular file that
       exists and is readable on disk.
    4. The SHA-256 of the resolved artifact bytes equals the
       attested ``validated_sha256`` exactly.
    5. The typed verdict fields ``decode_status`` and
       ``acceptance_status`` are each ``pass`` or ``fail``.
    """
    if not attestation_path.exists():
        raise _AttestationError(
            f"sibling validation attestation missing at {attestation_path}"
        )
    if not attestation_path.is_file():
        raise _AttestationError(
            f"sibling validation attestation MUST be a regular file "
            f"at {attestation_path}"
        )

    payload = _parse_attestation(attestation_path)
    portable_path = _require_str(payload, "validated_path")
    validated_abs = resolve_validated_path(
        repo_root=repo_root,
        validated_path=portable_path,
    )
    if not validated_abs.exists():
        raise _AttestationError(
            f"validated artifact missing at {validated_abs}"
        )
    if not validated_abs.is_file():
        raise _AttestationError(
            f"validated artifact MUST be a regular file; "
            f"{validated_abs} is not a file"
        )
    validated_sha = _require_str(payload, "validated_sha256")
    if not _SHA256_HEX_RE.match(validated_sha):
        raise _AttestationError(
            f"validation attestation field 'validated_sha256' MUST be a "
            f"64-char lowercase hex SHA-256; got {validated_sha!r}"
        )
    try:
        actual_bytes = validated_abs.read_bytes()
    except OSError as exc:
        raise _AttestationError(
            f"validated artifact not readable at {validated_abs}: {exc}"
        ) from exc
    actual_sha = hashlib.sha256(actual_bytes).hexdigest()
    if actual_sha != validated_sha:
        raise _AttestationError(
            f"SHA mismatch on validated artifact {validated_abs}: "
            f"expected {validated_sha}, got {actual_sha}"
        )
    parser_identity = _require_str(payload, "parser_identity")
    parser_command = _require_str(payload, "parser_command")
    if "\\" in parser_command or any(
        prefix in parser_command for prefix in FORBIDDEN_ABSOLUTE_PREFIXES
    ):
        raise _AttestationError(
            "validation attestation parser_command MUST be portable; "
            f"got {parser_command!r}"
        )
    decode_status = _require_typed_status(payload, "decode_status")
    acceptance_status = _require_typed_status(payload, "acceptance_status")

    return ValidationAttestationResult(
        attestation_path=attestation_path,
        validated_path=validated_abs,
        validated_sha256=validated_sha,
        parser_identity=parser_identity,
        decode_status=decode_status,
        acceptance_status=acceptance_status,
        portable_validated_path=portable_path,
    )


__all__ = [
    "FORBIDDEN_ABSOLUTE_PREFIXES",
    "ValidationAttestationResult",
    "portable_parser_command",
    "resolve_validated_path",
    "verify_validation_attestation",
    "write_validation_attestation",
]
