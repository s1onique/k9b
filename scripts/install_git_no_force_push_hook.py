#!/usr/bin/env python3
"""
Git pre-push hook installer for no-force-push policy.

This script installs the pre-push guard into .git/hooks/pre-push.
It safely handles existing hooks by wrapping them or refusing with instructions.

Usage:
    python scripts/install_git_no_force_push_hook.py        # Install
    python scripts/install_git_no_force_push_hook.py --check  # Check status
    python scripts/install_git_no_force_push_hook.py --uninstall  # Remove
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

# Sentinel markers for managed hooks
MANAGED_START = "# === MANAGED BY NO-FORCE-PUSH GUARD START ==="
MANAGED_END = "# === MANAGED BY NO-FORCE-PUSH GUARD END ==="


def get_hook_content(guard_path: Path) -> str:
    """Generate the pre-push hook content."""
    return f'''#!/usr/bin/env bash
# Pre-push hook installed by install_git_no_force_push_hook.py
# Policy: docs/doctrine/no-force-push.md

{MANAGED_START}

# Run the no-force-push guard
exec python {guard_path} "$@"

{MANAGED_END}
'''


def is_managed_hook(path: Path) -> bool:
    """Check if a hook file is managed by this installer."""
    if not path.exists():
        return False
    
    try:
        content = path.read_text()
        return MANAGED_START in content
    except OSError:
        return False


def is_compatible_existing_hook(path: Path) -> bool:
    """Check if existing hook can be safely wrapped."""
    if not path.exists():
        return True
    
    try:
        content = path.read_text()
        
        # Empty file
        if not content.strip():
            return True
        
        # Already managed by us
        if is_managed_hook(path):
            return True
        
        # Check for shebang
        lines = content.split('\n')
        shebang_lines = [line for line in lines if line.startswith('#!')]
        
        # If no shebang, we could potentially wrap
        if not shebang_lines:
            return True
        
        # Check if it's a simple Python script we understand
        for line in shebang_lines:
            if 'python' in line.lower():
                # Python script - check if it's simple enough to chain
                # We won't auto-wrap, but we won't refuse
                return True
        
        return False
        
    except OSError:
        return False


def install_hook(repo_root: Path | None = None, force: bool = False) -> tuple[bool, str]:
    """
    Install the pre-push hook.
    
    Args:
        repo_root: Repository root (defaults to cwd)
        force: Overwrite existing unmanaged hook
    
    Returns:
        Tuple of (success, message)
    """
    if repo_root is None:
        repo_root = Path.cwd()
    
    git_dir = repo_root / ".git"
    if not git_dir.exists():
        return False, f"Not a git repository: {repo_root}"
    
    hooks_dir = git_dir / "hooks"
    hook_path = hooks_dir / "pre-push"
    guard_path = Path(__file__).resolve()
    
    # Check existing hook
    if hook_path.exists() and not is_managed_hook(hook_path):
        if not force:
            if not is_compatible_existing_hook(hook_path):
                return False, (
                    f"Existing pre-push hook is incompatible.\n"
                    f"  Path: {hook_path}\n"
                    f"Please manually integrate or remove the existing hook, then re-run.\n"
                    f"Use --force to overwrite (existing content will be lost)."
                )
            else:
                return False, (
                    f"Existing pre-push hook found at {hook_path}.\n"
                    f"  Use --force to overwrite (existing content will be lost).\n"
                    f"  Or manually integrate the guard into your existing hook."
                )
    
    # Create hooks directory if needed
    hooks_dir.mkdir(parents=True, exist_ok=True)
    
    # Write the hook
    content = get_hook_content(guard_path)
    hook_path.write_text(content)
    
    # Make executable
    mode = hook_path.stat().st_mode
    hook_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    
    return True, f"Pre-push hook installed at {hook_path}"


def uninstall_hook(repo_root: Path | None = None) -> tuple[bool, str]:
    """Remove the pre-push hook installed by this script."""
    if repo_root is None:
        repo_root = Path.cwd()
    
    git_dir = repo_root / ".git"
    hook_path = git_dir / "hooks" / "pre-push"
    
    if not hook_path.exists():
        return True, "No hook installed"
    
    if not is_managed_hook(hook_path):
        return False, (
            f"Hook at {hook_path} is not managed by this installer.\n"
            f"Manual removal required."
        )
    
    try:
        hook_path.unlink()
        return True, f"Hook removed from {hook_path}"
    except OSError as e:
        return False, f"Failed to remove hook: {e}"


def check_hook_status(repo_root: Path | None = None) -> tuple[bool, str]:
    """Check the status of the pre-push hook."""
    if repo_root is None:
        repo_root = Path.cwd()
    
    git_dir = repo_root / ".git"
    hook_path = git_dir / "hooks" / "pre-push"
    
    if not hook_path.exists():
        return False, "Pre-push hook not installed"
    
    if is_managed_hook(hook_path):
        return True, f"Pre-push hook installed (managed by installer): {hook_path}"
    
    return False, f"Pre-push hook exists but not managed by installer: {hook_path}"


def main() -> int:
    """Entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Install/uninstall/check git pre-push guard",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check hook status only",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove the installed hook",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing hook",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: cwd)",
    )
    
    args = parser.parse_args()
    
    if args.check:
        success, message = check_hook_status(args.repo_root)
        print(message)
        return 0 if success else 1
    
    if args.uninstall:
        success, message = uninstall_hook(args.repo_root)
        print(message)
        return 0 if success else 1
    
    success, message = install_hook(args.repo_root, force=args.force)
    print(message)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
