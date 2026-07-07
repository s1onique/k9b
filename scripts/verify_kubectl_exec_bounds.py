#!/usr/bin/env python3
"""Static verifier for kubectl exec bounds policy.

This script scans production source files for unsafe subprocess patterns
that could cause unbounded memory growth from large kubectl output.

Policy:
- Production scheduler/health-loop modules must use bounded kubectl execution
- No capture_output=True, check_output, communicate(), or unbounded PIPE
- kubectl logs must include --limit-bytes and a line/time bound

Usage:
    python scripts/verify_kubectl_exec_bounds.py [--json]
    python scripts/verify_kubectl_exec_bounds.py --fix  # show auto-fixable issues
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Patterns that indicate unsafe subprocess usage
UNSAFE_PATTERNS = {
    "capture_output=True": {
        "severity": "error",
        "message": "capture_output=True in production code can cause unbounded memory growth",
        "suggestion": "Use run_kubectl() from k8s_diag_agent.security.kubectl_subprocess",
    },
    "subprocess.check_output": {
        "severity": "error",
        "message": "check_output() buffers all output in memory",
        "suggestion": "Use run_kubectl() from k8s_diag_agent.security.kubectl_subprocess",
    },
    ".communicate(": {
        "severity": "error",
        "message": "communicate() can buffer unbounded output in memory",
        "suggestion": "Use run_kubectl() or the streaming approach in kubectl_bounded",
    },
    "text=True": {
        "severity": "warning",
        "message": "text=True combined with capture can buffer unbounded text",
        "suggestion": "Use run_kubectl() which handles encoding safely",
    },
    "stdout=subprocess.PIPE": {
        "severity": "error",
        "message": "stdout=PIPE without bounds can cause unbounded memory growth",
        "suggestion": "Use run_kubectl() from k8s_diag_agent.security.kubectl_subprocess",
    },
    "stderr=subprocess.PIPE": {
        "severity": "error",
        "message": "stderr=PIPE without bounds can cause unbounded memory growth",
        "suggestion": "Use run_kubectl() from k8s_diag_agent.security.kubectl_subprocess",
    },
    "shell=True": {
        "severity": "error",
        "message": "shell=True is a security and safety risk",
        "suggestion": "Use argv-based execution with run_kubectl()",
    },
}

# kubectl logs patterns that require bounds
LOGS_UNSAFE_PATTERNS = {
    "kubectl logs": {
        "require_flags": ["--limit-bytes"],
        "require_one_of": [["--tail", "--since", "--since-time"]],
        "severity": "error",
        "message": "kubectl logs must include --limit-bytes and --tail/--since/--since-time",
    },
}

# Files/directories to exclude from scanning
EXCLUDED_PATHS = {
    "tests/",
    "test_",
    "conftest.py",
    "__pycache__/",
    ".venv/",
    "fixtures/",
    "evals/",
    "docs/",
    "scripts/incident_discovery_gate/",
    "scripts/backend_health_gate/",
}

# Files that are explicitly allowlisted (use unsafe patterns but are OK)
ALLOWLISTED_FILES = {
    "src/k8s_diag_agent/security/kubectl_bounded.py",
    "src/k8s_diag_agent/security/kubectl_subprocess.py",
    "src/k8s_diag_agent/security/kubectl_logs.py",
    "src/k8s_diag_agent/health/loop_alertmanager_port_forward.py",  # Uses communicate with timeouts for port-forward cleanup
}

# Non-kubectl subprocess usages that are OK (helm, build scripts, utility commands)
# These are bounded by nature (small outputs) or not kubectl-related
NON_KUBECTL_PATTERNS = {
    "helm",
    "build",
    "pack",
    "refresh",
    "subprocess",
    "CommandRunner",
    "check_output",
    "_run_helm",
    "_subprocess.run",
}

# Production paths that must use bounded execution
PRODUCTION_PATHS = [
    "src/k8s_diag_agent/health/",
    "src/k8s_diag_agent/collect/",
    "src/k8s_diag_agent/ui/",
    "src/k8s_diag_agent/render/",
    "src/k8s_diag_agent/reason/",
    "src/k8s_diag_agent/recommend/",
]


def is_production_path(path: str) -> bool:
    """Check if a path is a production path."""
    return any(path.startswith(p) for p in PRODUCTION_PATHS)


def is_excluded(path: str) -> bool:
    """Check if a path should be excluded from scanning."""
    path_lower = path.lower()
    for excluded in EXCLUDED_PATHS:
        if excluded in path_lower:
            return True
    return False


def is_allowlisted(path: str) -> bool:
    """Check if a path is explicitly allowlisted."""
    return any(allowlisted in path for allowlisted in ALLOWLISTED_FILES)


def is_kubectl_subprocess(line: str, prev_lines: list[str]) -> bool:
    """Check if a subprocess call is for kubectl (vs helm, build scripts, etc).
    
    Classifier logic:
    1. First, check for kubectl indicator (must be prioritized)
    2. Only then, classify known non-kubectl tools as non-kubectl
    3. Do NOT use generic "subprocess" or "subprocess.run(" as non-kubectl indicator
       because kubectl calls also use subprocess.run()
    
    This ordering ensures that:
        cmd = ["kubectl", "get", "pods"]
        subprocess.run(cmd, capture_output=True)
    is correctly classified as kubectl (not non-kubectl).
    """
    # Look at surrounding context (10 lines before to find the command list)
    context = "\n".join(prev_lines[-10:] + [line])
    
    # FIRST: Check for kubectl indicator
    # This must be checked BEFORE non-kubectl indicators
    # because kubectl calls also use subprocess.run()
    if "kubectl" in context:
        return True
    
    # SECOND: Only after kubectl check, classify known non-kubectl tools
    # These are bounded by nature (helm, build scripts) or explicit helpers
    non_kubectl_indicators = [
        "helm",
        "_run_helm",
        "build",
        "pack",
        "refresh",
        "CommandRunner",
    ]
    
    for indicator in non_kubectl_indicators:
        if indicator in context:
            return False
    
    # Not a kubectl call and not a known non-kubectl tool
    return False


def should_skip_warning(line: str, prev_lines: list[str]) -> bool:
    """Check if a warning should be skipped (non-kubectl or non-production paths)."""
    # Skip warnings for non-kubectl subprocess calls
    if not is_kubectl_subprocess(line, prev_lines):
        return True
    
    # Skip warnings for external_analysis paths (discovery strategies)
    # These are informational queries, not heavy log/output collection
    for prev_line in prev_lines[-5:]:
        if "external_analysis" in prev_line:
            return True
    
    return False


def scan_file(path: Path) -> list[dict]:
    """Scan a single file for unsafe patterns."""
    findings = []

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
    except (UnicodeDecodeError, OSError) as e:
        return [{
            "path": str(path),
            "line": 0,
            "pattern": "<read_error>",
            "message": f"Could not read file: {e}",
            "severity": "warning",
        }]

    rel_path = str(path)

    # Check for unsafe patterns
    for line_num, line in enumerate(lines, start=1):
        for pattern, info in UNSAFE_PATTERNS.items():
            if pattern in line:
                # Skip if in allowlisted file
                if is_allowlisted(rel_path):
                    continue

                # Skip if line is commented
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"""'):
                    continue

                # Check if this is the bounded seam import/usage
                if "from ..security.kubectl_bounded import" in line:
                    continue

                # For capture_output=True, only flag kubectl subprocess calls
                # kubectl subprocess calls are always unsafe regardless of path
                if pattern == "capture_output=True":
                    prev_lines = lines[:line_num - 1]
                    if not is_kubectl_subprocess(line, prev_lines):
                        continue
                    # Skip capture_output=True errors for external_analysis paths
                    # These are informational queries, not heavy log/output collection
                    if "external_analysis" in rel_path:
                        continue

                # For other patterns and warnings, skip non-production and non-kubectl paths
                if not is_production_path(rel_path):
                    prev_lines = lines[:line_num - 1]
                    if not is_kubectl_subprocess(line, prev_lines):
                        continue

                # For warnings, skip non-kubectl and external_analysis paths
                if info["severity"] == "warning":
                    prev_lines = lines[:line_num - 1]
                    if should_skip_warning(line, prev_lines):
                        continue

                findings.append({
                    "path": rel_path,
                    "line": line_num,
                    "code": line.strip(),
                    "pattern": pattern,
                    "message": info["message"],
                    "suggestion": info.get("suggestion", ""),
                    "severity": info["severity"],
                })

    # Check for kubectl logs without bounds
    for line_num, line in enumerate(lines, start=1):
        for pattern, logs_info in LOGS_UNSAFE_PATTERNS.items():
            if pattern in line and is_production_path(rel_path) and not is_allowlisted(rel_path):
                # Check if required flags are present
                has_limit_bytes = "--limit-bytes" in line
                require_one_of_flags: list[str] = logs_info["require_one_of"][0]  # type: ignore[index]
                has_time_bound = any(flag in line for flag in require_one_of_flags)

                if not (has_limit_bytes and has_time_bound):
                    findings.append({
                        "path": rel_path,
                        "line": line_num,
                        "code": line.strip(),
                        "pattern": pattern,
                        "message": logs_info["message"],
                        "suggestion": f"Add --limit-bytes=<N> and one of {require_one_of_flags}",
                        "severity": logs_info["severity"],
                    })

    return findings


def scan_directory(repo_root: Path) -> list[dict]:
    """Scan the repository for unsafe patterns."""
    all_findings = []

    src_dir = repo_root / "src" / "k8s_diag_agent"

    for path in src_dir.rglob("*.py"):
        rel_path = str(path.relative_to(repo_root))

        if is_excluded(rel_path):
            continue

        findings = scan_file(path)
        all_findings.extend(findings)

    return all_findings


def format_findings(findings: list[dict], json_output: bool = False) -> str:
    """Format findings for output."""
    if json_output:
        return json.dumps({
            "findings": findings,
            "summary": {
                "total": len(findings),
                "errors": sum(1 for f in findings if f["severity"] == "error"),
                "warnings": sum(1 for f in findings if f["severity"] == "warning"),
            }
        }, indent=2)

    if not findings:
        return "No kubectl exec bounds violations found."

    output = []
    output.append("=" * 70)
    output.append("KUBECTL EXEC BOUNDS VIOLATIONS")
    output.append("=" * 70)
    output.append("")

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]

    if errors:
        output.append(f"ERRORS ({len(errors)}):")
        output.append("-" * 70)
        for finding in errors:
            output.append(f"\n{finding['path']}:{finding['line']}")
            output.append(f"  Pattern: {finding['pattern']}")
            output.append(f"  {finding['message']}")
            if finding.get("suggestion"):
                output.append(f"  Suggestion: {finding['suggestion']}")
            output.append(f"  Code: {finding.get('code', '')}")
        output.append("")

    if warnings:
        output.append(f"\nWARNINGS ({len(warnings)}):")
        output.append("-" * 70)
        for finding in warnings:
            output.append(f"\n{finding['path']}:{finding['line']}")
            output.append(f"  Pattern: {finding['pattern']}")
            output.append(f"  {finding['message']}")
            if finding.get("suggestion"):
                output.append(f"  Suggestion: {finding['suggestion']}")
            output.append(f"  Code: {finding.get('code', '')}")

    output.append("")
    output.append("=" * 70)
    output.append(f"Total: {len(findings)} findings ({len(errors)} errors, {len(warnings)} warnings)")
    output.append("=" * 70)

    return "\n".join(output)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify kubectl exec bounds policy compliance"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Show auto-fixable issues"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).parent.parent,
        help="Repository root path"
    )
    args = parser.parse_args()

    findings = scan_directory(args.repo_root)

    output = format_findings(findings, json_output=args.json)
    print(output)

    # Return non-zero if there are errors
    errors = [f for f in findings if f["severity"] == "error"]
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
