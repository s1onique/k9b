#!/usr/bin/env python3
"""Static verifier to block unbounded kubectl get pods --all-namespaces -o json patterns.

This script enforces the bounded pod collection policy by scanning source code
for the exact pattern that caused OOM failures on large clusters:

    kubectl get pods --all-namespaces -o json
    kubectl get pods -A -o json
    _kubectl(context, "get", "pods", "--all-namespaces", "-o", "json")

The only exceptions are:
- Test files (tests/)
- Documentation (docs/)
- Fixtures (fixtures/)
- Scripts explicitly marked as test utilities
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Patterns that indicate unbounded all-namespace pod collection
# These are forbidden in production code paths (no label/field selectors allowed)
# Note: We intentionally DON'T match lines with -l (label) or -n (namespace) filters
# because those are scoped and don't cause OOM
FORBIDDEN_PATTERNS = [
    # Direct kubectl commands - ONLY match if no -l or -n flags are present
    re.compile(r'kubectl\s+get\s+pods\s+(-A|--all-namespaces)\s+(-o\s+json)?(?!\s+-l)(?!\s+-n)'),
    re.compile(r'kubectl\s+get\s+pods\s+-A\s+-o\s+json(?!\s+-l)'),
    
    # Python method calls with these exact arguments (unbounded)
    re.compile(r'["\']get["\']\s*,\s*["\']pods["\']\s*,\s*["\']--all-namespaces["\']\s*,\s*["\']-o["\']\s*,\s*["\']json["\']'),
    re.compile(r'["\']get["\']\s*,\s*["\']pods["\']\s*,\s*["\']-A["\']\s*,\s*["\']-o["\']\s*,\s*["\']json["\']'),
]

# Allowed directories (test fixtures, docs, etc.)
ALLOWED_DIRS = [
    "tests/",
    "docs/",
    "fixtures/",
    "evals/",
]

# File extensions that are scanned
SCANNED_EXTENSIONS = {".py"}


def is_allowed_path(path: str) -> bool:
    """Check if path is in an allowed directory."""
    for allowed in ALLOWED_DIRS:
        if allowed in path:
            return True
    return False


def scan_file(file_path: Path) -> list[tuple[int, str]]:
    """Scan a single file for forbidden patterns.
    
    Returns:
        List of (line_number, line_content) tuples for matching lines
    """
    matches = []
    try:
        with open(file_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                # Skip comments and docstrings entirely
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                
                # Skip lines that are only docstring delimiters
                if stripped in ('"""', "'''", 'r"""', "r'''"):
                    continue
                
                # Skip docstring content (lines that are inside triple quotes)
                # This is a simple heuristic - lines that contain the pattern
                # but are clearly documentation
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                
                for pattern in FORBIDDEN_PATTERNS:
                    if pattern.search(line):
                        # Extra check: skip if line has -l (label selector) or -n (namespace)
                        # as those are bounded queries (even when -l is followed by value directly)
                        if "-l" in line:
                            continue
                        if "-n" in line and "--all-namespaces" not in line and "-A" not in line:
                            # -n is namespace flag, but -A and --all-namespaces are different
                            continue
                        # Skip if this looks like a docstring reference
                        if "replaces" in line.lower() or "instead of" in line.lower():
                            continue
                        matches.append((line_num, line.rstrip()))
                        break
    except (OSError, UnicodeDecodeError):
        pass
    return matches


def scan_directory(root: Path) -> dict[str, list[tuple[int, str]]]:
    """Scan directory for forbidden patterns.
    
    Returns:
        Dict mapping file paths to list of (line_num, line) matches
    """
    results = {}
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix not in SCANNED_EXTENSIONS:
            continue
        
        relative_path = str(file_path.relative_to(root))
        if is_allowed_path(relative_path):
            continue
        
        matches = scan_file(file_path)
        if matches:
            results[relative_path] = matches
    
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify no unbounded kubectl pod JSON collection patterns exist"
    )
    parser.add_argument(
        "--src-dir",
        type=Path,
        default=Path("src"),
        help="Source directory to scan (default: src)",
    )
    parser.add_argument(
        "--fail",
        action="store_true",
        help="Exit with failure if violations found",
    )
    args = parser.parse_args()

    if not args.src_dir.exists():
        print(f"Source directory not found: {args.src_dir}")
        return 0  # Don't fail if directory doesn't exist

    results = scan_directory(args.src_dir)
    
    if not results:
        print("✓ No unbounded pod JSON collection patterns found")
        return 0
    
    print("✗ Found forbidden unbounded pod collection patterns:")
    print()
    for file_path, matches in sorted(results.items()):
        print(f"  {file_path}:")
        for line_num, line in matches:
            print(f"    Line {line_num}: {line[:80]}...")
        print()
    
    if args.fail:
        print(f"FAILED: Found {sum(len(m) for m in results.values())} violations")
        return 1
    
    print(f"Warning: Found {sum(len(m) for m in results.values())} violations (--fail not set)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
