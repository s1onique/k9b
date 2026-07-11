"""Canonical ACT-local gate-summary parser.

Companion to `scripts/factory/build_gate_summary.py`. This is the ONLY
code path that should be used to validate a `.factory/gate-summary.json`
artifact. Callers MUST go through `parse_gate_summary()` instead of
using `json.load()` directly.

The parser returns a structured `ParsedGateSummary` with explicit fields
for `source_status`, `schema_version`, `generated_at`, `overall_status`,
`checks_total`, and `checks_failed` — the values the R10 task's targeted
digest parser requires. The parser is the acceptance evidence per R10.

Exit code semantics
-------------------
- 0 : PASS — overall_status=pass, source_status=present, schema=1, no failed checks.
- 1 : FAIL — any of the above fields invalid.
- 2 : MISSING — no `.factory/gate-summary.json` file present.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

EXPECTED_SCHEMA_VERSION = 1
REQUIRED_R12_CHECK_NAMES = (
    "canonical-verifier-self-test",
    "standalone-production-verifier",
    "production-mypy-positive",
    "production-mypy-negative",
    "full-gate-negative-proofs",
    "opaque-bearer-regression",
    "sanitizer-regression-matrix",
    "credential-matrix",
    "omission-boundary",
    "serializer-multi-return",
    "ruff",
    "mypy",
    "git-diff-check",
    "git-diff-cached-check",
    "llm-friendly",
    "no-new-llm-allowlist",
    "targeted-repository-gate",
    "gate-summary-parser",
)


@dataclass(frozen=True)
class ParsedGateSummary:
    """Structured parse of a gate-summary.json artifact."""

    source_path: Path
    source_status: str
    schema_version: int
    generated_at: str
    overall_status: str
    checks_total: int
    checks_failed: int
    checks: list[dict[str, Any]]
    self_tests: dict[str, dict[str, int]]
    extras: dict[str, Any]
    parse_errors: list[str]

    @property
    def is_pass(self) -> bool:
        return (
            self.source_status == "present"
            and self.schema_version == EXPECTED_SCHEMA_VERSION
            and self.generated_at != ""
            and self.overall_status == "pass"
            and self.checks_total > 0
            and self.checks_failed == 0
            and not self.parse_errors
        )

    @property
    def missing_check_names(self) -> list[str]:
        """Return the list of R12 required check names absent from the artifact."""
        declared: set[str] = set()
        if isinstance(self.extras, dict):
            value = self.extras.get("required_check_names")
            if isinstance(value, list):
                declared.update(str(item) for item in value)
        check_names = {str(check.get("name", "")) for check in self.checks if isinstance(check, dict)}
        return sorted(set(REQUIRED_R12_CHECK_NAMES) - declared - check_names)


def parse_gate_summary(target: Path) -> ParsedGateSummary:
    """Parse and validate a gate-summary.json artifact.

    Returns a structured ParsedGateSummary. Never raises on parse errors —
    errors are recorded in `parse_errors`.
    """
    parse_errors: list[str] = []
    source_status = "missing"
    schema_version = 0
    generated_at = ""
    overall_status = "fail"
    checks_total = 0
    checks_failed = 0
    checks: list[dict[str, Any]] = []
    self_tests: dict[str, dict[str, int]] = {}
    extras: dict[str, Any] = {}

    if not target.exists():
        parse_errors.append(f"gate summary not found at {target}")
        return ParsedGateSummary(
            source_path=target,
            source_status=source_status,
            schema_version=schema_version,
            generated_at=generated_at,
            overall_status=overall_status,
            checks_total=checks_total,
            checks_failed=checks_failed,
            checks=checks,
            self_tests=self_tests,
            extras=extras,
            parse_errors=parse_errors,
        )

    try:
        raw = target.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        parse_errors.append(f"failed to read/parse {target}: {exc}")
        return ParsedGateSummary(
            source_path=target,
            source_status="invalid",
            schema_version=schema_version,
            generated_at=generated_at,
            overall_status=overall_status,
            checks_total=checks_total,
            checks_failed=checks_failed,
            checks=checks,
            self_tests=self_tests,
            extras=extras,
            parse_errors=parse_errors,
        )

    if not isinstance(data, dict):
        parse_errors.append(f"{target}: root is not a dict")
        return ParsedGateSummary(
            source_path=target,
            source_status="invalid",
            schema_version=schema_version,
            generated_at=generated_at,
            overall_status=overall_status,
            checks_total=checks_total,
            checks_failed=checks_failed,
            checks=checks,
            self_tests=self_tests,
            extras=extras,
            parse_errors=parse_errors,
        )

    source_status = "present"
    schema_version = int(data.get("schema_version", 0))
    generated_at = str(data.get("generated_at", ""))
    overall_status = str(data.get("overall_status", "fail"))
    checks_total = int(data.get("checks_total", len(data.get("checks", []))))
    checks_failed = int(
        data.get("checks_failed", sum(1 for c in data.get("checks", []) if c.get("status") == "fail")),
    )
    checks = list(data.get("checks", []))
    self_tests_raw = data.get("self_tests", {})
    if isinstance(self_tests_raw, dict):
        for name, val in self_tests_raw.items():
            if isinstance(val, dict):
                self_tests[name] = {k: int(v) for k, v in val.items() if isinstance(v, (int, bool, float))}
    extras = data.get("extras", {})

    # Validation
    if schema_version != EXPECTED_SCHEMA_VERSION:
        parse_errors.append(f"{target}: schema_version={schema_version} != {EXPECTED_SCHEMA_VERSION}")
    if not generated_at:
        parse_errors.append(f"{target}: generated_at is empty")
    else:
        try:
            stamp = generated_at.rstrip("Z")
            datetime.fromisoformat(stamp)
        except ValueError as exc:
            parse_errors.append(f"{target}: generated_at not ISO-8601: {exc}")
    if overall_status not in {"pass", "fail"}:
        parse_errors.append(f"{target}: overall_status={overall_status!r}")
    if checks_total <= 0:
        parse_errors.append(f"{target}: checks_total={checks_total} must be > 0")
    if checks_failed < 0 or checks_failed > checks_total:
        parse_errors.append(
            f"{target}: checks_failed={checks_failed} out of range for checks_total={checks_total}"
        )
    check_names = [str(check.get("name", "")) for check in checks if isinstance(check, dict)]
    if len(check_names) != len(set(check_names)):
        parse_errors.append(f"{target}: duplicate check names are not allowed")

    # The canonical REQUIRED_R12_CHECK_NAMES may be declared either via
    # ``extras.required_check_names`` (the canonical contract) or as
    # check names in the ``checks`` list itself. The parser fails closed
    # when any required name is absent from both surfaces.
    declared: set[str] = set()
    if isinstance(extras, dict):
        declared_value = extras.get("required_check_names")
        if isinstance(declared_value, list):
            declared.update(str(item) for item in declared_value)
    missing = sorted(set(REQUIRED_R12_CHECK_NAMES) - declared - set(check_names))
    if missing:
        parse_errors.append(f"{target}: missing required R12 checks: {', '.join(missing)}")

    return ParsedGateSummary(
        source_path=target,
        source_status=source_status,
        schema_version=schema_version,
        generated_at=generated_at,
        overall_status=overall_status,
        checks_total=checks_total,
        checks_failed=checks_failed,
        checks=checks,
        self_tests=self_tests,
        extras=extras,
        parse_errors=parse_errors,
    )


def render_targeted_digest(parsed: ParsedGateSummary) -> str:
    """Render the targeted digest output the R10 task requires."""
    lines = [
        f"source_path={parsed.source_path}",
        f"source_status={parsed.source_status}",
        f"schema_version={parsed.schema_version}",
        f"generated_at={parsed.generated_at}",
        f"overall_status={parsed.overall_status}",
        f"checks_total={parsed.checks_total}",
        f"checks_failed={parsed.checks_failed}",
        "check_names=" + ",".join(str(check.get("name", "")) for check in parsed.checks if isinstance(check, dict)),
    ]
    if parsed.missing_check_names:
        lines.append("missing_check_names=" + ",".join(parsed.missing_check_names))
    if parsed.parse_errors:
        lines.append("parse_errors=" + "; ".join(parsed.parse_errors))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Canonical gate-summary parser")
    parser.add_argument(
        "--target",
        default=".factory/gate-summary.json",
        help="Path to the gate-summary artifact",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Emit only the digest lines (no banner)",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    target = Path(args.target)
    parsed = parse_gate_summary(target)
    digest = render_targeted_digest(parsed)
    if not args.quiet:
        print("=== TARGETED DIGEST ===")
    sys.stdout.write(digest)
    sys.stdout.flush()
    if not args.quiet:
        print("========================")
    if parsed.parse_errors:
        return 1
    if not parsed.is_pass:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
