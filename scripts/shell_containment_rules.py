"""Shell Containment Rules and Pattern Detection.

Defines complex shell patterns and detection logic.
"""

from __future__ import annotations

import re

from shell_containment_contract import RiskLevel

# Patterns that indicate complex shell (high risk)
COMPLEX_PATTERNS: list[tuple[str, str, str]] = [
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
    
    # Heredocs with logic - MEDIUM risk
    (r'<<-?\s*[\'"]?\w+[\'"]?', 'heredoc', 'MEDIUM'),
    
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
CRITICAL_SHIM_ONLY: list[str] = [
    'scripts/verify_all.sh',
]


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
    code_lines = [line.strip() for line in lines if line.strip() and not line.strip().startswith('#')]
    
    if len(code_lines) > max_lines:
        violations.append(f"Exceeds {max_lines} lines of code ({len(code_lines)} non-comment lines)")
    
    # Check for complex patterns
    findings = detect_complex_patterns(content)
    if findings:
        for pattern, description, risk in findings:
            violations.append(f"Complex pattern: {description} ({risk} risk)")
    
    return len(violations) == 0, violations
