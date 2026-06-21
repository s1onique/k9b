#!/usr/bin/env python3
"""
Verification profile executor - CLI entrypoint.

This is a thin wrapper that imports from profile model and plan modules.
The authoritative profile semantics live in:
- verify_profile_model.py: Step registry and profile definitions
- verify_profile_plan.py: Profile resolution and plan generation

Usage:
    python scripts/verify_profile_executor.py --resolve --profile fast
    python scripts/verify_profile_executor.py --check-drift
    python scripts/verify_profile_executor.py --emit-plan --profile fast [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from verify_profile_model import FAST_EXCLUDES, STEPS
from verify_profile_plan import (
    emit_full_plan,
    resolve_profile,
)


def check_shell_drift() -> tuple[bool, list[str]]:
    """
    Check for drift between shell script and Python definitions.
    
    New architecture: Shell delegates to Python for profile semantics and execution.
    """
    errors = []
    shell_script = Path(__file__).parent / "verify_all.sh"
    
    if not shell_script.exists():
        errors.append("verify_all.sh not found")
        return False, errors
    
    content = shell_script.read_text()
    
    
    # 1. Verify shell delegates to Python runner for execution
    has_python_runner = bool(re.search(r'verify_profile_runner\.py', content))
    if not has_python_runner:
        errors.append("Shell should call verify_profile_runner.py for execution")
    
    # 2. Verify shell loads plan from Python
    has_plan_load = bool(re.search(r'emit_full_plan|from verify_profile_plan', content))
    if not has_plan_load:
        errors.append("Shell should load plan from verify_profile_plan")
    
    # 3. Verify shell delegates profile resolution to Python
    has_profile_resolution = bool(re.search(r"STEP_PROFILE|STEP_SCOPE", content))
    if not has_profile_resolution:
        errors.append("Shell should use Python-computed profile resolution")
    
    # 4. Verify shell does NOT own step execution logic
    has_step_dispatch = bool(re.search(r'case "\$step_id"', content))
    if has_step_dispatch:
        errors.append("Shell should not have case dispatch for step_id")
    
    has_hardcoded_steps = bool(re.search(r'python_steps=|frontend_steps=|helm_steps=', content))
    if has_hardcoded_steps:
        errors.append("Shell should not have hardcoded step lists")
    
    return len(errors) == 0, errors


def check_profile_plan_drift() -> tuple[bool, list[str]]:
    """Check for drift between profile plan and actual execution."""
    errors = []
    
    plan = resolve_profile("fast", "all")
    
    for step in plan.steps:
        if step["id"] not in STEPS:
            errors.append(f"Step {step['id']} in plan but not in registry")
    
    for step_id in plan.skipped:
        if step_id not in STEPS:
            errors.append(f"Skipped step {step_id} not in registry")
        if step_id not in FAST_EXCLUDES:
            errors.append(f"Step {step_id} skipped but not in FAST_EXCLUDES")
    
    return len(errors) == 0, errors


def main():
    parser = argparse.ArgumentParser(
        description="Verification profile executor - owns profile semantics"
    )
    parser.add_argument("--resolve", action="store_true", help="Resolve profile to step plan")
    parser.add_argument("--profile", choices=["fast", "full"], default="fast", help="Profile to resolve")
    parser.add_argument("--scope", choices=["all", "python", "frontend", "helm"], default="all", help="Execution scope")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--check-drift", action="store_true", help="Check shell/Python drift")
    parser.add_argument("--emit-plan", action="store_true", help="Emit plan for shell consumption")
    parser.add_argument("--shell-commands", action="store_true", help="Emit shell command array")

    args = parser.parse_args()

    if args.check_drift:
        shell_ok, shell_errors = check_shell_drift()
        plan_ok, plan_errors = check_profile_plan_drift()
        all_errors = shell_errors + plan_errors
        
        if args.json:
            print(json.dumps({
                "shell_drift_passed": shell_ok,
                "shell_drift_errors": shell_errors,
                "profile_plan_drift_passed": plan_ok,
                "profile_plan_drift_errors": plan_errors,
                "all_passed": len(all_errors) == 0,
            }, indent=2))
        else:
            print("=" * 60)
            print("Verification Profile Contract Drift Check")
            print("=" * 60)
            print()
            
            print("Shell/Python drift check:")
            if shell_ok:
                print("  ✓ PASS - Shell and Python aligned")
            else:
                print("  ✗ FAIL - Shell and Python drift detected:")
                for err in shell_errors:
                    print(f"    - {err}")
            
            print()
            print("Profile plan drift check:")
            if plan_ok:
                print("  ✓ PASS - Profile plan consistent")
            else:
                print("  ✗ FAIL - Profile plan drift detected:")
                for err in plan_errors:
                    print(f"    - {err}")
            
            print()
            print("=" * 60)
        
        return 1 if all_errors else 0

    if args.resolve or args.emit_plan or args.shell_commands:
        full_plan = emit_full_plan(args.profile, args.scope)
        
        if args.json:
            print(json.dumps(full_plan, indent=2))
        else:
            # Human-readable
            print(f"Profile: {full_plan['profile']}")
            print(f"Scope: {full_plan['scope']}")
            print(f"Full gate: {full_plan['is_full_gate']}")
            print(f"Full lane: {full_plan['is_full_lane']}")
            print()
            print(f"Steps to run ({full_plan['step_count']}):")
            
            for lane in ['python', 'frontend', 'helm']:
                steps = full_plan['lanes'].get(lane, [])
                if steps:
                    print(f"  [{lane}]")
                    for step in steps:
                        print(f"    - {step['id']}: {step['description']}")
            
            if full_plan['skipped']:
                print()
                print(f"Skipped ({full_plan['skipped_count']}):")
                for s in full_plan['skipped']:
                    print(f"  - {s['id']}: {s['reason']}")
            
            if full_plan['profile'] == "fast":
                print()
                print("For merge-grade verification:")
                print("  ./scripts/verify_all.sh --full")
        
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
