#!/usr/bin/env python3
"""
Verification Discipline Guard.

Mechanical guardrail that fails on repo-authored docs/prompts/rules that instruct
local agents to run broad checks by default.

It should reject default-local instructions containing:
- pytest tests/
- python -m pytest tests/
- bare pytest as local acceptance
- bare python -m pytest as local acceptance
- ./scripts/verify_all.sh --full
- bare ./scripts/verify_all.sh as local ACT acceptance
- rm -rf .verify_lock
- pkill -f

It should allow those only inside:
- explicit bad examples
- CI/manual sections
- human-authorized full verification sections

Usage:
    python scripts/verify_verification_discipline.py [--json]
    python scripts/verify_verification_discipline.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

REPO_ROOT = Path(__file__).parent.parent

# Files/directories to scan
SCAN_PATHS = [
    REPO_ROOT / "docs",
    REPO_ROOT / ".kilocode" / "rules",
    REPO_ROOT / "AGENTS.md",
]

# If there's a .clinerules directory
CLINERULES_DIR = REPO_ROOT / ".clinerules"
if CLINERULES_DIR.exists():
    SCAN_PATHS.append(CLINERULES_DIR)

# Patterns that indicate forbidden verification instructions
# These are patterns that should NOT appear in default-local sections
FORBIDDEN_PATTERNS = [
    # Broad pytest as default local acceptance
    (r'pytest\s+tests/', "pytest tests/", "Broad pytest suite"),
    (r'python\s+-m\s+pytest\s+tests/', "python -m pytest tests/", "Broad pytest suite"),
    (r'^pytest$', "^pytest$", "Bare pytest as local acceptance"),
    (r'^python\s+-m\s+pytest$', "^python -m pytest$", "Bare python -m pytest as local acceptance"),
    
    # Full gate as local acceptance
    (r'\./scripts/verify_all\.sh\s+--full', "./scripts/verify_all.sh --full", "Full gate as local acceptance"),
    (r'^verify_all\.sh$', "^verify_all.sh$", "Bare verify_all.sh as local ACT acceptance"),
    (r'\./scripts/verify_all\.sh$', "./scripts/verify_all.sh", "Bare verify_all.sh as local acceptance"),
    
    # Destructive operations
    (r'rm\s+-rf\s+\.verify_lock', "rm -rf .verify_lock", "Deletion of verify lock"),
    (r'pkill\s+-f', "pkill -f", "Process killing by pattern"),
]

# Section markers that indicate the content is NOT default-local
# Dangerous commands are allowed ONLY in explicit sections
ALLOWED_SECTION_MARKERS = [
    r'# Bad [Ee]xample',  # Explicit bad example (case insensitive)
    r'## CI',  # CI section
    r'## Manual',  # Manual section
    r'## Human',  # Human authorization section
    r'<!-- ',  # HTML comment start
    r'-->',  # HTML comment end
]


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class Violation:
    """A single violation of verification discipline."""
    file_path: str
    line_number: int
    line_content: str
    pattern: str
    description: str


@dataclass
class ScanResult:
    """Result from scanning for verification discipline violations."""
    success: bool
    violations: list[Violation]
    files_scanned: int
    errors: list[str]


# =============================================================================
# Scanning Logic
# =============================================================================

def is_in_excluded_section(content: str, line_num: int) -> bool:
    """Check if a line is within an excluded section (code block, example, etc.)."""
    lines = content.split('\n')
    
    # Find the nearest section marker before this line
    for i in range(line_num - 1, -1, -1):
        line = lines[i]
        for marker in ALLOWED_SECTION_MARKERS:
            if re.search(marker, line, re.IGNORECASE):
                # Check if we're still in this section
                # Look for end markers
                for j in range(i + 1, line_num):
                    if re.search(r'^```\s*$', lines[j]):
                        # Code block ended before our line
                        break
                else:
                    return True
        # Check for code block ending
        if re.match(r'^```\s*$', line):
            # Code block ended, we're past it
            break
    
    return False


def scan_file(file_path: Path) -> tuple[list[Violation], list[str]]:
    """Scan a single file for verification discipline violations.
    
    Returns (violations, errors).
    """
    violations: list[Violation] = []
    errors: list[str] = []
    
    try:
        content = file_path.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        errors.append(f"Error reading {file_path}: {e}")
        return violations, errors
    
    rel_path = str(file_path.relative_to(REPO_ROOT))
    is_clinerules = rel_path.startswith('.clinerules/')
    
    lines = content.split('\n')
    
    for line_num, line in enumerate(lines, start=1):
        # Skip comment-only lines (but not comment-annotated code)
        stripped = line.strip()
        if stripped.startswith('#') and not stripped.startswith('#: '):
            continue
        
        # Skip lines in excluded sections
        if is_in_excluded_section(content, line_num):
            continue
        
        # For .clinerules/ files, skip lines that appear to be documenting
        # forbidden commands (in tables, lists, or explicitly marked sections)
        if is_clinerules and is_documenting_forbidden_command(line):
            continue
        
        # Check for forbidden patterns
        for pattern, pattern_str, description in FORBIDDEN_PATTERNS:
            if re.search(pattern, line, re.MULTILINE):
                violations.append(Violation(
                    file_path=str(file_path.relative_to(REPO_ROOT)),
                    line_number=line_num,
                    line_content=line.strip()[:100],  # Truncate for display
                    pattern=pattern_str,
                    description=description,
                ))
    
    return violations, errors


def is_documenting_forbidden_command(line: str) -> bool:
    """Check if a line is documenting a forbidden command (not instructing to run it).
    
    This is allowed in rules files where we document what's forbidden.
    Returns True for:
    - Table rows (contain |)
    - List items documenting forbidden commands (start with - or * and contain backtick-wrapped commands)
    - Lines in sections explicitly documenting policy
    """
    stripped = line.strip()
    
    # Table rows in documentation
    if '|' in stripped:
        return True
    
    # List items documenting forbidden commands
    # Match patterns like: - `command`, - rm -rf .verify_lock, * `command`
    if stripped.startswith('- ') or stripped.startswith('* '):
        # Contains backtick-wrapped command (indicates documentation)
        if '`' in stripped:
            return True
        # Known forbidden command patterns in list items
        forbidden_patterns = ['rm -rf', 'pkill', 'pytest tests/', 'verify_all.sh --full']
        for pattern in forbidden_patterns:
            if pattern in stripped.lower():
                return True
    
    return False


def scan_directory(dir_path: Path) -> tuple[list[Violation], int]:
    """Scan a directory recursively for files to check.
    
    Returns (all_violations, files_scanned).
    """
    all_violations = []
    files_scanned = 0
    
    # File extensions to scan
    scan_extensions = {'.md', '.py', '.txt', '.rst', '.yml', '.yaml'}
    
    # Directories to skip
    skip_dirs = {'.git', '.venv', 'node_modules', '__pycache__', '.mypy_cache', '.ruff_cache'}
    
    for path in dir_path.rglob('*'):
        if path.is_dir():
            if any(skip in path.parts for skip in skip_dirs):
                continue
            continue
        
        if path.is_file() and path.suffix in scan_extensions:
            violations, errors = scan_file(path)
            all_violations.extend(violations)
            files_scanned += 1
    
    return all_violations, files_scanned


def scan_verification_discipline() -> ScanResult:
    """Run verification discipline scan.
    
    Returns ScanResult with violations and metadata.
    """
    all_violations = []
    total_files_scanned = 0
    all_errors = []
    
    for scan_path in SCAN_PATHS:
        if not scan_path.exists():
            continue
        
        if scan_path.is_file():
            violations, errors = scan_file(scan_path)
            all_violations.extend(violations)
            all_errors.extend(errors)
            total_files_scanned += 1
        elif scan_path.is_dir():
            violations, files = scan_directory(scan_path)
            all_violations.extend(violations)
            total_files_scanned += files
    
    success = len(all_violations) == 0
    
    return ScanResult(
        success=success,
        violations=all_violations,
        files_scanned=total_files_scanned,
        errors=all_errors,
    )


# =============================================================================
# Self-Test
# =============================================================================

def run_self_test() -> tuple[bool, list[str]]:
    """Run self-test validation.
    
    Returns (success, errors).
    """
    errors = []
    
    # Test 1: Generic code block with dangerous command (should be flagged)
    # Generic code blocks without explicit section markers are not allowed
    bad_code_block_content = '''
# Good Example

```bash
pytest tests/test_my_feature.py
```
'''
    violations, _ = scan_file_content(bad_code_block_content, "bad_code_block.md")
    if not violations:
        errors.append("Self-test: dangerous command in generic code block was NOT flagged")
    
    # Test 2: Bad example section (should NOT be flagged)
    bad_example_content = '''
# Bad Example

pytest tests/

This is a bad example showing what NOT to do.
'''
    violations, _ = scan_file_content(bad_example_content, "bad_example.md")
    if violations:
        errors.append(f"Self-test: bad example section was incorrectly flagged: {violations}")
    
    # Test 3: Full gate as local acceptance (should be flagged)
    bad_full_content = '''
# Verification

Run: ./scripts/verify_all.sh --full
'''
    violations, _ = scan_file_content(bad_full_content, "bad_full.md")
    if not violations:
        errors.append("Self-test: full gate as local acceptance was NOT flagged")
    
    # Test 4: rm -rf .verify_lock (should be flagged)
    bad_lock_content = '''
# Fix

rm -rf .verify_lock
'''
    violations, _ = scan_file_content(bad_lock_content, "bad_lock.md")
    if not violations:
        errors.append("Self-test: rm -rf .verify_lock was NOT flagged")
    
    # Test 5: pkill -f (should be flagged)
    bad_pkill_content = '''
# Cleanup

pkill -f verify
'''
    violations, _ = scan_file_content(bad_pkill_content, "bad_pkill.md")
    if not violations:
        errors.append("Self-test: pkill -f was NOT flagged")
    
    # Test 6: CI section (should NOT be flagged)
    ci_content = '''
## CI

Run pytest tests/ in CI pipeline.
'''
    violations, _ = scan_file_content(ci_content, "ci.md")
    if violations:
        errors.append(f"Self-test: CI section was incorrectly flagged: {violations}")
    
    # Test 7: Manual section (should NOT be flagged)
    manual_content = '''
## Manual

Run pytest tests/ manually.
'''
    violations, _ = scan_file_content(manual_content, "manual.md")
    if violations:
        errors.append(f"Self-test: Manual section was incorrectly flagged: {violations}")
    
    return len(errors) == 0, errors


def scan_file_content(content: str, name: str = "test.md") -> tuple[list[Violation], list[str]]:
    """Helper to scan content string as a file for testing."""
    
    violations: list[Violation] = []
    errors: list[str] = []
    lines = content.split('\n')
    
    for line_num, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith('#') and not stripped.startswith('#: '):
            continue
        
        if is_in_excluded_section(content, line_num):
            continue
        
        for pattern, pattern_str, description in FORBIDDEN_PATTERNS:
            if re.search(pattern, line, re.MULTILINE):
                violations.append(Violation(
                    file_path=name,
                    line_number=line_num,
                    line_content=line.strip()[:100],
                    pattern=pattern_str,
                    description=description,
                ))
    
    return violations, errors


# =============================================================================
# Output Formatting
# =============================================================================

def format_results(result: ScanResult, json_output: bool = False) -> str:
    """Format scan results for display."""
    if json_output:
        return json.dumps({
            "success": result.success,
            "files_scanned": result.files_scanned,
            "violations": [
                {
                    "file": v.file_path,
                    "line": v.line_number,
                    "content": v.line_content,
                    "pattern": v.pattern,
                    "description": v.description,
                }
                for v in result.violations
            ],
            "errors": result.errors,
        }, indent=2)
    
    lines = []
    lines.append("=" * 60)
    lines.append("Verification Discipline Check")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Files scanned: {result.files_scanned}")
    lines.append(f"Violations found: {len(result.violations)}")
    lines.append("")
    
    if result.errors:
        lines.append("Errors:")
        for error in result.errors:
            lines.append(f"  - {error}")
        lines.append("")
    
    if result.violations:
        lines.append("VIOLATIONS:")
        for v in result.violations:
            lines.append(f"  {v.file_path}:{v.line_number}")
            lines.append(f"    Pattern: {v.description}")
            lines.append(f"    Content: {v.line_content}")
        lines.append("")
    
    status = "PASSED" if result.success else "FAILED"
    lines.append("=" * 60)
    lines.append(f"Verification Discipline: {status}")
    lines.append("=" * 60)
    
    return '\n'.join(lines)


# =============================================================================
# CLI
# =============================================================================

def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verification Discipline Guard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--json', action='store_true', help='JSON output')
    parser.add_argument('--self-test', action='store_true', help='Run self-test validation')
    parser.add_argument('--changed-only', action='store_true', help='Scan only changed files')
    
    args = parser.parse_args()
    
    if args.self_test:
        print("Running self-test validation...")
        success, errors = run_self_test()
        if success:
            print("SELF-TEST: PASSED")
            return 0
        else:
            print("SELF-TEST: FAILED")
            for error in errors:
                print(f"  - {error}")
            return 1
    
    # Run scan
    if args.changed_only:
        # Scan only changed files
        result = scan_verification_discipline_changed_only()
    else:
        # Full repo scan
        result = scan_verification_discipline()
    
    # Format and print results
    print(format_results(result, json_output=args.json))
    
    return 0 if result.success else 1


def scan_verification_discipline_changed_only() -> ScanResult:
    """Scan only changed files for verification discipline violations.
    
    This is used by ACT-local to avoid failing on pre-existing violations.
    """
    # Get changed files
    changed = set()
    for cmd in [["git", "diff", "--name-only"], ["git", "diff", "--cached", "--name-only"]]:
        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    changed.add(line.strip())
    
    # Filter to docs/rules files only
    docs_rules_patterns = ['docs/', '.kilocode/rules/', 'AGENTS.md', '.clinerules/']
    changed_docs_rules = [
        f for f in changed
        if any(f.startswith(p) or f == p for p in docs_rules_patterns)
    ]
    
    if not changed_docs_rules:
        # No changed docs/rules, return empty success
        return ScanResult(
            success=True,
            violations=[],
            files_scanned=0,
            errors=[],
        )
    
    # Scan only changed files
    all_violations = []
    all_errors = []
    
    for file_path_str in changed_docs_rules:
        file_path = REPO_ROOT / file_path_str
        if file_path.exists():
            violations, errors = scan_file(file_path)
            all_violations.extend(violations)
            all_errors.extend(errors)
    
    return ScanResult(
        success=len(all_violations) == 0,
        violations=all_violations,
        files_scanned=len(changed_docs_rules),
        errors=all_errors,
    )


if __name__ == '__main__':
    sys.exit(main())
