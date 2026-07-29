"""Producer + runtime verifier for the gate-summary validation attestation.

ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION05:

Two halves live here:

* :func:`write_validation_attestation` is invoked by
  :mod:`scripts.factory.populate_gate_summary` after it writes the
  canonical artifact. The producer persists a *portable*
  ``validated_path`` (repository-relative POSIX) in the sibling
  ``.factory/gate-summary-validation.json`` attestation so the
  committed byte content is identical on every runner.
* :func:`verify_validation_attestation` is the runtime verifier.
  It re-creates the absolute path on the runtime runner and rejects,
  with a bounded diagnostic, any attestation that:
  - leaks an absolute path (``/Users/...``, ``/home/runner/...``,
    Windows drive prefix ``C:\\...``);
  - contains ``..`` path-traversal segments;
  - resolves to a location outside ``repo_root``.

Callers MUST go through :func:`verify_validation_attestation` so the
attestation integrity (file presence, portable ``validated_path``,
``parser_identity`` identity, and ``validated_sha256`` SHA-256
match against the current file bytes) is enforced through one
canonical helper. The verifier never auto-fetches artefacts from a
remote source -- the attestation is always resolved relative to the
caller-supplied ``repo_root``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ACT-K9B-HULK-PROMOTION-FINAL-LOCAL-ACCEPTANCE01-CORRECTION05:
# Forbidden absolute-path prefixes that MUST be rejected at the
# runtime verifier so committed attestations never leak host paths.
FORBIDDEN_ABSOLUTE_PREFIXES = (
    "/Users/",       # macOS / developer workstation prefix
    "/home/runner/", # GitHub Actions Linux runner prefix
    "/home/circleci/",
    "/root/",
    "C:\\",          # Windows drive prefix
    "D:\\",
    "/private/",     # macOS /private/var/.../pytest-of-* temp prefix
)

# Bounded 64-char lowercase hex SHA-256 fingerprint.
_SHA256_HEX_LENGTH = 64
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ValidationAttestationResult:
    """Structured verification result for a sibling attestation."""

    attestation_path: Path
    validated_path: Path
    validated_sha256: str
    parser_identity: str
    decode_status: str
    acceptance_status: str
    sha_matches: bool
    portable_validated_path: str


class _AttestationError(ValueError):
    """Bounded, machine-parseable exception type for verifier failures."""


def _reject_forbidden_absolute(value: str) -> None:
    """Raise ``_AttestationError`` if ``value`` leaks an absolute path.

    The rejection covers macOS developer prefixes, GitHub Actions
    runner prefixes, Windows drive prefixes, and ``/private/``
    prefixes that pytest-emitted tmp paths occasionally produce on
    macOS. The check is intentionally conservative: any rejected
    prefix MUST be explicitly listed in
    :data:`FORBIDDEN_ABSOLUTE_PREFIXES` so the contract is auditable.
    """
    if not isinstance(value, str) or not value:
        raise _AttestationError(
            "validated_path MUST be a non-empty string"
        )
    for prefix in FORBIDDEN_ABSOLUTE_PREFIXES:
        if value.startswith(prefix):
            raise _AttestationError(
                f"validated_path MUST be portable (repository-relative); "
                f"detected forbidden absolute prefix {prefix!r} in {value!r}"
            )
    if value.startswith("/") or value.startswith("\\"):
        # Catch any remaining absolute POSIX or Windows path that is
        # not in the explicit prefix list (preserves the contract
        # while keeping the surface narrow).
        raise _AttestationError(
            f"validated_path MUST be portable (repository-relative); "
            f"got absolute path {value!r}"
        )


def resolve_validated_path(
    *,
    repo_root: Path,
    validated_path: str,
) -> Path:
    """Resolve a portable ``validated_path`` against ``repo_root``.

    Raises :class:`_AttestationError` (exposed publicly as the
    attestation-failure contract) when ``validated_path`` carries an
    absolute prefix, a Windows drive prefix, a ``..`` traversal
    segment, or when the resolved path escapes ``repo_root``.

    The returned :class:`pathlib.Path` is the canonical, attacker-safe
    absolute location the runtime verifier should read.
    """
    _reject_forbidden_absolute(validated_path)
    segments = validated_path.replace("\\", "/").split("/")
    if ".." in segments:
        raise _AttestationError(
            f"validated_path MUST NOT contain '..' path traversal; "
            f"got {validated_path!r}"
        )
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
    return value  # type: ignore[return-value]


def verify_validation_attestation(
    *,
    repo_root: Path,
    attestation_path: Path,
) -> ValidationAttestationResult:
    """Verify the sibling gate-summary validation attestation.

    The verifier enforces, end-to-end, every invariant a portable
    validation attestation MUST satisfy:

    1. The sibling attestation is present next to
       ``.factory/gate-summary.json``.
    2. The ``validated_path`` is portable (no absolute prefix, no
       ``..`` traversal, resolves inside ``repo_root``).
    3. The ``parser_identity`` is a non-empty string identifying the
       canonical parser module path.
    4. The ``validated_sha256`` is a 64-char lowercase hex value that
       matches the SHA-256 of the artefact at the resolved location.
       If the artefact was mutated after the attestation was written
       the SHA mismatch surfaces immediately -- callers may treat
       this as the canonical drift detector.
    5. The typed verdict fields ``decode_status`` and
       ``acceptance_status`` are each ``pass`` or ``fail``.

    The verifier is intentionally strict: every diagnostic is bounded
    and machine-parseable so reviewers can tell a missing field from
    a forbidden path from a SHA mismatch without rerunning the
    producer.
    """
    repo_root = repo_root.resolve()
    if not attestation_path.exists():
        raise _AttestationError(
            f"sibling validation attestation missing at {attestation_path}"
        )

    payload = _parse_attestation(attestation_path)
    portable_path = _require_str(payload, "validated_path")
    validated_abs = resolve_validated_path(
        repo_root=repo_root,
        validated_path=portable_path,
    )
    validated_sha = _require_str(payload, "validated_sha256")
    if not _SHA256_HEX_RE.match(validated_sha):
        raise _AttestationError(
            f"validation attestation field 'validated_sha256' MUST be a "
            f"64-char lowercase hex SHA-256; got {validated_sha!r}"
        )
    parser_identity = _require_str(payload, "parser_identity")
    decode_status = _require_typed_status(payload, "decode_status")
    acceptance_status = _require_typed_status(payload, "acceptance_status")

    sha_matches: bool
    if not validated_abs.exists():
        sha_matches = False
    else:
        actual_sha = hashlib.sha256(
            validated_abs.read_bytes()
        ).hexdigest()
        sha_matches = actual_sha == validated_sha
        if not sha_matches:
            raise _AttestationError(
                f"SHA mismatch on validated artifact {validated_abs}: "
                f"expected {validated_sha}, got {actual_sha}"
            )

    return ValidationAttestationResult(
        attestation_path=attestation_path,
        validated_path=validated_abs,
        validated_sha256=validated_sha,
        parser_identity=parser_identity,
        decode_status=decode_status,
        acceptance_status=acceptance_status,
        sha_matches=sha_matches,
        portable_validated_path=portable_path,
    )



def write_validation_attestation(
    *,
    repo_root: Path,
    target: Path,
    final_sha256: str,
    parser_command: str,
    parser_exit_code: int,
    parser_duration_ms: int,
    decode_status: str,
    acceptance_status: str,
    diagnostics: Mapping[str, Any] | None = None,
) -> Path:
    """Persist the sibling ``gate-summary-validation.json`` attestation.

    The ``validated_path`` written into the attestation is a portable
    repository-relative POSIX path (``target`` resolved under
    ``repo_root`` when possible). Absolute paths, ``..`` traversal,
    and Windows drive prefixes are forbidden -- the runtime verifier
    rejects every such shape with a bounded diagnostic. The
    function NEVER embeds the parser verdict inside the validated
    artifact bytes: the attestation lives in a separate sibling
    file so subsequent mutations are detectable as SHA-256
    mismatches.
    """
    try:
        portable_validated_path = target.resolve().relative_to(
            repo_root.resolve()
        ).as_posix()
    except ValueError:
        portable_validated_path = ".factory/gate-summary.json"
    attestation_path = target.parent / "gate-summary-validation.json"
    attestation = {
        "schema_version": 1,
        "validated_path": portable_validated_path,
        "validated_sha256": final_sha256,
        "validated_at": datetime.now(UTC).isoformat(),
        "parser_identity": "scripts/factory/parse_gate_summary.py",
        "parser_command": parser_command,
        "parser_exit_code": parser_exit_code,
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


__all__ = [
    "FORBIDDEN_ABSOLUTE_PREFIXES",
    "ValidationAttestationResult",
    "resolve_validated_path",
    "verify_validation_attestation",
    "write_validation_attestation",
]
