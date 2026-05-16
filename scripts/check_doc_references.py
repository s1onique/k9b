#!/usr/bin/env python3
"""
Documentation drift checker.

Only flags backtick-quoted paths that:
1. Have a directory prefix (docs/, scripts/, .github/, src/, tests/, .kilocode/, fixtures/)
2. Don't have command-like flags (--flag or KEY=value patterns)
3. Don't exist in the repo
4. Are not in the intentionally-missing list

This avoids false positives from:
- Commands (e.g., `.venv/bin/python`)
- Commands with flags (e.g., `scripts/verify_all.sh --python-only`)
- Short filenames (e.g., `progress.md`)
- Code/function names (e.g., `EvidenceRecord`, `run-health-loop`)
- Audit table entries (intentionally missing files documented there)
- Code blocks
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Only scan files that exist
SCAN_PATHS = [
    "AGENTS.md",
    "docs/agent-docs-audit.md",
    "docs/coverage.md",
    "docs/verification.md",
    ".kilocode/rules/00-global.md",
    ".kilocode/rules/05-fast-task-bootstrap.md",
    ".kilocode/rules/20-architecture-doctrine.md",
    ".kilocode/rules/memory-bank/architecture.md",
    ".kilocode/rules/memory-bank/brief.md",
    ".kilocode/rules/memory-bank/current.md",
    ".kilocode/rules/memory-bank/progress.md",
]

# Intentionally missing files (documented as such in audit tables)
ACCEPTABLE_MISSING = {
    ".kilocode/rules/10-agent-mission.md",
    ".kilocode/rules/30-output-contracts.md",
    ".kilocode/rules/40-tool-use.md",
    ".kilocode/rules/50-kubernetes-monitoring-domain.md",
    ".kilocode/rules/memory-bank/tech.md",
    ".kilocode/rules/memory-bank/product.md",
}

# Only check paths that start with these directory prefixes
PATH_PREFIXES = (
    "docs/",
    "scripts/",
    ".github/",
    "src/",
    "tests/",
    ".kilocode/",
    "fixtures/",
    "charts/",
    "frontend/",
    "docker/",
    "evals/",
    "snapshots/",
    "runs/",
)


def is_broken(path: str) -> bool:
    """Check if a path is broken (has prefix, not in acceptable list, doesn't exist)."""
    path = path.strip()
    
    # Must start with a known prefix
    if not any(path.startswith(p) for p in PATH_PREFIXES):
        return False
    
    # Skip if in acceptable missing list
    if path in ACCEPTABLE_MISSING:
        return False
    
    # Skip if empty or has special chars
    if not path or "<" in path or ">" in path or "*" in path:
        return False
    
    # Skip if it's a URL
    if path.startswith("http"):
        return False
    
    # Skip if it looks like a command with flags (--flag or KEY=value)
    # This catches things like "scripts/verify_all.sh --python-only"
    if re.search(r'\s+--|^\s*--|=', path):
        return False
    
    # Check if exists
    return not REPO_ROOT.joinpath(path).exists()


def check_file(fp: Path) -> list[tuple[int, str]]:
    """Check a file for broken references."""
    issues = []
    try:
        content = fp.read_text()
    except (OSError, UnicodeDecodeError):
        return [(0, "Cannot read")]
    
    lines = content.split("\n")
    in_audit_table = False
    
    for i, line in enumerate(lines, 1):
        # Track audit table sections (they document intentionally-missing files)
        if "## Classification Table" in line or "## Missing Reference Decisions" in line:
            in_audit_table = True
        elif in_audit_table and line.startswith("## "):
            in_audit_table = False
        
        # Skip audit table rows
        if in_audit_table and line.strip().startswith("|"):
            continue
        
        # Skip code blocks
        if line.strip().startswith("```"):
            continue
        
        # Find backtick-quoted paths
        for m in re.finditer(r'`([^`]+)`', line):
            path = m.group(1).strip()
            if is_broken(path):
                issues.append((i, path))
    
    return issues


def main():
    print("Checking doc references...")
    print()
    all_issues = []
    for path in sorted(SCAN_PATHS):
        fp = REPO_ROOT / path
        if not fp.exists():
            print(f"SKIP: {path} (not found)")
            continue
        issues = check_file(fp)
        if issues:
            print(f"ISSUE: {path}")
            for line, p in issues:
                print(f"  Line {line}: '{p}'")
            all_issues.extend(issues)
        else:
            print(f"OK:    {path}")
    print()
    print(f"Found {len(all_issues)} broken reference(s)" if all_issues else "All references verified")
    return 1 if all_issues else 0


if __name__ == "__main__":
    sys.exit(main())