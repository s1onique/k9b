#!/usr/bin/env python3
"""
Regression guard: Ensure no src.k8s_diag_agent imports exist.

This verifier prevents the src/ layout anti-pattern where code imports from
'src.k8s_diag_agent' instead of the canonical 'k8s_diag_agent' package.

The repo uses Python src/ layout:
- Source root: src/
- Import package: k8s_diag_agent (NOT src.k8s_diag_agent)

Patterns that are forbidden because they create duplicate module mappings for mypy:
  from src.k8s_diag_agent.* import ...
  import src.k8s_diag_agent.*
  from src.k8s_diag_agent import ...

Usage:
    python scripts/verify_package_import_hygiene.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Patterns that match forbidden imports
FORBIDDEN_PATTERNS = [
    re.compile(r'^\s*from\s+src\.k8s_diag_agent\b'),
    re.compile(r'^\s*import\s+src\.k8s_diag_agent\b'),
]

# Files and directories to scan
SCAN_PATHS = [
    Path("src"),
    Path("tests"),
    Path("scripts"),
]

# Extensions to scan
SCAN_EXTENSIONS = {".py"}

# Directories to skip
SKIP_DIRS = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    "node_modules",
    ".pytest_cache",
    "coverage_html",
}

# Files to skip (the verifier itself)
SKIP_FILES = {
    "verify_package_import_hygiene.py",
}


def check_file(path: Path) -> list[str]:
    """Check a single file for forbidden imports."""
    errors = []
    
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return errors  # Skip binary or unreadable files
    
    for line_num, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        # Skip comments
        if stripped.startswith("#"):
            continue
        
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.match(stripped):
                errors.append(
                    f"  {path}:{line_num}: Forbidden import pattern: {stripped}"
                )
    
    return errors


def scan_directory(root: Path) -> list[str]:
    """Recursively scan a directory for forbidden imports."""
    errors = []
    
    for path in root.rglob("*"):
        # Skip directories
        if path.is_dir():
            continue
        
        # Skip based on name
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        
        # Skip specific files
        if path.name in SKIP_FILES:
            continue
        
        # Only scan Python files
        if path.suffix not in SCAN_EXTENSIONS:
            continue
        
        errors.extend(check_file(path))
    
    return errors


def main() -> int:
    """Main entry point."""
    errors: list[str] = []
    
    for scan_path in SCAN_PATHS:
        if not scan_path.exists():
            print(f"WARNING: Skipping missing path: {scan_path}", file=sys.stderr)
            continue
        
        if scan_path.is_file():
            errors.extend(check_file(scan_path))
        else:
            errors.extend(scan_directory(scan_path))
    
    if errors:
        print("PACKAGE IMPORT HYGIENE: FAIL")
        print()
        print("Found forbidden src.k8s_diag_agent imports:")
        print()
        for error in errors:
            print(error)
        print()
        print(
            "The repository uses Python src/ layout. "
            "Import from 'k8s_diag_agent', not 'src.k8s_diag_agent'."
        )
        return 1
    
    print("PACKAGE IMPORT HYGIENE: PASS")
    print("No src.k8s_diag_agent imports found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
