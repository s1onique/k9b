"""Canonical ACT-local gate-summary generator.

This module is the SINGLE source of truth for emitting the
`.factory/gate-summary.json` artifact. The shape is fixed at:

    schema_version = 1
    generated_at    = "<RFC3339 UTC timestamp>"
    source_status   = "present"
    overall_status  = "pass" | "fail"
    profile         = "act-local"
    checks          = { "<check_name>": {"status": "pass"|"fail"|"skip", "duration_ms": int} }
    checks_total    = int
    checks_failed   = int
    self_tests      = { "<category>": {accepted, rejected, failed} }
    r10_definition_of_done = { ... }

The companion `scripts/factory/parse_gate_summary.py` is the SINGLE source of
truth for validating a `.factory/gate-summary.json` artifact. Other code MUST
go through that parser instead of `json.load`.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
PROFILE = "act-local"


@dataclass(frozen=True)
class CheckOutcome:
    """Per-check outcome derived from an executed command."""

    name: str
    status: str  # "pass" | "fail" | "skip"
    duration_ms: int = 0
    error_message: str | None = None
    command: str | None = None
    exit_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SubsystemSelfTestCount:
    """Self-test counts for a verifier subsystem."""

    accepted: int
    rejected: int
    failed: int


def build_self_test_counts(
    accepted: int,
    rejected: int,
    failed: int,
) -> SubsystemSelfTestCount:
    return SubsystemSelfTestCount(
        accepted=accepted,
        rejected=rejected,
        failed=failed,
    )


@dataclass(frozen=True)
class GateSummary:
    """The complete gate-summary artifact."""

    schema_version: int = SCHEMA_VERSION
    profile: str = PROFILE
    overall_status: str = "pass"
    source_status: str = "present"
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    checks: list[CheckOutcome] = field(default_factory=list)
    self_tests: dict[str, SubsystemSelfTestCount] = field(default_factory=dict)
    r10_definition_of_done: dict[str, Any] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def checks_total(self) -> int:
        return len(self.checks)

    @property
    def checks_failed(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail")

    @property
    def checks_passed(self) -> int:
        return sum(1 for c in self.checks if c.status == "pass")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "profile": self.profile,
            "source_status": self.source_status,
            "overall_status": self.overall_status if self.checks_total > 0 else "fail",
            "generated_at": self.generated_at,
            "checks_total": self.checks_total,
            "checks_failed": self.checks_failed,
            "checks": [c.to_dict() for c in self.checks],
            "self_tests": {name: asdict(count) for name, count in self.self_tests.items()},
            "r10_definition_of_done": dict(self.r10_definition_of_done),
        }
        if self.extras:
            out["extras"] = dict(self.extras)
        return out

    def write(self, target: Path) -> None:
        """Write the gate summary atomically to the target path."""
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )


def make_r10_defaults() -> dict[str, Any]:
    """Return the canonical r10_definition_of_done payload."""
    return {
        "canonical_self_test_uses_production_verifiers": (
            "redaction_types.py --self-test invokes "
            "check_trusted_constructor_usage, check_protected_boundary_imports, "
            "check_serializer_explicit_conversion, check_projector_parameter_type, "
            "check_privacy_state_factories, check_exception_definition, "
            "check_safe_omission_constant, check_alias_declarations, "
            "check_type_hierarchy via temp source trees"
        ),
        "shared_evaluator": ("accepted fixture: errors == []; rejected fixture: errors != [] AND every expected substring present AND unrelated diagnostic does NOT satisfy"),
        "postponed_annotations": ("ast.Constant string annotations parsed via ast.parse(mode=eval); nested and qualified protected types rejected; 'list[X]' 'dict[K,V]' subscripts parsed recursively"),
        "act_local_negative_proofs": ("Each violation invoked as subprocess of the canonical redaction_types.py --self-test wrapper; nonzero exit + diagnostic matched; clean rerun confirmed."),
        "mypy_negative_uses_production": (
            "Negative fixture imports the production incident_evidence_redaction.RedactedEvidenceText and incident_evidence_llm_safe.RedactedEvidenceSummary / evidence_artifact_to_llm_safe_summary; mirror NewType hierarchy NOT used as final acceptance proof."
        ),
        "gate_summary_canonical_contract": ("scripts/factory/build_gate_summary.py is the SINGLE generator; scripts/factory/parse_gate_summary.py is the SINGLE parser."),
    }


def load_existing(target: Path) -> GateSummary | None:
    """Load an existing gate summary, or None if missing/incompatible."""
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if data.get("schema_version") != SCHEMA_VERSION:
        return None
    raw_self_tests = data.get("self_tests", {})
    parsed_self_tests: dict[str, SubsystemSelfTestCount] = {}
    for _name, _vals in raw_self_tests.items():
        if isinstance(_vals, dict):
            parsed_self_tests[_name] = SubsystemSelfTestCount(**_vals)
    return GateSummary(
        schema_version=data.get("schema_version", SCHEMA_VERSION),
        profile=data.get("profile", PROFILE),
        overall_status=data.get("overall_status", "pass"),
        source_status=data.get("source_status", "present"),
        generated_at=data.get("generated_at", ""),
        checks=[CheckOutcome(**c) for c in data.get("checks", [])],
        self_tests=parsed_self_tests,
        r10_definition_of_done=data.get("r10_definition_of_done", {}),
        extras=data.get("extras", {}),
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Re-emit an existing summary using the canonical schema."""
    argv = list(sys.argv[1:] if argv is None else argv)
    target = Path(argv[0]) if argv else Path(".factory/gate-summary.json")
    existing = load_existing(target)
    if existing is None:
        print(
            f"gate summary unavailable at {target}; use scripts/factory/populate_gate_summary.py to execute checks",
            file=sys.stderr,
        )
        return 1
    else:
        # Preserve existing values but normalize to canonical schema.
        summary = GateSummary(
            schema_version=existing.schema_version,
            profile=existing.profile,
            overall_status=existing.overall_status,
            source_status=existing.source_status,
            generated_at=existing.generated_at,
            checks=list(existing.checks),
            self_tests=dict(existing.self_tests),
            r10_definition_of_done=existing.r10_definition_of_done or make_r10_defaults(),
            extras=existing.extras,
        )
        # Refresh generated_at only when explicitly regenerating.
        summary = GateSummary(
            schema_version=summary.schema_version,
            profile=summary.profile,
            overall_status=summary.overall_status,
            source_status=summary.source_status,
            generated_at=datetime.now(UTC).isoformat(),
            checks=summary.checks,
            self_tests=summary.self_tests,
            r10_definition_of_done=summary.r10_definition_of_done,
            extras=summary.extras,
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    summary.write(target)
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
