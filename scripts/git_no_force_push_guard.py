#!/usr/bin/env python3
"""
Git pre-push guard against force-push and history rewrite operations.

This module provides the core logic for detecting dangerous git push operations
before they leave the local repository.

Usage:
    # As a git hook (reads from stdin):
    python scripts/git_no_force_push_guard.py
    
    # As a library:
    from git_no_force_push_guard import check_push, parse_pre_push_stdin, GuardResult

Exit codes:
    0 - Push allowed
    1 - Push blocked (dangerous operation detected)
    2 - Configuration error
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

# Default protected branches (can be overridden by config file)
DEFAULT_PROTECTED_REFS = [
    "refs/heads/main",
    "refs/heads/master",
    "refs/heads/release/",
    "refs/heads/deploy/",
]

# Banned command-line flags
BANNED_FLAGS = frozenset([
    "--force",
    "-f",
    "--force-with-lease",
    "--force-if-includes",
    "--mirror",
    "--delete",
])

# Banned patterns in refspecs
BANNED_REFSPEC_PATTERNS = [
    re.compile(r"^\+"),  # Force prefix
    re.compile(r":$"),     # Delete pattern (src:)
]


@dataclass
class GuardResult:
    """Result from a push guard check."""
    allowed: bool
    reason: str | None = None
    details: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "details": self.details,
        }


def load_protected_refs_config() -> list[str]:
    """Load protected refs from configuration file."""
    config_paths = [
        Path("docs/policy/no-force-push-protected-refs.json"),
        Path(__file__).parent.parent / "docs/policy/no-force-push-protected-refs.json",
    ]
    
    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                refs: list[str] = config.get("protected_refs", DEFAULT_PROTECTED_REFS)
                return refs
            except (json.JSONDecodeError, OSError):
                pass
    
    return DEFAULT_PROTECTED_REFS


def is_protected_ref(ref: str, protected_refs: list[str]) -> bool:
    """Check if a ref is protected based on protected ref patterns."""
    for pattern in protected_refs:
        if pattern.endswith("/*"):
            # Wildcard pattern with /* suffix - check if ref starts with prefix
            prefix = pattern[:-2]  # Remove /*
            if ref.startswith(prefix + "/") or ref == prefix:
                return True
        elif pattern.endswith("/"):
            # Wildcard pattern with / suffix - check if ref starts with prefix
            prefix = pattern[:-1]  # Remove trailing /
            if ref.startswith(prefix + "/") or ref == prefix:
                return True
        elif ref == pattern:
            return True
    return False


def check_command_line_args(args: list[str]) -> GuardResult | None:
    """Check command-line arguments for banned force-push flags.
    
    Returns None if no banned flags found, or a GuardResult if blocked.
    """
    for arg in args:
        if arg in BANNED_FLAGS:
            return GuardResult(
                allowed=False,
                reason=f"Banned flag detected: {arg}",
                details={"flag": arg, "operation": "force_push"},
            )
        
        # Check for refspecs with + prefix in arguments
        for pattern in BANNED_REFSPEC_PATTERNS:
            if pattern.search(arg):
                return GuardResult(
                    allowed=False,
                    reason=f"Banned refspec pattern detected: {arg}",
                    details={"refspec": arg, "operation": "force_push"},
                )
    
    return None


def parse_pre_push_stdin(stdin: TextIO | None = None) -> list[tuple[str, str, str, str]]:
    """Parse pre-push hook input from stdin.
    
    Input format:
        <local ref> <local sha1> <remote ref> <remote sha1>
    
    Returns list of tuples: (local_ref, local_sha, remote_ref, remote_sha)
    """
    if stdin is None:
        stdin = sys.stdin
    
    refs = []
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        
        parts = line.split()
        if len(parts) == 4:
            local_ref, local_sha, remote_ref, remote_sha = parts
            refs.append((local_ref, local_sha, remote_ref, remote_sha))
    
    return refs


def check_stdin_updates(
    refs: list[tuple[str, str, str, str]],
    protected_refs: list[str],
    skip_sha_checks: bool = True,
) -> GuardResult | None:
    """Check pre-push stdin updates for dangerous operations.
    
    Args:
        refs: List of (local_ref, local_sha, remote_ref, remote_sha) tuples
        protected_refs: List of protected ref patterns
        skip_sha_checks: Skip SHA validation (requires local git access)
    
    Returns None if no danger detected, or a GuardResult if blocked.
    """
    for local_ref, local_sha, remote_ref, remote_sha in refs:
        # Check for branch deletion (all zeros SHA)
        if local_sha == "0" * 40 or remote_sha == "0" * 40:
            if is_protected_ref(remote_ref, protected_refs):
                return GuardResult(
                    allowed=False,
                    reason=f"Branch deletion detected on protected ref: {remote_ref}",
                    details={
                        "operation": "deletion",
                        "local_sha": local_sha,
                        "remote_sha": remote_sha,
                        "ref": remote_ref,
                    },
                )
        
        # Check for protected ref updates
        if is_protected_ref(remote_ref, protected_refs):
            # All-zeros local SHA means deletion
            if local_sha == "0" * 40:
                return GuardResult(
                    allowed=False,
                    reason=f"Deletion of protected ref: {remote_ref}",
                    details={
                        "operation": "deletion",
                        "ref": remote_ref,
                    },
                )
            
            # Without SHA validation, we must fail closed for protected refs
            # unless this is a new branch (remote_sha is all zeros means new)
            if remote_sha != "0" * 40 and skip_sha_checks:
                # We can't determine if this is fast-forward without SHA validation
                # For protected refs, require fast-forward or fail closed
                return GuardResult(
                    allowed=False,
                    reason=(
                        f"Cannot verify fast-forward for protected ref {remote_ref}. "
                        "SHA validation requires local git access."
                    ),
                    details={
                        "operation": "protected_ref_update",
                        "ref": remote_ref,
                        "note": "fail_closed",
                    },
                )
    
    return None


def check_push(
    args: list[str] | None = None,
    stdin: TextIO | None = None,
    protected_refs: list[str] | None = None,
    skip_sha_checks: bool = True,
) -> GuardResult:
    """
    Main guard function that checks for dangerous push operations.
    
    Args:
        args: Command-line arguments (sys.argv[1:])
        stdin: Input stream for pre-push data
        protected_refs: List of protected ref patterns
        skip_sha_checks: Skip SHA-based fast-forward checks
    
    Returns GuardResult indicating whether push is allowed.
    """
    if protected_refs is None:
        protected_refs = load_protected_refs_config()
    
    # Check command-line arguments first
    if args:
        result = check_command_line_args(args)
        if result:
            return result
    
    # Parse and check stdin updates
    refs = parse_pre_push_stdin(stdin)
    if refs:
        result = check_stdin_updates(refs, protected_refs, skip_sha_checks)
        if result:
            return result
    
    # Allow the push
    return GuardResult(
        allowed=True,
        reason="No dangerous operations detected",
        details={"refs_checked": len(refs)},
    )


def main() -> int:
    """Entry point for git hook execution."""
    # Read stdin
    stdin_lines = sys.stdin.read()
    
    # Re-parse with our captured input
    import io
    stdin_stream = io.StringIO(stdin_lines)
    
    # Check push
    result = check_push(
        args=sys.argv[1:] if len(sys.argv) > 1 else None,
        stdin=stdin_stream,
    )
    
    if not result.allowed:
        print("ERROR: Push blocked by no-force-push guard", file=sys.stderr)
        print(f"Reason: {result.reason}", file=sys.stderr)
        if result.details:
            print(f"Details: {json.dumps(result.details)}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
