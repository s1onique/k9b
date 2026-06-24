#!/usr/bin/env python3
"""
ACT-Local Verification Mode.

Bounded verification for local agent ACT work:
- Checks changed files precisely
- Preserves cheap global safety gates
- Reports broader repo failures separately
- Never runs broad pytest or full local verification unless explicitly requested
- Gives actionable per-step commands and failure attribution

Usage:
    python scripts/act_local_verification.py [--json]

This module is the thin CLI orchestrator that imports from act_local_* modules.
"""

from __future__ import annotations

import sys

from act_local_changed_files import filter_python_files, get_changed_files
from act_local_checks import (
    run_doctrine_check,
    run_golden_case_check,
    run_golden_case_privacy_check,
    run_incident_api_one_pass_diagnosis_check,
    run_incident_api_route_one_pass_diagnosis_check,
    run_json_contract_check,
    run_llm_friendly_on_files,
    run_mypy_on_files,
    run_no_new_llm_allowlist_check,
    run_provenance_golden_case_check,
    run_ruff_on_files,
    run_shell_containment_on_files,
    run_verification_discipline_check,
    run_workflow_check,
)
from act_local_contract import ActLocalResult, CheckResult
from act_local_output import format_human_output, format_json_output

# =============================================================================
# ACT-Local Verification
# =============================================================================

def run_act_local_verification(json_mode: bool = False) -> ActLocalResult:
    """
    Run ACT-local verification.
    
    This runs bounded checks on changed files only:
    - ruff on changed Python files
    - mypy on changed Python files
    - LLM-friendly checks on changed files
    - shell containment on changed shell files
    - doctrine checks
    - verification discipline guard
    
    Forbidden by default:
    - pytest (broad)
    - full fast profile
    - expensive frontend suite
    """
    checks: list[CheckResult] = []
    failure_commands: list[str] = []
    
    # Get changed files
    changed_files = get_changed_files()
    
    # Filter for check types
    python_files = filter_python_files(changed_files)
    
    # Run ruff on changed Python files
    ruff_result = run_ruff_on_files(python_files)
    checks.append(ruff_result)
    if ruff_result.status == "FAIL":
        failure_commands.append(ruff_result.command)
    
    # Run mypy on changed Python files
    mypy_result = run_mypy_on_files(python_files)
    checks.append(mypy_result)
    if mypy_result.status == "FAIL":
        failure_commands.append(mypy_result.command)
    
    # Run no-new-allowlist check BEFORE LLM-friendly check
    # This gate rejects allowlist growth before the normal gate can accept it
    no_new_allowlist_result = run_no_new_llm_allowlist_check()
    checks.append(no_new_allowlist_result)
    if no_new_allowlist_result.status == "FAIL":
        failure_commands.append(no_new_allowlist_result.command)
    
    # Run LLM-friendly checks on changed files
    llm_result = run_llm_friendly_on_files(changed_files)
    checks.append(llm_result)
    if llm_result.status == "FAIL":
        failure_commands.append(llm_result.command)
    
    # Run shell containment on changed shell files
    shell_result = run_shell_containment_on_files(changed_files)
    checks.append(shell_result)
    if shell_result.status == "FAIL":
        failure_commands.append(shell_result.command)
    
    # Run doctrine check (always runs, cheap)
    doctrine_result = run_doctrine_check()
    checks.append(doctrine_result)
    if doctrine_result.status == "FAIL":
        failure_commands.append(doctrine_result.command)
    
    # Run verification discipline guard
    discipline_result = run_verification_discipline_check()
    checks.append(discipline_result)
    if discipline_result.status == "FAIL":
        failure_commands.append(discipline_result.command)
    
    # Run JSON contract check
    json_result = run_json_contract_check()
    checks.append(json_result)
    if json_result.status == "FAIL":
        failure_commands.append(json_result.command)
    
    # Run GitHub workflow verifier (always runs - cheap, global check)
    workflow_result = run_workflow_check()
    checks.append(workflow_result)
    if workflow_result.status == "FAIL":
        failure_commands.append(workflow_result.command)
    
    # Run golden case diagnosis verification (uses checked-in fixtures)
    golden_result = run_golden_case_check()
    checks.append(golden_result)
    if golden_result.status == "FAIL":
        failure_commands.append(golden_result.command)
    
    # Run provenance verification for golden case (verifies live-derived provenance fields)
    provenance_result = run_provenance_golden_case_check()
    checks.append(provenance_result)
    if provenance_result.status == "FAIL":
        failure_commands.append(provenance_result.command)
    
    # Run privacy verification for golden case (verifies no private topology leaks)
    privacy_result = run_golden_case_privacy_check()
    checks.append(privacy_result)
    if privacy_result.status == "FAIL":
        failure_commands.append(privacy_result.command)
    
    # Run incident API/service one-pass diagnosis wiring verification
    # This exercises the service seam with golden-case fixtures and proves
    # the same one-pass loop is invoked as the golden-case proof
    api_one_pass_result = run_incident_api_one_pass_diagnosis_check()
    checks.append(api_one_pass_result)
    if api_one_pass_result.status == "FAIL":
        failure_commands.append(api_one_pass_result.command)
    
    # Run incident API route one-pass diagnosis wiring verification
    # This exercises the HTTP API route with golden-case fixtures and proves
    # the route wires to run_incident_one_pass_diagnosis()
    api_route_result = run_incident_api_route_one_pass_diagnosis_check()
    checks.append(api_route_result)
    if api_route_result.status == "FAIL":
        failure_commands.append(api_route_result.command)
    
    # Determine overall success (all non-skipped checks must pass)
    non_skipped = [c for c in checks if c.status != "SKIP"]
    success = all(c.status == "PASS" for c in non_skipped) if non_skipped else True
    
    # Build skipped checks list
    skipped_checks = [
        {"id": "pytest-broad", "reason": "Broad pytest suite - use targeted pytest for changed tests"},
        {"id": "full-fast-gate", "reason": "Full fast profile - not evaluated by ACT-local"},
        {"id": "frontend-suite", "reason": "Frontend suite - not evaluated by ACT-local"},
        {"id": "expensive-docs", "reason": "Expensive docs checks - not evaluated by ACT-local"},
    ]
    
    return ActLocalResult(
        success=success,
        changed_files=changed_files,
        checks=checks,
        skipped_checks=skipped_checks,
        broader_gate_status="not_evaluated",
        failure_commands=failure_commands,
    )


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    """Main entry point."""
    # Handle --help
    if "--help" in sys.argv or "-h" in sys.argv:
        print("""
ACT-Local Verification Mode

Bounded verification for local agent ACT work.

Usage:
    python scripts/act_local_verification.py [--json]

Options:
    --json    Emit JSON output to stdout

ACT-local runs bounded checks on changed files only:
- ruff on changed Python files
- mypy on changed Python files
- LLM-friendly checks
- shell containment
- doctrine checks
- verification discipline guard

It SKIPS:
- broad pytest
- full fast profile
- expensive frontend suite
""")
        return 0
    
    json_mode = "--json" in sys.argv
    
    try:
        result = run_act_local_verification(json_mode=json_mode)
        
        if json_mode:
            print(format_json_output(result))
        else:
            print(format_human_output(result))
        
        return 0 if result.success else 1
        
    except Exception as e:
        if json_mode:
            import json
            print(json.dumps({
                "profile": "act-local",
                "success": False,
                "error": str(e),
            }))
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
