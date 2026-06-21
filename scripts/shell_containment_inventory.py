"""Shell Containment Inventory Management.

Handles loading and validating the shell script inventory.
"""

from __future__ import annotations

import csv
from pathlib import Path

from shell_containment_contract import (
    Classification,
    FindingDict,
    InventoryEntry,
    MigrationStatus,
    ShellScript,
    VerificationResult,
)
from shell_containment_rules import (
    calculate_risk_score,
    detect_complex_patterns,
    get_risk_level,
    is_shim_compliant,
)

REPO_ROOT = Path(__file__).parent.parent
INVENTORY_PATH = REPO_ROOT / "docs/tooling/shell-containment-inventory.csv"
VERIFY_ALL_SH = REPO_ROOT / "scripts/verify_all.sh"


def load_inventory(path: Path) -> dict[str, InventoryEntry]:
    """Load inventory from CSV file."""
    entries: dict[str, InventoryEntry] = {}
    
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
            except (KeyError, ValueError):
                # Skip malformed rows
                continue
    
    return entries


def scan_shell_file(path: Path, repo_root: Path) -> ShellScript:
    """Scan a shell file and return analysis."""
    try:
        content = path.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        return ShellScript(
            path=path,
            relative_path=str(path.relative_to(repo_root)),
            line_count=0,
            detected_patterns=[("read_error", f"Error reading file: {e}", "LOW")]
        )
    
    lines = content.split('\n')
    findings = detect_complex_patterns(content)
    risk_score = calculate_risk_score(findings)
    
    return ShellScript(
        path=path,
        relative_path=str(path.relative_to(repo_root)),
        line_count=len(lines),
        detected_patterns=findings,
        is_complex=len(findings) > 0 or len([line for line in lines if line.strip() and not line.strip().startswith('#')]) > 50,
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
    code_lines = [line for line in content.split('\n') if not line.strip().startswith('#')]
    code_only = '\n'.join(code_lines)
    
    for pattern, description in forbidden_in_shim:
        if pattern in code_only:
            violations.append(f"Forbidden in shim: {description}")
    
    return violations


def verify_shell_containment() -> VerificationResult:
    """Run shell containment verification."""
    errors: list[str] = []
    findings: list[FindingDict] = []
    
    # Find all shell scripts
    scripts = find_shell_scripts(REPO_ROOT)
    
    # Load inventory
    inventory = load_inventory(INVENTORY_PATH)
    
    unregistered: list[str] = []
    complex_shims: list[str] = []
    verify_all_violations: list[str] = []
    
    for script_path in scripts:
        rel_path = str(script_path.relative_to(REPO_ROOT))
        analysis = scan_shell_file(script_path, REPO_ROOT)
        
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
