"""Shared source builders and assertions for backend-outcome verifier self-tests.

This module is deliberately not named ``test_*`` and contains no collected tests.
Every check delegates to the real verifier implementation.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Final, cast

import pytest

SCRIPTS: Final[Path] = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from verifiers import (  # noqa: E402
    automatic_diagnosis_backend_detail_outcomes as verifier,
)

OUTCOMES_PATH: Final[Path] = (
    verifier.SRC_ROOT / "collect" / "incident_diagnosis_backend_detail_outcomes.py"
)
LOOKUP_PATH: Final[Path] = (
    verifier.SRC_ROOT / "collect" / "incident_diagnosis_backend_detail_lookup.py"
)
DISPATCH_PATH: Final[Path] = (
    verifier.SRC_ROOT / "collect" / "incident_diagnosis_dispatch.py"
)
PROCESSOR_PATH: Final[Path] = (
    verifier.SRC_ROOT
    / "collect"
    / "incident_diagnosis_auto_loop_evidence_processor.py"
)


def _format_violations(violations: Iterable[str]) -> str:
    return "\n".join(f"- {violation}" for violation in violations)


def assert_violation(violations: list[str], *fragments: str) -> None:
    """Assert one verifier violation contains every fragment, case-insensitively."""
    lowered = tuple(fragment.lower() for fragment in fragments)
    assert any(
        all(fragment in violation.lower() for fragment in lowered)
        for violation in violations
    ), (
        f"Expected one violation containing {fragments!r}, got:\n"
        f"{_format_violations(violations)}"
    )


def assert_no_violation(violations: list[str], fragment: str) -> None:
    """Assert no verifier violation contains ``fragment``, case-insensitively."""
    assert not any(fragment.lower() in violation.lower() for violation in violations), (
        f"Did not expect a violation containing {fragment!r}, got:\n"
        f"{_format_violations(violations)}"
    )


def write_synthetic_source(tmp_path: Path, source: str) -> Path:
    """Write one synthetic module used by per-file verifier checks."""
    path = tmp_path / "synthetic_backend_outcome_seam.py"
    path.write_text(source, encoding="utf-8")
    return path


def _patch_named_source(
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    source: str,
) -> None:
    original_read = verifier._read

    def patched_read(path: Path) -> str | None:
        if path.name == filename:
            return source
        return cast(str | None, original_read(path))

    monkeypatch.setattr(verifier, "_read", patched_read)


def check_outcome_source(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> list[str]:
    _patch_named_source(monkeypatch, OUTCOMES_PATH.name, source)
    return cast(list[str], verifier._check_outcome_model())


def check_lookup_source(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> list[str]:
    """Run both real lookup checks against a synthetic canonical source."""
    _patch_named_source(monkeypatch, LOOKUP_PATH.name, source)
    return [
        *verifier._check_lookup_signature(),
        *verifier._check_lookup_module_not_found_branch(LOOKUP_PATH),
    ]


def check_dispatch_source(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> list[str]:
    _patch_named_source(monkeypatch, DISPATCH_PATH.name, source)
    return cast(
        list[str],
        verifier._check_local_mode_truthfulness(DISPATCH_PATH),
    )


def check_processor_source(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> list[str]:
    _patch_named_source(monkeypatch, PROCESSOR_PATH.name, source)
    return cast(list[str], verifier._check_processor_dispatch(PROCESSOR_PATH))


def check_disposition_source(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> list[str]:
    _patch_named_source(
        monkeypatch,
        "incident_diagnosis_disposition.py",
        source,
    )
    return cast(list[str], verifier._check_reason_codes())


def check_compat_source(
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> list[str]:
    _patch_named_source(
        monkeypatch,
        "incident_diagnosis_disposition_compat.py",
        source,
    )
    return cast(
        list[str],
        verifier._check_no_substring_backend_incident_matching(),
    )


def check_touched_seam_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> list[str]:
    """Run the real per-file exception, truthiness, and construction checks."""
    path = write_synthetic_source(tmp_path, source)
    module_name = verifier._module_name_from_path(path)
    monkeypatch.setattr(
        verifier,
        "TOUCHED_SEAM_MODULES",
        (module_name, *verifier.TOUCHED_SEAM_MODULES),
    )
    return [
        *verifier._check_not_found_construction(path),
        *verifier._check_no_broad_exception_to_not_found(path),
        *verifier._check_no_truthiness_to_not_found(path),
    ]


def outcome_model_source(
    *,
    variants: tuple[str, ...] = verifier.REQUIRED_VARIANTS,
    union_members: tuple[str, ...] | None = None,
    frozen: bool = True,
    slots: bool = True,
    found_incident_annotation: str = "Incident",
    found_discriminator: bool = False,
    include_failure_enum: bool = True,
) -> str:
    """Build a valid outcome model with narrowly selectable mutations."""
    if union_members is None:
        union_members = variants
    blocks = [
        "from dataclasses import dataclass",
        "from enum import StrEnum",
        "from typing import TypeAlias",
        "",
        "class BackendIncidentLookupSource(StrEnum):",
        '    BACKEND_API = "backend_api"',
        '    LOCAL_STORE = "local_store"',
    ]
    if include_failure_enum:
        blocks.extend([
            "",
            "class BackendIncidentLookupFailureCode(StrEnum):",
            '    INVALID_JSON = "invalid_json"',
            '    INVALID_PAYLOAD = "invalid_payload"',
            '    UNSUPPORTED_SCHEMA = "unsupported_schema"',
            '    DESERIALIZATION_FAILED = "deserialization_failed"',
            '    IDENTITY_MISMATCH = "identity_mismatch"',
            '    UNAUTHORIZED = "unauthorized"',
            '    FORBIDDEN = "forbidden"',
            '    HTTP_CLIENT_ERROR = "http_client_error"',
            '    BACKEND_ERROR = "backend_error"',
            '    TRANSPORT_ERROR = "transport_error"',
        ])
    decorator = f"@dataclass(frozen={frozen!r}, slots={slots!r})"
    if "BackendIncidentFound" in variants:
        blocks.extend([
            "",
            decorator,
            "class BackendIncidentFound:",
            "    requested_incident_id: IncidentId",
            f"    incident: {found_incident_annotation}",
            "    source: BackendIncidentLookupSource",
            "    http_status: int | None = None",
        ])
        if found_discriminator:
            blocks.append("    found: bool = True")
    if "BackendIncidentNotFound" in variants:
        blocks.extend([
            "",
            decorator,
            "class BackendIncidentNotFound:",
            "    requested_incident_id: IncidentId",
            "    source: BackendIncidentLookupSource",
            "    http_status: int | None = None",
        ])
    if "BackendIncidentLookupFailed" in variants:
        blocks.extend([
            "",
            decorator,
            "class BackendIncidentLookupFailed:",
            "    requested_incident_id: IncidentId",
            "    failure_code: BackendIncidentLookupFailureCode",
        ])
    if "BackendIncidentRetryable" in union_members:
        blocks.extend([
            "",
            decorator,
            "class BackendIncidentRetryable:",
            "    requested_incident_id: IncidentId",
        ])
    blocks.extend([
        "",
        "BackendIncidentLookupOutcome: TypeAlias = (",
        f'    "{" | ".join(union_members)}"',
        ")",
    ])
    return "\n".join(blocks)


def lookup_source(
    *,
    predicate: str = "response.http_status == 404",
    source_expression: str | None = "BackendIncidentLookupSource.BACKEND_API",
    include_http_status: bool = True,
    return_annotation: str = "BackendIncidentLookupOutcome",
    include_parser_call: bool = True,
    include_bare_none: bool = False,
) -> str:
    """Build a structurally valid lookup with selectable HTTP mutations."""
    lines = [
        f"def lookup_backend_incident(client, incident_id) -> {return_annotation}:",
    ]
    if include_bare_none:
        lines.extend(["    if not incident_id:", "        return None"])
    lines.extend([
        "    response = client.get(incident_id)",
        f"    if {predicate}:",
        "        return BackendIncidentNotFound(",
        "            requested_incident_id=incident_id,",
    ])
    if source_expression is not None:
        lines.append(f"            source={source_expression},")
    if include_http_status:
        lines.append("            http_status=404,")
    parser_name = (
        "parse_internal_incident_detail_payload" if include_parser_call else "parse_payload"
    )
    lines.extend([
        "        )",
        f"    payload = {parser_name}(response.payload)",
        "    incident = Incident.from_dict(payload)",
        "    if incident.incident_id != incident_id:",
        "        return BackendIncidentLookupFailed(requested_incident_id=incident_id)",
        "    return BackendIncidentFound(",
        "        requested_incident_id=incident_id, incident=incident",
        "    )",
    ])
    return "\n".join(lines)

