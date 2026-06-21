#!/usr/bin/env python3
"""
Canonical verification gate entrypoint.

This is the Python implementation of the verification gate orchestration.
The shell script verify_all.sh is now a compatibility shim that execs this module.

Usage:
    python scripts/verify_all.py [--fast|--full|--act-local] [--json] [--python-only|--frontend-only|--helm-only]
    python scripts/verify_all.py --lock-status [--json]
    python scripts/verify_all.py [--fast|--act-local] --wait-for-lock <seconds>
    python scripts/verify_all.py --unlock-stale

For backward compatibility, the shell shim delegates all arguments:
    ./scripts/verify_all.sh ... → .venv/bin/python scripts/verify_all.py ...

Policy: Only --full may be called "full gate green".

ACT-Local mode:
    --act-local runs bounded verification on changed files only.
    It never runs broad pytest or full fast profile unless explicitly requested.
    Use this as the default close-check for local agent ACTs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add scripts to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from act_local_verification import (
    format_human_output,
    run_act_local_verification,
)
from act_local_verification import (
    format_json_output as act_local_format_json,
)
from verify_all_lock import (
    LockError,
    VerifyLock,
    acquire_verify_lock,
    check_recursion,
    get_lock_status,
    set_recursion_guard,
    unlock_stale_lock,
    wait_for_lock,
)
from verify_all_lock_types import format_lock_status_human
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
  --act-local  Bounded verification on changed files only (local agent default)

Without -f or --full, defaults to --fast for local development.

Output modes:
  --json       Emit only JSON summary to stdout

Lock management commands:
  --lock-status              Show lock status and owner diagnostics
  --lock-status --json       Show lock status in JSON format
  --wait-for-lock <seconds>  Wait for lock to be released (with timeout)
  --unlock-stale             Remove a stale/orphaned lock (safe operation)

Policy: Only --full may be called "full gate green".
ACT-Local: Use --act-local as the default close-check for local agent ACTs.
        """,
    )
    
    # Profile group (mutually exclusive)
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
    profile_group.add_argument(
        "--act-local",
        action="store_const",
        const="act-local",
        dest="profile",
        help="Bounded verification on changed files only (local agent default)",
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit only JSON summary to stdout",
    )
    
    # Lock management commands (mutually exclusive with profile)
    lock_group = parser.add_mutually_exclusive_group()
    lock_group.add_argument(
        "--lock-status",
        action="store_true",
        help="Show lock status and owner diagnostics",
    )
    lock_group.add_argument(
        "--unlock-stale",
        action="store_true",
        help="Remove a stale/orphaned lock (safe operation only)",
    )
    
    parser.add_argument(
        "--wait-for-lock",
        type=int,
        metavar="SECONDS",
        help="Wait for lock to be released with timeout (default: 300s)",
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
    
    parser.set_defaults(profile=None, scope="all", wait_for_lock=None)
    
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


def handle_lock_status(repo_root: Path, json_mode: bool) -> int:
    """Handle --lock-status command."""
    status = get_lock_status(repo_root)
    
    if json_mode:
        print(json.dumps(status.to_dict(), indent=2))
        return 0
    else:
        print(format_lock_status_human(status))
        return 0


def handle_unlock_stale(repo_root: Path) -> int:
    """Handle --unlock-stale command."""
    success, message = unlock_stale_lock(repo_root)
    print(message)
    return 0 if success else 1


def handle_wait_for_lock(repo_root: Path, timeout_seconds: int, profile: str) -> tuple[bool, int | None]:
    """
    Handle --wait-for-lock command.
    
    Returns:
        Tuple of (proceed, exit_code)
        - proceed=True means lock was acquired, caller should continue
        - proceed=False means timeout or error, exit_code is the error code
    """
    acquired, message = wait_for_lock(repo_root, timeout_seconds=timeout_seconds)
    
    if acquired:
        return True, None
    
    print(f"ERROR: {message}", file=sys.stderr)
    print("Hint: Run ./scripts/verify_all.sh --lock-status for more diagnostics", file=sys.stderr)
    return False, 4


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
    
    # Get repo root
    repo_root = get_repo_root()
    
    # Handle lock-only commands (don't need full setup)
    if args.lock_status:
        return handle_lock_status(repo_root, args.json)
    
    if args.unlock_stale:
        return handle_unlock_stale(repo_root)
    
    # Resolve profile and scope
    profile, scope = resolve_profile_and_scope(args)
    
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
    
    # Handle ACT-local profile separately (bypasses lock and normal gate infrastructure)
    if profile == "act-local":
        # Check for wait-for-lock
        if args.wait_for_lock is not None:
            proceed, exit_code = handle_wait_for_lock(
                repo_root, 
                args.wait_for_lock, 
                profile
            )
            if not proceed:
                assert exit_code is not None
                return exit_code
        
        act_result = run_act_local_verification(json_mode=args.json)
        
        if args.json:
            print(act_local_format_json(act_result))
        else:
            print(format_human_output(act_result))
        
        return 0 if act_result.success else 1
    
    # For fast/full profiles, optionally wait for lock
    # After waiting, we MUST acquire the lock before proceeding
    lock: VerifyLock | None = None
    try:
        if args.wait_for_lock is not None:
            # First wait for the lock to be released
            proceed, exit_code = handle_wait_for_lock(
                repo_root, 
                args.wait_for_lock, 
                profile
            )
            if not proceed:
                assert exit_code is not None
                return exit_code
            
            # Lock was released - now acquire it before proceeding
            # This prevents races between wait completion and actual acquisition
            lock = acquire_verify_lock(repo_root, profile=profile)
        else:
            # Default: fail fast on lock contention with owner diagnostics
            lock = acquire_verify_lock(repo_root, profile=profile)
    except LockError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print("Hint: Run ./scripts/verify_all.sh --lock-status for diagnostics", file=sys.stderr)
        return 4
    # Set recursion guard
    set_recursion_guard()
    
    # Ensure runs directory exists
    (repo_root / "runs" / "verification").mkdir(parents=True, exist_ok=True)
    
    try:
        # Run standard verification (fast/full profiles)
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
        # Release the lock we acquired - NOT a new lock
        if lock is not None:
            lock.release()


if __name__ == "__main__":
    sys.exit(main())
