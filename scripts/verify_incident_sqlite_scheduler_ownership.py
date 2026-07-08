#!/usr/bin/env python3
"""Static verifier for incident SQLite scheduler ownership.

This script verifies that scheduler/health-loop modules do not directly import
or call SQLite store primitives, ensuring proper promotion via backend API.

Usage:
    python scripts/verify_incident_sqlite_scheduler_ownership.py

Exit codes:
    0: All checks passed
    1: Violations found

Integration:
    Gate target: make verify-incident-scheduler-backend-api
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

# Patterns that indicate forbidden direct SQLite usage in scheduler promotion path
FORBIDDEN_PATTERNS = [
    # Direct SQLite store imports (scheduler-specific paths)
    (r"from.*incident_store_sqlite.*import", "Direct SQLiteIncidentStore import"),
    (r"import\s+sqlite3", "Direct sqlite3 module import"),
    (r"create_sqlite_store\s*\(", "Direct create_sqlite_store() call"),
    (r"SQLiteIncidentStore\s*\(", "Direct SQLiteIncidentStore instantiation"),
    # Scheduler promotion path direct store access
    (r"get_incident_store\s*\(\s*\)\s*\.\s*promote_candidates", 
     "Direct store promotion in scheduler path"),
    (r"get_incident_store\s*\(\s*\)\s*\.\s*promote_alert_signals",
     "Direct alert signal promotion via store"),
]

# Paths that are allowed to use SQLite directly
ALLOWED_PATHS = [
    # Backend/internal handlers own SQLite
    r"src/k8s_diag_agent/ui/server_incident_internal",
    r"src/k8s_diag_agent/collect/incident_store_sqlite",
    # Provider role guards
    r"src/k8s_diag_agent/collect/incident_store_provider",
    # Tests are allowed
    r"tests/",
    # Incident promotion dispatcher is the correct path
    r"src/k8s_diag_agent/collect/incident_promotion_dispatch",
    # Candidate serialization
    r"src/k8s_diag_agent/collect/incident_candidate_serialization",
]

# Scheduler-specific paths that should NOT have direct SQLite access
SCHEDULER_PATHS = [
    r"src/k8s_diag_agent/health/",
    r"src/k8s_diag_agent/scheduler/",
]


class Violation(NamedTuple):
    """Represents a policy violation."""
    file_path: str
    line_number: int
    line_content: str
    violation_type: str


def is_allowed_path(file_path: str) -> bool:
    """Check if the file path is allowed to use SQLite directly."""
    for pattern in ALLOWED_PATHS:
        if re.search(pattern, file_path):
            return True
    return False


def is_scheduler_path(file_path: str) -> bool:
    """Check if the file is a scheduler/health-loop module."""
    for pattern in SCHEDULER_PATHS:
        if re.search(pattern, file_path):
            return True
    return False


def check_file(file_path: Path) -> list[Violation]:
    """Check a single file for policy violations.
    
    Args:
        file_path: Path to the Python file to check
        
    Returns:
        List of violations found
    """
    violations: list[Violation] = []
    
    if file_path.suffix != ".py":
        return violations
        
    if not is_scheduler_path(str(file_path)):
        # Only check scheduler/health-loop paths
        return violations
    
    if is_allowed_path(str(file_path)):
        # Allowed paths don't need checking
        return violations
    
    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"WARNING: Could not read {file_path}: {e}", file=sys.stderr)
        return violations
    
    for line_num, line in enumerate(content.splitlines(), start=1):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        
        for pattern, violation_type in FORBIDDEN_PATTERNS:
            if re.search(pattern, line):
                violations.append(Violation(
                    file_path=str(file_path),
                    line_number=line_num,
                    line_content=line.strip(),
                    violation_type=violation_type,
                ))
    
    return violations


def check_directory(base_path: Path) -> list[Violation]:
    """Recursively check all Python files in a directory.
    
    Args:
        base_path: Base directory to check
        
    Returns:
        List of all violations found
    """
    violations = []
    
    for item in base_path.rglob("*.py"):
        # Skip test files and __pycache__
        if "__pycache__" in str(item):
            continue
        if item.name.startswith("test_") or item.name.endswith("_test.py"):
            continue
            
        violations.extend(check_file(item))
    
    return violations


def main() -> int:
    """Main entry point."""
    # Determine project root
    script_dir = Path(__file__).parent.resolve()
    project_root = script_dir.parent
    
    src_dir = project_root / "src"
    
    print("=" * 70)
    print("Incident SQLite Scheduler Ownership Verifier")
    print("=" * 70)
    print()
    print("Checking that scheduler/health-loop modules do not directly")
    print("access SQLite store primitives...")
    print()
    
    violations = check_directory(src_dir)
    
    if not violations:
        print("PASSED: No policy violations found")
        print()
        print("Scheduler promotion paths correctly use incident_promotion_dispatch")
        print("instead of direct SQLite access.")
        return 0
    
    print(f"FAILED: Found {len(violations)} policy violation(s)")
    print()
    print("Violations:")
    print("-" * 70)
    
    for v in violations:
        print(f"  File: {v.file_path}")
        print(f"  Line: {v.line_number}")
        print(f"  Type: {v.violation_type}")
        print(f"  Code: {v.line_content}")
        print()
    
    print("-" * 70)
    print()
    print("Fix: Use incident_promotion_dispatch module for promotion instead")
    print("      of direct SQLite store access in scheduler/health-loop paths.")
    print()
    print("Correct usage:")
    print("  from k8s_diag_agent.collect.incident_promotion_dispatch import (")
    print("      promote_candidates,")
    print("      promote_alert_signals,")
    print("  )")
    
    return 1


if __name__ == "__main__":
    sys.exit(main())
