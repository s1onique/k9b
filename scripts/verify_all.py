#!/usr/bin/env python3
"""
Canonical verification gate entrypoint.

This is the Python implementation of the verification gate orchestration.
The shell script verify_all.sh is now a compatibility shim that execs this module.

Usage:
    python scripts/verify_all.py [--fast|--full] [--json] [--python-only|--frontend-only|--helm-only]

For backward compatibility, the shell shim delegates all arguments:
    ./scripts/verify_all.sh ... → .venv/bin/python scripts/verify_all.py ...

Policy: Only --full may be called "full gate green".
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add scripts to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from verify_all_lock import (
    acquire_verify_lock,
    check_recursion,
    set_recursion_guard,
    LockError,
)
from verify_all_orchestrator import run_verification
from verify_all_output import print_result


def get_repo_root() -> Path:
    """Get the repository root directory."""
    return SCRIPT_DIR.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Canonical verification gate for the k9b repository.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Profiles:
  --fast       Fast local profile (≤60s, policy + smoke checks) [DEFAULT]
  --full       Exhaustive merge-grade verification

Without -f or --full, defaults to --fast for local development.

Output modes:
  --json       Emit only JSON summary to stdout

Policy: Only --full may be called "full gate green".
        """,
    )
    
    profile_group = parser.add_mutually_exclusive_group()
    profile_group.add_argument(
        "--fast",
        action="store_const",
        const="fast",
        dest="profile",
        help="Fast local profile (≤60s, policy + smoke checks)",
    )
    profile_group.add_argument(
        "--full",
        action="store_const",
        const="full",
        dest="profile",
        help="Exhaustive merge-grade verification",
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit only JSON summary to stdout",
    )
    
    # Legacy scope options (preserved)
    scope_group = parser.add_mutually_exclusive_group()
    scope_group.add_argument(
        "--python-only",
        action="store_const",
        const="python",
        dest="scope",
        help="Run only Python lane steps",
    )
    scope_group.add_argument(
        "--frontend-only",
        action="store_const",
        const="frontend",
        dest="scope",
        help="Run only Frontend lane steps",
    )
    scope_group.add_argument(
        "--helm-only",
        action="store_const",
        const="helm",
        dest="scope",
        help="Run only Helm lane steps",
    )
    
    parser.set_defaults(profile=None, scope="all")
    
    return parser.parse_args(argv)


def resolve_profile_and_scope(args: argparse.Namespace) -> tuple[str, str]:
    """
    Resolve effective profile and scope.
    
    Logic:
    - If scope is not 'all', profile becomes 'full' (legacy behavior)
    - Otherwise, default to 'fast' for local development
    """
    scope = args.scope or "all"
    
    if scope != "all":
        # Lane scope = full (legacy behavior)
        return "full", scope
    
    if args.profile:
        return args.profile, scope
    
    # Local default
    return "fast", scope


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    # Recursion protection - check before argument parsing
    # so --help works even when recursion is detected
    if check_recursion():
        print("ERROR: verify_all.py recursion detected.", file=sys.stderr)
        return 2
    
    # Parse arguments
    try:
        args = parse_args(argv)
    except SystemExit:
        raise  # Re-raise argparse's SystemExit
    
    # Resolve profile and scope
    profile, scope = resolve_profile_and_scope(args)
    
    # Get repo root
    repo_root = get_repo_root()
    
    # Check for Python availability
    python_path = repo_root / ".venv" / "bin" / "python"
    if not python_path.exists():
        python_path = Path(sys.executable)
    if not python_path.exists():
        print("ERROR: Python not available", file=sys.stderr)
        return 1
    
    # Recursion protection
    if check_recursion():
        print("ERROR: verify_all.py recursion detected.", file=sys.stderr)
        return 2
    
    # Acquire lock
    try:
        lock = acquire_verify_lock(repo_root)
    except LockError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 4
    
    # Set recursion guard
    set_recursion_guard()
    
    # Ensure runs directory exists
    (repo_root / "runs" / "verification").mkdir(parents=True, exist_ok=True)
    
    try:
        # Run verification
        result = run_verification(
            repo_root=repo_root,
            profile=profile,
            scope=scope,
            json_mode=args.json,
        )
        
        # Print result
        print_result(result, repo_root, json_mode=args.json)
        
        # Return exit code
        return 0 if result.success else 1
        
    except Exception as e:
        if args.json:
            # In JSON mode, emit error as JSON
            import json
            print(json.dumps({
                "success": False,
                "profile": profile,
                "scope": scope,
                "error": str(e),
            }))
        else:
            print(f"ERROR: Verification failed: {e}", file=sys.stderr)
        return 1
    
    finally:
        # Release lock
        lock.release()


if __name__ == "__main__":
    sys.exit(main())