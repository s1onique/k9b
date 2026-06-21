#!/usr/bin/env python3
"""
Shell Containment Verifier.

Enforces shell containment policy by:
1. Scanning for shell scripts in the repository
2. Validating against the inventory
3. Classifying/risk-scoring based on complex patterns
4. Failing on unregistered shell scripts
5. Failing on shim scripts with complex patterns
6. Verifying verify_all.sh remains shim-only

Usage:
    python scripts/verify_shell_containment.py           # Run verification
    python scripts/verify_shell_containment.py --json    # JSON output
    python scripts/verify_shell_containment.py --self-test  # Self-test mode
    python scripts/verify_shell_containment.py --verbose # Detailed output
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


# =============================================================================
# Configuration
# =============================================================================

REPO_ROOT = Path(__file__).parent.parent
INVENTORY_PATH = REPO_ROOT / "docs/tooling/shell-containment-inventory.csv"
VERIFY_ALL_SH = REPO_ROOT / "scripts/verify_all.sh"

# Patterns that indicate complex shell (high risk)
COMPLEX_PATTERNS = [
    # Loops - HIGH risk
    (r'\bwhile\s+\S', 'while loop', 'HIGH'),
    (r'\buntil\s+\S', 'until loop', 'HIGH'),
    (r'\bfor\s+\S+\s+in\b', 'for-in loop', 'HIGH'),
    
    # Arrays and data structures - HIGH risk
    (r'declare\s+-[aA]', 'array declaration', 'HIGH'),
    (r'\${[a-zA-Z_][a-zA-Z0-9_]*\[@\]}', 'array expansion', 'HIGH'),
    (r'\bmapfile\b', 'mapfile/array builtin', 'HIGH'),
    (r'\breadarray\b', 'readarray builtin', 'HIGH'),
    
    # Case statements - MEDIUM risk
    (r'\bcase\b.*\bin\b', 'case statement', 'MEDIUM'),
    
    # Data parsing - HIGH risk
    (r'\bjq\s+', 'jq invocation', 'HIGH'),
    (r'\bawk\s+', 'awk invocation', 'HIGH'),
    (r'\bsed\s+-[efnr]', 'sed with complex flags', 'HIGH'),
    (r'\bgrep\s+-[A-Za-z]*[A-Z]', 'grep with complex flags', 'MEDIUM'),
    
    # Temp files and IPC - MEDIUM risk
    (r'\bmktemp\b', 'mktemp usage', 'MEDIUM'),
    (r'/tmp/', 'temp file path', 'MEDIUM'),
    
    # Network calls - HIGH risk
    (r'\bcurl\s+', 'curl invocation', 'HIGH'),
    (r'\bwget\s+', 'wget invocation', 'HIGH'),
    
    # Signal and state management - HIGH risk
    (r'\btrap\b', 'trap signal handler', 'HIGH'),
    (r'\blocks?\b', 'lock/mutex', 'HIGH'),
    (r'\bsemaphore\b', 'semaphore', 'HIGH'),
    
    # Heredocs with logic - HIGH risk
    (r'<<-?\s*[\'\"]?\w+[\'\"]?', 'heredoc', 'MEDIUM'),
    
    # Retry and polling - HIGH risk
    (r'\bretry\b', 'retry logic', 'HIGH'),
    (r'\bbackoff\b', 'backoff logic', 'HIGH'),
    (r'\bpolling\b', 'polling logic', 'HIGH'),
    
    # Complex conditionals - MEDIUM risk
    (r'\[\[\s*.*&&', 'compound conditional AND', 'MEDIUM'),
    (r'\[\[\s*.*\|\|', 'compound conditional OR', 'MEDIUM'),
    (r'\[\[.*==.*\]\]/', 'pattern matching', 'MEDIUM'),
    
    # Subshells and process substitution - MEDIUM risk
    (r'\(\s*\$', 'command substitution in subshell', 'MEDIUM'),
    (r'<\s*\([^)]+\)', 'process substitution', 'MEDIUM'),
]

# Critical scripts that must remain shim-only
CRITICAL_SHIM_ONLY = [
    'scripts/verify_all.sh',
]


# =============================================================================
# Data Models
# =============================================================================

class Classification(str, Enum):
    SHIM = "shim"
    LEGACY_DEBT = "legacy-debt"
    BLOCKED = "blocked"


class MigrationStatus(str, Enum):
    REGISTERED = "registered"
    MIGRATED = "migrated"
    PENDING = "pending"
    DEFERRED = "deferred"
    DONE = "done"  # Alias for migrated, used for completed migrations


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class InventoryEntry:
    path: str
    classification: Classification
    owner: str
    reason: str
    target_language: str
    migration_status: MigrationStatus
    follow_up_act: str


@dataclass
class ShellScript:
    path: Path
    relative_path: str
    line_count: int
    detected_patterns: list[tuple[str, str, str]] = field(default_factory=list)
    is_complex: bool = False
    risk_score: int = 0
    risk_level: RiskLevel = RiskLevel.LOW


@dataclass
class VerificationResult:
    success: bool
    total_scripts: int
    registered_scripts: int
    unregistered_scripts: int
    complex_shims: int
    verify_all_violations: list[str] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# =============================================================================
# Pattern Detection
# =============================================================================

def detect_complex_patterns(content: str) -> list[tuple[str, str, str]]:
    """Detect complex shell patterns in content."""
    findings = []
    for pattern, description, risk in COMPLEX_PATTERNS:
        if re.search(pattern, content, re.MULTILINE):
            findings.append((pattern, description, risk))
    return findings


def calculate_risk_score(findings: list[tuple[str, str, str]]) -> int:
    """Calculate risk score from findings."""
    score = 0
    for _, _, risk in findings:
        if risk == "HIGH":
            score += 3
        elif risk == "MEDIUM":
            score += 1
    return score


def get_risk_level(score: int) -> RiskLevel:
    """Get risk level from score."""
    if score >= 5:
        return RiskLevel.HIGH
    elif score >= 2:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def is_shim_compliant(content: str, max_lines: int = 50) -> tuple[bool, list[str]]:
    """
    Check if shell content is shim-compliant.
    
    A shim should be:
    - Under max_lines
    - Only contain allowed patterns
    - NOT contain complex patterns
    """
    violations = []
    lines = content.split('\n')
    
    # Remove comments and empty lines for analysis
    code_lines = [l.strip() for l in lines if l.strip() and not l.strip().startswith('#')]
    
    if len(code_lines) > max_lines:
        violations.append(f"Exceeds {max_lines} lines of code ({len(code_lines)} non-comment lines)")
    
    # Check for complex patterns
    findings = detect_complex_patterns(content)
    if findings:
        for pattern, description, risk in findings:
            violations.append(f"Complex pattern: {description} ({risk} risk)")
    
    return len(violations) == 0, violations


def scan_shell_file(path: Path) -> ShellScript:
    """Scan a shell file and return analysis."""
    try:
        content = path.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        return ShellScript(
            path=path,
            relative_path=str(path.relative_to(REPO_ROOT)),
            line_count=0,
            detected_patterns=[("read_error", f"Error reading file: {e}", "LOW")]
        )
    
    lines = content.split('\n')
    findings = detect_complex_patterns(content)
    risk_score = calculate_risk_score(findings)
    
    return ShellScript(
        path=path,
        relative_path=str(path.relative_to(REPO_ROOT)),
        line_count=len(lines),
        detected_patterns=findings,
        is_complex=len(findings) > 0 or len([l for l in lines if l.strip() and not l.strip().startswith('#')]) > 50,
        risk_score=risk_score,
        risk_level=get_risk_level(risk_score),
    )


def find_shell_scripts(repo_root: Path) -> list[Path]:
    """Find all shell scripts in the repository."""
    patterns = ['*.sh', '*.bash']
    exclude_dirs = {'.venv', 'node_modules', '.git', '__pycache__', '.tox', '.mypy_cache', '.ruff_cache'}
    
    scripts = []
    for pattern in patterns:
        for path in repo_root.rglob(pattern):
            # Check if path is in excluded directory
            if any(excluded in path.parts for excluded in exclude_dirs):
                continue
            scripts.append(path)
    
    return sorted(scripts)


# =============================================================================
# Inventory Management
# =============================================================================

def load_inventory(path: Path) -> dict[str, InventoryEntry]:
    """Load inventory from CSV file."""
    entries = {}
    
    if not path.exists():
        return entries
    
    with path.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                entry = InventoryEntry(
                    path=row['path'],
                    classification=Classification(row['classification']),
                    owner=row['owner'],
                    reason=row['reason'],
                    target_language=row['target_language'],
                    migration_status=MigrationStatus(row['migration_status']),
                    follow_up_act=row['follow_up_act'],
                )
                entries[row['path']] = entry
            except (KeyError, ValueError) as e:
                # Skip malformed rows
                continue
    
    return entries


def check_verify_all_shim(content: str) -> list[str]:
    """Verify verify_all.sh is shim-only."""
    violations = []
    
    # Must contain exec to Python
    if 'exec' not in content.lower():
        violations.append("Missing 'exec' delegation to verify_all.py")
    
    if 'verify_all.py' not in content:
        violations.append("Missing delegation to verify_all.py")
    
    # Check for forbidden patterns (complex logic)
    forbidden_in_shim = [
        ('case ', 'case statement'),
        ('while ', 'while loop'),
        ('for ', 'for loop'),
        ('STEP_PROFILE=', 'profile variable'),
        ('STEP_SCOPE=', 'scope variable'),
        ('step_runner.sh', 'step runner sourcing'),
    ]
    
    # Remove comment lines for pattern check
    code_lines = [l for l in content.split('\n') if not l.strip().startswith('#')]
    code_only = '\n'.join(code_lines)
    
    for pattern, description in forbidden_in_shim:
        if pattern in code_only:
            violations.append(f"Forbidden in shim: {description}")
    
    return violations


# =============================================================================
# Verification Logic
# =============================================================================

def verify_shell_containment() -> VerificationResult:
    """Run shell containment verification."""
    errors = []
    findings = []
    
    # Find all shell scripts
    scripts = find_shell_scripts(REPO_ROOT)
    
    # Load inventory
    inventory = load_inventory(INVENTORY_PATH)
    
    unregistered = []
    complex_shims = []
    verify_all_violations = []
    
    for script_path in scripts:
        rel_path = str(script_path.relative_to(REPO_ROOT))
        analysis = scan_shell_file(script_path)
        
        # Check if registered
        if rel_path not in inventory:
            unregistered.append(rel_path)
            findings.append({
                'path': rel_path,
                'status': 'UNREGISTERED',
                'line_count': analysis.line_count,
                'risk_level': analysis.risk_level.value,
                'patterns': [p[1] for p in analysis.detected_patterns],
            })
            continue
        
        entry = inventory[rel_path]
        
        # Check shim compliance
        if entry.classification == Classification.SHIM:
            content = script_path.read_text(encoding='utf-8', errors='replace')
            is_compliant, violations = is_shim_compliant(content)
            
            if not is_compliant:
                complex_shims.append(rel_path)
                findings.append({
                    'path': rel_path,
                    'status': 'SHIM_VIOLATION',
                    'violations': violations,
                    'line_count': analysis.line_count,
                    'patterns': [p[1] for p in analysis.detected_patterns],
                })
            else:
                findings.append({
                    'path': rel_path,
                    'status': 'OK',
                    'classification': 'shim',
                })
        
        # Check legacy-debt scripts (informational only)
        elif entry.classification == Classification.LEGACY_DEBT:
            findings.append({
                'path': rel_path,
                'status': 'DEBT',
                'classification': 'legacy-debt',
                'line_count': analysis.line_count,
                'risk_level': analysis.risk_level.value,
                'risk_score': analysis.risk_score,
                'patterns': [p[1] for p in analysis.detected_patterns],
                'migration_status': entry.migration_status.value,
                'owner': entry.owner,
            })
    
    # Check verify_all.sh specifically
    if VERIFY_ALL_SH.exists():
        content = VERIFY_ALL_SH.read_text(encoding='utf-8')
        violations = check_verify_all_shim(content)
        if violations:
            verify_all_violations = violations
            errors.append(f"verify_all.sh shim violation: {'; '.join(violations)}")
    
    # Determine success
    success = len(unregistered) == 0 and len(complex_shims) == 0 and len(verify_all_violations) == 0
    
    if unregistered:
        errors.append(f"Unregistered shell scripts: {', '.join(unregistered)}")
    
    if complex_shims:
        errors.append(f"Shim scripts with complex patterns: {', '.join(complex_shims)}")
    
    return VerificationResult(
        success=success,
        total_scripts=len(scripts),
        registered_scripts=len(scripts) - len(unregistered),
        unregistered_scripts=len(unregistered),
        complex_shims=len(complex_shims),
        verify_all_violations=verify_all_violations,
        findings=findings,
        errors=errors,
    )


def generate_migration_backlog(findings: list[dict]) -> list[dict]:
    """Generate ranked migration backlog from findings."""
    debt_scripts = [f for f in findings if f.get('status') == 'DEBT']
    
    # Sort by risk score (highest first)
    ranked = sorted(
        debt_scripts,
        key=lambda x: (x.get('risk_score', 0), x.get('line_count', 0)),
        reverse=True
    )
    
    return [
        {
            'path': item['path'],
            'risk_level': item.get('risk_level'),
            'risk_score': item.get('risk_score'),
            'line_count': item.get('line_count'),
            'patterns': item.get('patterns', []),
            'owner': item.get('owner'),
            'migration_status': item.get('migration_status'),
        }
        for item in ranked
    ]


# =============================================================================
# Self-Test Fixtures and Validation
# =============================================================================

SELF_TEST_FIXTURES = [
    {
        'name': 'good_shim',
        'path': '.fixtures/shell-containment/good_shim.sh',
        'expected': 'pass',
        'content': '''#!/usr/bin/env bash
# Good shim - only sets env and delegates
set -euo pipefail
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON="$REPO_ROOT/.venv/bin/python"
exec "$PYTHON" "$REPO_ROOT/scripts/verify.py" "$@"
''',
    },
    {
        'name': 'bad_shim_case',
        'path': '.fixtures/shell-containment/bad_shim_case.sh',
        'expected': 'fail',
        'content': '''#!/usr/bin/env bash
# Bad shim - contains case statement
set -euo pipefail
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON="$REPO_ROOT/.venv/bin/python"

case "$1" in
    --fast) exec "$PYTHON" "$REPO_ROOT/scripts/verify.py" --fast ;;
    --full) exec "$PYTHON" "$REPO_ROOT/scripts/verify.py" --full ;;
    *) exit 1 ;;
esac
''',
    },
    {
        'name': 'bad_shim_loop',
        'path': '.fixtures/shell-containment/bad_shim_loop.sh',
        'expected': 'fail',
        'content': '''#!/usr/bin/env bash
# Bad shim - contains while loop
set -euo pipefail
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
count=0
while [[ $count -lt 10 ]]; do
    count=$((count + 1))
done
exec python "$REPO_ROOT/script.py"
''',
    },
    {
        'name': 'bad_shim_arrays',
        'path': '.fixtures/shell-containment/bad_shim_arrays.sh',
        'expected': 'fail',
        'content': '''#!/usr/bin/env bash
# Bad shim - contains arrays
set -euo pipefail
declare -a steps=("step1" "step2" "step3")
for step in "${steps[@]}"; do
    echo "$step"
done
exec python script.py
''',
    },
    {
        'name': 'unregistered_shell',
        'path': '.fixtures/shell-containment/unregistered_complex.sh',
        'expected': 'fail',
        'content': '''#!/usr/bin/env bash
# Unregistered complex shell script
set -euo pipefail
curl -s https://example.com/api | jq '.data'
''',
    },
    {
        'name': 'verify_all_shim_only',
        'path': '.fixtures/shell-containment/verify_all.sh',
        'expected': 'pass',
        'content': '''#!/usr/bin/env bash
# Compatibility shim for verify_all.py.
set -euo pipefail
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON="$REPO_ROOT/.venv/bin/python"
exec "$PYTHON" "$(dirname "$0")/verify_all.py" "$@"
''',
    },
    {
        'name': 'verify_all_shim_violation',
        'path': '.fixtures/shell-containment/verify_all_violation.sh',
        'expected': 'fail',
        'content': '''#!/usr/bin/env bash
# Bad verify_all.sh with case statement
set -euo pipefail
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON="$REPO_ROOT/.venv/bin/python"

case "$1" in
    --fast) PROFILE=fast ;;
    --full) PROFILE=full ;;
    *) PROFILE=fast ;;
esac

exec "$PYTHON" "$(dirname "$0")/verify_all.py" --profile "$PROFILE"
''',
    },
]


def run_self_test() -> tuple[bool, list[str]]:
    """Run self-test validation."""
    errors = []
    fixture_dir = REPO_ROOT / '.fixtures/shell-containment'
    
    # Create fixture directory
    fixture_dir.mkdir(parents=True, exist_ok=True)
    
    # Write fixtures
    for fixture in SELF_TEST_FIXTURES:
        path = REPO_ROOT / fixture['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fixture['content'])
    
    # Temporarily add fixtures to inventory
    original_inventory = INVENTORY_PATH.read_text() if INVENTORY_PATH.exists() else ""
    
    # Add fixture entries to inventory (matching actual fixture paths)
    inventory_lines = original_inventory.strip().split('\n')
    inventory_lines.append('.fixtures/shell-containment/good_shim.sh,shim,test,Test fixture,Python,done,N/A')
    inventory_lines.append('.fixtures/shell-containment/bad_shim_case.sh,shim,test,Test fixture,Python,done,N/A')
    inventory_lines.append('.fixtures/shell-containment/bad_shim_loop.sh,shim,test,Test fixture,Python,done,N/A')
    inventory_lines.append('.fixtures/shell-containment/bad_shim_arrays.sh,shim,test,Test fixture,Python,done,N/A')
    
    INVENTORY_PATH.write_text('\n'.join(inventory_lines))
    
    try:
        # Test full verifier with unregistered fixture present
        # The unregistered_complex.sh fixture is NOT in inventory, so verify_shell_containment should fail
        result = verify_shell_containment()
        if result.success:
            errors.append("self-test: full verifier should fail with unregistered fixture")
        if result.unregistered_scripts == 0:
            errors.append("self-test: full verifier should detect unregistered scripts")
        unregistered_found = any(
            f.get('status') == 'UNREGISTERED' and 'unregistered_complex.sh' in f.get('path', '')
            for f in result.findings
        )
        if not unregistered_found:
            errors.append("self-test: unregistered_complex.sh should appear in findings")
        
        # Test good shim
        good_shim = REPO_ROOT / '.fixtures/shell-containment/good_shim.sh'
        content = good_shim.read_text()
        is_compliant, violations = is_shim_compliant(content)
        if not is_compliant:
            errors.append(f"self-test: good_shim should pass but got violations: {violations}")
        
        # Test bad shim with case
        bad_case = REPO_ROOT / '.fixtures/shell-containment/bad_shim_case.sh'
        content = bad_case.read_text()
        is_compliant, violations = is_shim_compliant(content)
        if is_compliant:
            errors.append("self-test: bad_shim_case should fail shim check")
        
        # Test bad shim with loop
        bad_loop = REPO_ROOT / '.fixtures/shell-containment/bad_shim_loop.sh'
        content = bad_loop.read_text()
        is_compliant, violations = is_shim_compliant(content)
        if is_compliant:
            errors.append("self-test: bad_shim_loop should fail shim check")
        
        # Test bad shim with arrays
        bad_arrays = REPO_ROOT / '.fixtures/shell-containment/bad_shim_arrays.sh'
        content = bad_arrays.read_text()
        is_compliant, violations = is_shim_compliant(content)
        if is_compliant:
            errors.append("self-test: bad_shim_arrays should fail shim check")
        
        # Test verify_all.sh validation
        verify_all_ok = REPO_ROOT / '.fixtures/shell-containment/verify_all.sh'
        content = verify_all_ok.read_text()
        violations = check_verify_all_shim(content)
        if violations:
            errors.append(f"self-test: verify_all.sh should pass but got violations: {violations}")
        
        verify_all_bad = REPO_ROOT / '.fixtures/shell-containment/verify_all_violation.sh'
        content = verify_all_bad.read_text()
        violations = check_verify_all_shim(content)
        if not violations:
            errors.append("self-test: verify_all_violation.sh should fail verify_all check")
        
        # Test pattern detection
        findings = detect_complex_patterns('while true; do echo hi; done')
        if not findings:
            errors.append("self-test: while loop should be detected")
        
        findings = detect_complex_patterns('curl -s http://example.com | jq .')
        if not findings:
            errors.append("self-test: curl and jq should be detected")
        
        findings = detect_complex_patterns('declare -a arr=(a b c)')
        if not findings:
            errors.append("self-test: array declaration should be detected")
        
        # Test risk scoring
        score = calculate_risk_score([('pattern', 'test', 'HIGH'), ('pattern', 'test', 'MEDIUM')])
        if score != 4:
            errors.append(f"self-test: risk score should be 4, got {score}")
        
        # Test migration backlog generation
        test_findings = [
            {'path': 'test1.sh', 'status': 'DEBT', 'risk_score': 3, 'line_count': 100},
            {'path': 'test2.sh', 'status': 'DEBT', 'risk_score': 1, 'line_count': 50},
            {'path': 'test3.sh', 'status': 'OK'},
        ]
        backlog = generate_migration_backlog(test_findings)
        if len(backlog) != 2:
            errors.append(f"self-test: backlog should have 2 entries, got {len(backlog)}")
        if backlog[0]['risk_score'] != 3:
            errors.append("self-test: backlog should be sorted by risk_score desc")
        
    finally:
        # Restore original inventory
        INVENTORY_PATH.write_text(original_inventory)
        
        # Clean up fixtures
        for fixture in SELF_TEST_FIXTURES:
            path = REPO_ROOT / fixture['path']
            if path.exists():
                path.unlink()
        
        # Remove fixture directory if empty
        if fixture_dir.exists() and not any(fixture_dir.iterdir()):
            fixture_dir.rmdir()
    
    return len(errors) == 0, errors


# =============================================================================
# Output Formatting
# =============================================================================

def format_results(result: VerificationResult, json_output: bool = False, verbose: bool = False) -> str:
    """Format verification results."""
    backlog = generate_migration_backlog(result.findings)
    
    if json_output:
        return json.dumps({
            'success': result.success,
            'summary': {
                'total_scripts': result.total_scripts,
                'registered_scripts': result.registered_scripts,
                'unregistered_scripts': result.unregistered_scripts,
                'complex_shims': result.complex_shims,
            },
            'verify_all_violations': result.verify_all_violations,
            'errors': result.errors,
            'findings': result.findings,
            'migration_backlog': backlog,
        }, indent=2)
    
    lines = []
    lines.append("=" * 60)
    lines.append("Shell Containment Verification")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Total shell scripts: {result.total_scripts}")
    lines.append(f"Registered: {result.registered_scripts}")
    lines.append(f"Unregistered: {result.unregistered_scripts}")
    lines.append(f"Complex shims: {result.complex_shims}")
    lines.append("")
    
    if result.errors:
        lines.append("ERRORS:")
        for error in result.errors:
            lines.append(f"  - {error}")
        lines.append("")
    
    if verbose and result.findings:
        lines.append("FINDINGS:")
        for finding in result.findings:
            lines.append(f"  [{finding.get('status', 'UNKNOWN')}] {finding['path']}")
            if 'violations' in finding:
                for v in finding['violations']:
                    lines.append(f"    - {v}")
            if 'patterns' in finding and finding['patterns']:
                lines.append(f"    Patterns: {', '.join(finding['patterns'])}")
            if 'risk_score' in finding:
                lines.append(f"    Risk score: {finding['risk_score']}")
        lines.append("")
    
    if backlog:
        lines.append("MIGRATION BACKLOG (by risk):")
        for i, item in enumerate(backlog[:10], 1):
            lines.append(f"  {i}. {item['path']}")
            lines.append(f"     Risk: {item.get('risk_level', 'N/A')} (score: {item.get('risk_score', 0)})")
            lines.append(f"     Lines: {item.get('line_count', 0)}")
            lines.append(f"     Owner: {item.get('owner', 'N/A')}")
            if item.get('patterns'):
                lines.append(f"     Patterns: {', '.join(item['patterns'][:3])}")
        lines.append("")
    
    lines.append("=" * 60)
    status = "PASSED" if result.success else "FAILED"
    lines.append(f"Shell Containment: {status}")
    lines.append("=" * 60)
    
    return '\n'.join(lines)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Shell containment verification gate",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--json', action='store_true', help='JSON output')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--self-test', action='store_true', help='Run self-test validation')
    
    args = parser.parse_args()
    
    if args.self_test:
        print("Running self-test validation...")
        success, errors = run_self_test()
        if success:
            print("SELF-TEST: PASSED")
            print(f"All {len(SELF_TEST_FIXTURES)} fixtures validated successfully.")
            return 0
        else:
            print("SELF-TEST: FAILED")
            for error in errors:
                print(f"  - {error}")
            return 1
    
    # Run verification
    result = verify_shell_containment()
    
    # Format and print results
    output = format_results(result, json_output=args.json, verbose=args.verbose)
    print(output)
    
    return 0 if result.success else 1


if __name__ == '__main__':
    sys.exit(main())