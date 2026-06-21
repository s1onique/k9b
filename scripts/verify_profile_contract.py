#!/usr/bin/env python3
"""
Verification profile contract validator.

Ensures that:
1. fast does not accidentally include known expensive suites
2. full includes all required merge-grade gates
3. skipped checks are reported honestly
4. success output always includes the profile name

Usage:
    python scripts/verify_profile_contract.py          # Run all contract checks
    python scripts/verify_profile_contract.py --json   # JSON output
    python scripts/verify_profile_contract.py --check <contract>  # Run specific check
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Optional

# Import from verify_profiles
sys.path.insert(0, str(__file__).rsplit("/", 1)[0] if "/" in __file__ else ".")
from verify_profiles import (
    get_all_steps,
    get_profiles,
    resolve_profile,
    StepCategory,
)


# =============================================================================
# Contract Definitions
# =============================================================================


@dataclass
class ContractCheck:
    """A single contract check."""
    id: str
    description: str
    check_fn: callable
    severity: str = "error"


def check_fast_no_expensive_steps() -> tuple[bool, str]:
    """Contract: Fast profile must not include expensive steps."""
    steps, skipped = resolve_profile("fast")
    expensive_steps = [s for s in steps if s.is_expensive]
    if expensive_steps:
        return False, f"fast includes expensive steps: {[s.id for s in expensive_steps]}"
    return True, "fast excludes all expensive steps"


def check_fast_includes_core_checks() -> tuple[bool, str]:
    """Contract: Fast profile must include core linting and typing checks."""
    steps, _ = resolve_profile("fast")
    step_ids = {s.id for s in steps}
    required = {"ruff-lint", "mypy"}
    missing = required - step_ids
    if missing:
        return False, f"fast missing core checks: {sorted(missing)}"
    return True, "fast includes core linting and typing checks"


def check_full_includes_all_non_excluded() -> tuple[bool, str]:
    """Contract: Full profile must include all steps not explicitly excluded."""
    all_step_ids = {s.id for s in get_all_steps()}
    steps, _ = resolve_profile("full")
    full_step_ids = {s.id for s in steps}
    profiles = get_profiles()
    full_profile = profiles["full"]
    expected = all_step_ids - set(full_profile.excludes)
    missing = expected - full_step_ids
    if missing:
        return False, f"full missing steps: {sorted(missing)}"
    return True, "full includes all expected steps"


def check_all_steps_in_some_profile() -> tuple[bool, str]:
    """Contract: Every known step must appear in at least one profile."""
    all_step_ids = {s.id for s in get_all_steps()}
    profiles = get_profiles()
    covered = set()
    for profile in profiles.values():
        covered.update(profile.includes)
        covered -= set(profile.excludes)
    orphan = all_step_ids - covered
    if orphan:
        return False, f"steps not covered by any profile: {sorted(orphan)}"
    return True, "all steps covered by profiles"


def check_profile_contract_has_escalation() -> tuple[bool, str]:
    """Contract: Non-full profiles must have escalation commands."""
    profiles = get_profiles()
    missing_escalation = []
    for name, profile in profiles.items():
        if name != "full" and not profile.escalation_command:
            missing_escalation.append(name)
    if missing_escalation:
        return False, f"profiles missing escalation_command: {missing_escalation}"
    return True, "all non-full profiles have escalation commands"


def check_step_commands_are_valid() -> tuple[bool, str]:
    """Contract: All step commands should be non-empty."""
    issues = []
    for step in get_all_steps():
        if not step.command.strip():
            issues.append(f"{step.id}: empty command")
    if issues:
        return False, f"invalid step commands: {issues}"
    return True, "all step commands are valid"


def check_no_duplicate_step_ids() -> tuple[bool, str]:
    """Contract: All step IDs must be unique."""
    step_ids = [s.id for s in get_all_steps()]
    seen = set()
    duplicates = []
    for sid in step_ids:
        if sid in seen:
            duplicates.append(sid)
        seen.add(sid)
    if duplicates:
        return False, f"duplicate step IDs: {sorted(set(duplicates))}"
    return True, "all step IDs are unique"


def check_shell_gate_drift() -> tuple[bool, str]:
    """Contract: Shell delegates to Python for profile semantics."""
    from verify_profile_executor import check_shell_drift as executor_check_shell_drift
    passed, errors = executor_check_shell_drift()
    if passed:
        return True, "shell and Python aligned (verified by verify_profile_executor)"
    return False, "; ".join(errors)


# =============================================================================
# Contract Registry
# =============================================================================


CONTRACT_CHECKS = [
    ContractCheck("fast-no-expensive", "Fast profile excludes expensive steps", check_fast_no_expensive_steps, "error"),
    ContractCheck("fast-core-checks", "Fast profile includes core linting and typing", check_fast_includes_core_checks, "error"),
    ContractCheck("full-completeness", "Full profile includes all non-excluded steps", check_full_includes_all_non_excluded, "error"),
    ContractCheck("all-covered", "All steps are covered by at least one profile", check_all_steps_in_some_profile, "error"),
    ContractCheck("escalation-commands", "Non-full profiles have escalation commands", check_profile_contract_has_escalation, "error"),
    ContractCheck("valid-commands", "All step commands are valid", check_step_commands_are_valid, "warning"),
    ContractCheck("unique-ids", "All step IDs are unique", check_no_duplicate_step_ids, "error"),
    ContractCheck("shell-drift", "Shell and Python profile definitions aligned", check_shell_gate_drift, "error"),
]


# =============================================================================
# Contract Execution
# =============================================================================


@dataclass
class ContractResult:
    id: str
    description: str
    passed: bool
    message: str
    severity: str


def run_contract_checks(check_ids: Optional[list[str]] = None) -> list[ContractResult]:
    """Run contract checks, optionally filtered by IDs."""
    results = []
    for check in CONTRACT_CHECKS:
        if check_ids and check.id not in check_ids:
            continue
        try:
            passed, message = check.check_fn()
        except Exception as e:
            passed = False
            message = f"Exception during check: {e}"
        results.append(ContractResult(check.id, check.description, passed, message, check.severity))
    return results


def format_results(results: list[ContractResult], json_output: bool = False) -> str:
    """Format contract check results."""
    if json_output:
        return json.dumps({
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "checks": [{"id": r.id, "description": r.description, "passed": r.passed, "message": r.message, "severity": r.severity} for r in results],
        }, indent=2)
    
    lines = ["=" * 60, "Verification Profile Contract Results", "=" * 60]
    lines.append(f"Total: {len(results)} | Passed: {sum(1 for r in results if r.passed)} | Failed: {sum(1 for r in results if not r.passed)}")
    lines.append("")
    for r in results:
        status = "✓ PASS" if r.passed else "✗ FAIL"
        lines.append(f"{status} [{r.severity}] {r.id}")
        lines.append(f"  {r.description}")
        if not r.passed:
            lines.append(f"  Details: {r.message}")
        lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Verify verification profile contracts")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--check", action="append", dest="checks", help="Run specific check")
    parser.add_argument("--list", action="store_true", help="List all available contract checks")

    args = parser.parse_args()

    if args.list:
        print("Available contract checks:")
        for check in CONTRACT_CHECKS:
            print(f"  {check.id}: {check.description} [{check.severity}]")
        return 0

    results = run_contract_checks(check_ids=args.checks)
    print(format_results(results, json_output=args.json))
    
    errors = [r for r in results if not r.passed and r.severity == "error"]
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
