"""Canonical ACT-local gate-summary parser.

Companion to `scripts/factory/build_gate_summary.py`. This is the ONLY
code path that should be used to validate a `.factory/gate-summary.json`
artifact. Callers MUST go through `parse_gate_summary()` instead of
using `json.load()` directly.

The parser returns a structured `ParsedGateSummary` with explicit fields
for `source_status`, `schema_version`, `generated_at`, `overall_status`,
`checks_total`, `checks_failed`, `decode_status`, and `acceptance_status`
— the values the R10 task's targeted digest parser requires. The
parser is the acceptance evidence per R10.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01-
CORRECTION03-EXTERNAL-EVIDENCE-AND-PARSER-FAIL-CLOSED-TRUTH01:

* The parser distinguishes ``decode_status`` (the JSON document is
  syntactically valid and conformant to the documented schema) from
  ``acceptance_status`` (every check inside the artifact passed).
  A structurally valid artifact with one or more failing checks
  produces ``decode_status=pass`` and ``acceptance_status=fail``.
* The parser fails CLOSED on the required-check inventory:
  ``actual_check_names == REQUIRED_R12_CHECK_NAMES`` is enforced
  directly. Declaring names in ``extras.required_check_names``
  does NOT substitute for actually executing the check.
* The parser records ``acceptance_status=fail`` when any of
  ``checks_total == len(checks)``, ``checks_failed == count(status
  == "fail")``, ``overall_status == "pass" iff checks_failed == 0``,
  or the required-check invariant fails.
* The CLI exposes three unambiguous modes:
  ``--decode-only`` returns the parse without enforcing the
  acceptance contract; ``--accept-only`` enforces the acceptance
  contract; the default behaviour returns both.

Exit code semantics
-------------------
- 0 : PASS  -- ``decode_status=pass`` AND ``acceptance_status=pass``.
- 1 : FAIL  -- ``acceptance_status=fail`` (acceptance check failed).
- 2 : DECODE-FAIL -- ``decode_status=fail`` (could not decode the artifact).
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
# ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01-CORRECTION02:
# ``gate-summary-parser`` is removed from the required check
# inventory. The parser is the self-referential consumer of the
# artifact; recording it in the ``checks`` array would force a
# circular dependency between the artifact and the parser that
# consumes it. The producer records the parser invocation in a
# separate validation attestation artifact (NOT in the gate-summary
# artifact) so the canonical contract becomes
# ``len(checks) == checks_total == len(required_check_names)``.
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
    decode_status: str
    acceptance_status: str
    decode_errors: list[str]
    acceptance_errors: list[str]
    parse_errors: list[str]

    @property
    def is_pass(self) -> bool:
        return self.decode_status == "pass" and self.acceptance_status == "pass"

    @property
    def is_decode_pass(self) -> bool:
        return self.decode_status == "pass"

    @property
    def is_acceptance_pass(self) -> bool:
        return self.acceptance_status == "pass"

    @property
    def check_names(self) -> list[str]:
        return [str(check.get("name", "")) for check in self.checks if isinstance(check, dict)]

    @property
    def unique_check_names(self) -> set[str]:
        return {n for n in self.check_names if n}

    @property
    def required_check_names(self) -> tuple[str, ...]:
        return REQUIRED_R12_CHECK_NAMES

    @property
    def missing_check_names(self) -> list[str]:
        actual = self.unique_check_names
        required = set(self.required_check_names)
        return sorted(required - actual)

    @property
    def unexpected_check_names(self) -> list[str]:
        actual = self.unique_check_names
        required = set(self.required_check_names)
        return sorted(actual - required)


def parse_gate_summary(target: Path) -> ParsedGateSummary:
    """Parse and validate a gate-summary.json artifact.

    The parser never raises on parse errors -- errors are recorded
    in ``parse_errors``. ``decode_status`` and ``acceptance_status``
    are computed independently so callers can distinguish a
    structurally broken artifact from a structurally valid artifact
    whose contents are failing the gate.

    The required-check inventory is enforced against the actual
    ``checks`` list. Declaring names in ``extras.required_check_names``
    is documentation only and does NOT substitute for executing the
    check.
    """
    parse_errors: list[str] = []
    decode_errors: list[str] = []
    acceptance_errors: list[str] = []
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
        decode_errors.append("artifact_missing")
        return _build_parsed(
            target=target,
            parse_errors=parse_errors,
            decode_errors=decode_errors,
            acceptance_errors=acceptance_errors,
            source_status=source_status,
            schema_version=schema_version,
            generated_at=generated_at,
            overall_status=overall_status,
            checks_total=checks_total,
            checks_failed=checks_failed,
            checks=checks,
            self_tests=self_tests,
            extras=extras,
        )

    try:
        raw = target.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        parse_errors.append(f"failed to read/parse {target}: {exc}")
        decode_errors.append("json_decode_error")
        return _build_parsed(
            target=target,
            parse_errors=parse_errors,
            decode_errors=decode_errors,
            acceptance_errors=acceptance_errors,
            source_status="invalid",
            schema_version=schema_version,
            generated_at=generated_at,
            overall_status=overall_status,
            checks_total=checks_total,
            checks_failed=checks_failed,
            checks=checks,
            self_tests=self_tests,
            extras=extras,
        )

    if not isinstance(data, dict):
        parse_errors.append(f"{target}: root is not a dict")
        decode_errors.append("root_not_dict")
        return _build_parsed(
            target=target,
            parse_errors=parse_errors,
            decode_errors=decode_errors,
            acceptance_errors=acceptance_errors,
            source_status="invalid",
            schema_version=schema_version,
            generated_at=generated_at,
            overall_status=overall_status,
            checks_total=checks_total,
            checks_failed=checks_failed,
            checks=checks,
            self_tests=self_tests,
            extras=extras,
        )

    source_status = "present"
    schema_version = int(data.get("schema_version", 0))
    generated_at = str(data.get("generated_at", ""))
    overall_status = str(data.get("overall_status", "fail"))
    raw_checks = data.get("checks", [])
    if not isinstance(raw_checks, list):
        decode_errors.append("checks_not_array")
        raw_checks = []
    checks_total = int(data.get("checks_total", len(raw_checks)))
    checks_failed = int(
        data.get(
            "checks_failed",
            sum(1 for c in raw_checks if isinstance(c, dict) and c.get("status") == "fail"),
        ),
    )
    checks = list(raw_checks)
    self_tests_raw = data.get("self_tests", {})
    if isinstance(self_tests_raw, dict):
        for name, val in self_tests_raw.items():
            if isinstance(val, dict):
                self_tests[name] = {
                    k: int(v) for k, v in val.items() if isinstance(v, (int, bool, float))
                }
    extras = data.get("extras", {})

    # Schema-decode checks.  These conditions are required for a
    # structurally valid v1 artifact; failing any of them produces
    # ``decode_status=fail`` and the parser refuses to compute
    # ``acceptance_status`` (which remains ``fail``).
    if schema_version != EXPECTED_SCHEMA_VERSION:
        decode_errors.append(f"schema_version={schema_version} != {EXPECTED_SCHEMA_VERSION}")
    if not generated_at:
        decode_errors.append("generated_at_empty")
    else:
        try:
            stamp = generated_at.rstrip("Z")
            datetime.fromisoformat(stamp)
        except ValueError as exc:
            decode_errors.append(f"generated_at_not_iso8601: {exc}")
    if overall_status not in {"pass", "fail"}:
        decode_errors.append(f"overall_status_invalid: {overall_status!r}")
    if checks_total < 0:
        decode_errors.append(f"checks_total_negative: {checks_total}")
    if checks_failed < 0 or checks_failed > max(checks_total, len(checks)):
        decode_errors.append(
            f"checks_failed_out_of_range: {checks_failed}/{checks_total}"
        )

    decode_status = "pass" if not decode_errors else "fail"

    # Acceptance checks.  Each invariant is recorded as a separate
    # error so the caller can localise the regression without
    # rerunning the producer.
    if decode_status == "pass":
        if checks_total == 0:
            acceptance_errors.append(
                "acceptance_failure: checks_total=0 (no checks executed)"
            )
        if len(checks) != checks_total:
            acceptance_errors.append(
                f"checks_total_derivation: {checks_total} != len(checks)={len(checks)}"
            )
        actual_failed = sum(
            1 for c in checks if isinstance(c, dict) and c.get("status") == "fail"
        )
        if actual_failed != checks_failed:
            acceptance_errors.append(
                f"checks_failed_derivation: {checks_failed} != "
                f"count(status==fail)={actual_failed}"
            )
        # Direct acceptance signals: a structurally valid artifact
        # with any failing check MUST produce acceptance_status=fail.
        if actual_failed > 0:
            acceptance_errors.append(
                f"acceptance_failure: {actual_failed} check(s) failed"
            )
        if overall_status == "fail":
            acceptance_errors.append(
                "acceptance_failure: overall_status='fail'"
            )
        check_names = [str(c.get("name", "")) for c in checks if isinstance(c, dict)]
        duplicates = [n for n in set(check_names) if check_names.count(n) > 1]
        if duplicates:
            acceptance_errors.append(f"duplicate_check_names: {duplicates}")
        actual_set = {n for n in check_names if n}
        required_set = set(REQUIRED_R12_CHECK_NAMES)
        missing = sorted(required_set - actual_set)
        if missing:
            acceptance_errors.append(
                f"missing_required_checks: declaration alone does not satisfy the "
                f"contract; missing={missing}"
            )
        unexpected = sorted(actual_set - required_set)
        if unexpected:
            acceptance_errors.append(
                f"unexpected_check_names: {unexpected}"
            )
        expected_overall = "pass" if checks_failed == 0 else "fail"
        if overall_status != expected_overall:
            acceptance_errors.append(
                f"overall_status_derivation: overall_status={overall_status!r} "
                f"!= derived={expected_overall!r}"
            )

    acceptance_status = "pass" if not acceptance_errors else "fail"

    parse_errors.extend(decode_errors)
    parse_errors.extend(acceptance_errors)

    return _build_parsed(
        target=target,
        parse_errors=parse_errors,
        decode_errors=decode_errors,
        acceptance_errors=acceptance_errors,
        source_status=source_status,
        schema_version=schema_version,
        generated_at=generated_at,
        overall_status=overall_status,
        checks_total=checks_total,
        checks_failed=checks_failed,
        checks=checks,
        self_tests=self_tests,
        extras=extras,
        decode_status=decode_status,
        acceptance_status=acceptance_status,
    )


def _build_parsed(
    *,
    target: Path,
    parse_errors: list[str],
    decode_errors: list[str],
    acceptance_errors: list[str],
    source_status: str,
    schema_version: int,
    generated_at: str,
    overall_status: str,
    checks_total: int,
    checks_failed: int,
    checks: list[dict[str, Any]],
    self_tests: dict[str, dict[str, int]],
    extras: dict[str, Any],
    decode_status: str = "fail",
    acceptance_status: str = "fail",
) -> ParsedGateSummary:
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
        decode_status=decode_status,
        acceptance_status=acceptance_status,
        decode_errors=decode_errors,
        acceptance_errors=acceptance_errors,
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
        f"decode_status={parsed.decode_status}",
        f"acceptance_status={parsed.acceptance_status}",
        "check_names=" + ",".join(parsed.check_names),
    ]
    if parsed.missing_check_names:
        lines.append("missing_check_names=" + ",".join(parsed.missing_check_names))
    if parsed.unexpected_check_names:
        lines.append("unexpected_check_names=" + ",".join(parsed.unexpected_check_names))
    if parsed.decode_errors:
        lines.append("decode_errors=" + "; ".join(parsed.decode_errors))
    if parsed.acceptance_errors:
        lines.append("acceptance_errors=" + "; ".join(parsed.acceptance_errors))
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
    parser.add_argument(
        "--decode-only",
        action="store_true",
        help="Decode the artifact but do not enforce the acceptance contract",
    )
    parser.add_argument(
        "--accept-only",
        action="store_true",
        help="Enforce the acceptance contract only (assumes decode already passed)",
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
    if parsed.decode_status != "pass":
        return 2
    if not args.decode_only and parsed.acceptance_status != "pass":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())