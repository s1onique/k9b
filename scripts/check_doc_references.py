#!/usr/bin/env python3
"""
Documentation drift checker.

Checks backtick-quoted paths in agent-facing docs for existence.
Only flags paths that:
1. Start with a known directory prefix (docs/, scripts/, .github/, src/, tests/, .kilocode/, fixtures/)
2. Don't exist in the repo
3. Are not in the intentionally-missing list

Skips:
- Short filenames (e.g., `progress.md`) — valid in context
- Code/function names (e.g., `EvidenceRecord`, `run-health-loop`)
- Commands with flags (e.g., `scripts/verify_all.sh --python-only`)
- Globs (e.g., `.kilocode/rules/memory-bank/*.md`)

Does NOT explicitly skip code blocks — backtick-quoted paths in code blocks ARE checked
since broken commands are exactly what we want to catch. If a command is referenced
in a code block, it should still resolve.

Usage:
    .venv/bin/python scripts/check_doc_references.py           # check docs
    .venv/bin/python scripts/check_doc_references.py --self-check  # run internal tests
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


def normalize_path(path: str) -> str:
    """Normalize path by stripping leading ./ or .\\ for consistent prefix checking."""
    path = path.strip()
    # Strip leading ./
    if path.startswith("./"):
        path = path[2:]
    elif path.startswith(".\\"):
        path = path[2:]
    return path


def is_broken(path: str) -> bool:
    """Check if a path is broken (has prefix, not in acceptable list, doesn't exist)."""
    path = path.strip()
    normalized = normalize_path(path)
    
    # Must start with a known prefix (check both original and normalized)
    if not any(path.startswith(p) for p in PATH_PREFIXES) and \
       not any(normalized.startswith(p) for p in PATH_PREFIXES):
        return False
    
    # Skip if in acceptable missing list
    if normalized in ACCEPTABLE_MISSING or path in ACCEPTABLE_MISSING:
        return False
    
    # Skip if empty or has special chars
    if not path or "<" in path or ">" in path:
        return False
    
    # Skip if it's a URL
    if path.startswith("http"):
        return False
    
    # Skip globs
    if "*" in path or "?" in path:
        return False
    
    # Skip if it looks like a command with flags (--flag or KEY=value)
    if re.search(r'\s+--|^\s*--|=', path):
        return False
    
    # Check if exists (try both normalized and original)
    if REPO_ROOT.joinpath(normalized).exists() or REPO_ROOT.joinpath(path).exists():
        return False
    
    return True


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
        
        # Find backtick-quoted paths
        for m in re.finditer(r'`([^`]+)`', line):
            path = m.group(1).strip()
            if is_broken(path):
                issues.append((i, path))
    
    return issues


def run_self_check() -> bool:
    """Run internal self-check tests. Returns True if all pass."""
    print("Running self-check tests...")
    print()
    
    tests = [
        # (description, path, expected_is_broken)
        
        # ✅ Should be OK: scripts/run_coverage.sh exists
        ("scripts/foo.sh missing is flagged", "scripts/foo.sh", True),
        
        # ✅ Should be OK: ./scripts/... normalized to scripts/...
        ("./scripts/foo.sh missing is flagged", "./scripts/foo.sh", True),
        
        # ✅ Should be OK: scripts/run_coverage.sh exists
        ("scripts/run_coverage.sh exists", "scripts/run_coverage.sh", False),
        
        # ✅ Should be OK: ./scripts/run_coverage.sh exists
        ("./scripts/run_coverage.sh exists", "./scripts/run_coverage.sh", False),
        
        # ✅ Should be OK: acceptable missing paths are ignored
        ("acceptable missing .kilocode/rules/10-agent-mission.md ignored", 
         ".kilocode/rules/10-agent-mission.md", False),
        
        # ✅ Should be OK: globs are ignored
        (".kilocode/rules/memory-bank/*.md glob ignored", 
         ".kilocode/rules/memory-bank/*.md", False),
        
        # ✅ Should be OK: commands with flags are ignored
        ("verify_all.sh --python-only ignored", "scripts/verify_all.sh --python-only", False),
        
        # ✅ Should be OK: short filenames ignored (no prefix)
        ("progress.md short filename ignored", "progress.md", False),
        
        # ✅ Should be OK: function names ignored
        ("EvidenceRecord function name ignored", "EvidenceRecord", False),
        
        # ✅ Should be OK: URLs ignored
        ("https://example.com ignored", "https://example.com", False),
        
        # ✅ Should be OK: existing files exist
        ("AGENTS.md exists", "AGENTS.md", False),
        (".kilocode/rules/00-global.md exists", ".kilocode/rules/00-global.md", False),
        ("docs/coverage.md exists", "docs/coverage.md", False),
        
        # ✅ Should be OK: frontend paths exist
        ("frontend/src/App.tsx exists", "frontend/src/App.tsx", False),
    ]
    
    passed = 0
    failed = 0
    
    for desc, path, expected in tests:
        result = is_broken(path)
        status = "PASS" if result == expected else "FAIL"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"  [{status}] {desc}")
        if result != expected:
            print(f"         Expected: {expected}, Got: {result}")
    
    print()
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


def main():
    # Check for self-check mode
    if len(sys.argv) > 1 and sys.argv[1] in ("--self-check", "-t", "--test"):
        success = run_self_check()
        return 0 if success else 1
    
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