#!/usr/bin/env python3
"""
Changed-file verification recommendation engine.

Analyzes changed files and recommends verification checks relevant to the changes.

Usage:
    python scripts/recommend_verification.py [--diff <path>] [--run]
    python scripts/recommend_verification.py --list-recommendations

Output:
    - Recommended local checks (fast profile + targeted tests)
    - Merge-grade escalation command
    - Exit code: 0 always (recommendations, not execution)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# =============================================================================
# Path Mappings
# =============================================================================


@dataclass
class PathMapping:
    """Maps changed paths to relevant verification steps."""
    patterns: list[str]                    # Glob patterns to match
    recommended_steps: list[str]           # Step IDs to recommend
    priority: int = 0                      # Higher = more important

    def matches(self, path: str) -> bool:
        """Check if a path matches this mapping."""
        from fnmatch import fnmatch
        for pattern in self.patterns:
            if fnmatch(path, pattern) or fnmatch(Path(path).name, pattern):
                return True
            # Also match if path contains the pattern as a component
            if pattern in path:
                return True
        return False


# Path-to-step mappings
PATH_MAPPINGS = [
    # Frontend changes
    PathMapping(
        patterns=["frontend/**/*.tsx", "frontend/**/*.ts", "frontend/**/*.jsx", "frontend/**/*.js"],
        recommended_steps=["npm-ci", "npm-test-ui", "npm-build"],
        priority=5,
    ),
    PathMapping(
        patterns=["frontend/package.json", "frontend/package-lock.json"],
        recommended_steps=["npm-ci", "npm-test-ui", "npm-build"],
        priority=10,
    ),

    # Python source changes
    PathMapping(
        patterns=["src/**/*.py"],
        recommended_steps=["ruff-lint", "mypy"],
        priority=5,
    ),

    # Python test changes
    PathMapping(
        patterns=["tests/**/*.py"],
        recommended_steps=["ruff-lint", "mypy-tests", "unit-tests"],
        priority=5,
    ),

    # Helm chart changes
    PathMapping(
        patterns=["charts/**/*", "helm/**/*"],
        recommended_steps=["helm-chart", "helm-oci-login"],
        priority=10,
    ),

    # CI workflow changes
    PathMapping(
        patterns=[".github/workflows/*.yml", ".github/workflows/*.yaml"],
        recommended_steps=["ci-gate-drift"],
        priority=10,
    ),

    # Documentation changes
    PathMapping(
        patterns=["docs/**/*.md", "docs/**/*.rst", "docs/**/*.txt"],
        recommended_steps=["docs-inventory", "docs-claims-registry"],
        priority=3,
    ),

    # Docker changes
    PathMapping(
        patterns=["Dockerfile*", "docker/**/*", ".dockerignore"],
        recommended_steps=["dockerhub-base-images", "docker-workflow-hygiene", "docker-build-locality"],
        priority=10,
    ),

    # Configuration changes
    PathMapping(
        patterns=["pyproject.toml", "setup.py", "setup.cfg", "mypy.ini", "pytest.ini", ".pre-commit-config.yaml"],
        recommended_steps=["ruff-lint", "mypy"],
        priority=7,
    ),

    # Agent/pipeline changes
    PathMapping(
        patterns=[
            "src/k8s_diag_agent/collect/**/*.py",
            "src/k8s_diag_agent/normalization/**/*.py",
            "src/k8s_diag_agent/correlation/**/*.py",
            "src/k8s_diag_agent/reasoning/**/*.py",
            "src/k8s_diag_agent/recommendation/**/*.py",
        ],
        recommended_steps=["agent-pipeline", "llm-evidence-boundaries", "llm-semantic-injection"],
        priority=5,
    ),

    # UI/API changes
    PathMapping(
        patterns=[
            "src/k8s_diag_agent/ui/**/*.py",
            "frontend/**/*.tsx",
            "frontend/**/*.ts",
        ],
        recommended_steps=["agent-pipeline", "llm-evidence-boundaries"],
        priority=5,
    ),

    # LLM/evidence changes
    PathMapping(
        patterns=[
            "src/k8s_diag_agent/llm/**/*.py",
            "src/k8s_diag_agent/evidence/**/*.py",
        ],
        recommended_steps=["llm-evidence-boundaries", "llm-semantic-injection"],
        priority=7,
    ),

    # Discovery changes
    PathMapping(
        patterns=["src/k8s_diag_agent/discovery/**/*.py"],
        recommended_steps=["discovery-logging-hygiene", "llm-evidence-boundaries"],
        priority=5,
    ),

    # Script changes
    PathMapping(
        patterns=["scripts/**/*.py", "scripts/**/*.sh"],
        recommended_steps=["ruff-lint"],
        priority=3,
    ),
]


# =============================================================================
# Recommendation Engine
# =============================================================================


@dataclass
class VerificationRecommendation:
    """A verification recommendation."""
    step_id: str
    command: str
    reason: str
    priority: int = 0


@dataclass
class RecommendationSet:
    """Set of recommendations from changed files."""
    changed_files: list[str] = field(default_factory=list)
    recommendations: list[VerificationRecommendation] = field(default_factory=list)
    matched_mappings: list[str] = field(default_factory=list)

    def unique_recommendations(self) -> list[VerificationRecommendation]:
        """Return deduplicated recommendations, preserving highest priority."""
        seen: dict[str, VerificationRecommendation] = {}
        for rec in sorted(self.recommendations, key=lambda r: -r.priority):
            if rec.step_id not in seen:
                seen[rec.step_id] = rec
        return list(seen.values())


def get_changed_files(ref: Optional[str] = None) -> list[str]:
    """
    Get list of changed files compared to ref (default: HEAD).
    Includes both modified/tracked AND untracked files.
    
    Returns empty list on error.
    """
    files = []
    try:
        # Get tracked changed files
        cmd = ["git", "diff", "--name-only", f"{ref}...HEAD" if ref else "HEAD"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        files.extend(f.strip() for f in result.stdout.strip().split("\n") if f.strip())
        
        # Get untracked files (new files not yet committed)
        cmd_untracked = ["git", "ls-files", "--others", "--exclude-standard"]
        result_untracked = subprocess.run(
            cmd_untracked,
            capture_output=True,
            text=True,
            check=True,
        )
        files.extend(f.strip() for f in result_untracked.stdout.strip().split("\n") if f.strip())
        
        # Deduplicate while preserving order
        seen = set()
        unique_files = []
        for f in files:
            if f not in seen:
                seen.add(f)
                unique_files.append(f)
        return unique_files
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def get_staged_files() -> list[str]:
    """Get list of staged files."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        return files
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def recommend_for_files(files: list[str]) -> RecommendationSet:
    """Generate recommendations for a list of changed files.
    
    Accumulates ALL matching mappings per file (not just first match).
    This ensures domain-specific checks are included alongside generic ones.
    """
    recommendations: list[VerificationRecommendation] = []
    matched_mappings: list[str] = []

    for file_path in files:
        # Accumulate ALL matching mappings for this file
        for mapping in sorted(PATH_MAPPINGS, key=lambda m: -m.priority):
            if mapping.matches(file_path):
                matched_mappings.append(f"{file_path} -> {mapping.recommended_steps}")
                for step_id in mapping.recommended_steps:
                    rec = VerificationRecommendation(
                        step_id=step_id,
                        command=f"# {step_id}",  # Command lookup deferred
                        reason=f"Changed: {file_path}",
                        priority=mapping.priority,
                    )
                    recommendations.append(rec)
                # DO NOT break - continue to accumulate ALL matching mappings

    return RecommendationSet(
        changed_files=files,
        recommendations=recommendations,
        matched_mappings=matched_mappings,
    )


def get_step_command(step_id: str) -> str:
    """Get the command for a step ID."""
    commands = {
        "ruff-lint": "python -m ruff check src tests",
        "mypy": "python -m mypy src/k8s_diag_agent",
        "mypy-tests": "python -m mypy tests/__init__.py tests/path_helper.py tests/test_*.py",
        "unit-tests": "bash scripts/run_unit_tests.sh",
        "npm-ci": "cd frontend && npm ci",
        "npm-test-ui": "cd frontend && npm run test:ui",
        "npm-build": "cd frontend && npm run build",
        "helm-chart": "bash scripts/verify_helm_chart.sh",
        "helm-oci-login": "bash scripts/verify_helm_oci_login.sh",
        "llm-friendly": "python scripts/check_llm_friendly_files.py --quiet",
        "doctrine": "bash scripts/verify_factory_doctrine.sh",
        "dockerhub-base-images": "bash scripts/verify_dockerhub_base_images.sh",
        "docker-workflow-hygiene": "bash scripts/verify_docker_workflow_hygiene.sh",
        "docker-build-locality": "bash scripts/verify_docker_build_locality.sh",
        "structured-output": "bash scripts/verify_health_loop_structured_output.sh",
        "agent-pipeline": "python scripts/verify_agentic_pipeline.py",
        "llm-evidence-boundaries": "python scripts/verify_llm_evidence_boundaries.py",
        "llm-semantic-injection": "python scripts/verify_llm_semantic_injection_detection.py",
        "ci-gate-drift": "python scripts/verify_ci_gate_drift.py",
        "incident-report-quality": "python scripts/verify_incident_report_quality.py",
        "artifact-immutability": "python scripts/verify_artifact_immutability.py",
        "production-readiness-disclaimer": "python scripts/verify_production_readiness_disclaimer.py",
        "docs-inventory": "python scripts/verify_docs_inventory.py",
        "docs-claims-registry": "python scripts/verify_docs_claims_registry.py",
        "discovery-logging-hygiene": "python scripts/verify_discovery_logging_hygiene.py",
    }
    return commands.get(step_id, f"# unknown step: {step_id}")


# =============================================================================
# Output Formatting
# =============================================================================


def format_recommendations(rec_set: RecommendationSet, json_output: bool = False) -> str:
    """Format recommendations for display."""
    if json_output:
        unique_recs = rec_set.unique_recommendations()
        output = {
            "changed_files_count": len(rec_set.changed_files),
            "changed_files": rec_set.changed_files,
            "recommendations": [
                {
                    "step_id": rec.step_id,
                    "command": get_step_command(rec.step_id),
                    "reason": rec.reason,
                    "priority": rec.priority,
                }
                for rec in sorted(unique_recs, key=lambda r: -r.priority)
            ],
            "escalation": {
                "fast": "./scripts/verify_all.sh --fast",
                "full": "./scripts/verify_all.sh --full",
            },
        }
        return json.dumps(output, indent=2)

    # Human-readable output
    lines = []
    lines.append("=" * 60)
    lines.append("Changed Files Verification Recommendations")
    lines.append("=" * 60)
    lines.append("")

    if rec_set.changed_files:
        lines.append(f"Changed files ({len(rec_set.changed_files)}):")
        for f in rec_set.changed_files[:20]:  # Limit display
            lines.append(f"  - {f}")
        if len(rec_set.changed_files) > 20:
            lines.append(f"  ... and {len(rec_set.changed_files) - 20} more")
        lines.append("")

    unique_recs = rec_set.unique_recommendations()
    if unique_recs:
        lines.append(f"Recommended local checks ({len(unique_recs)}):")
        lines.append("")
        for rec in sorted(unique_recs, key=lambda r: -r.priority):
            cmd = get_step_command(rec.step_id)
            lines.append(f"  {rec.step_id}:")
            lines.append(f"    Command: {cmd}")
            lines.append(f"    Reason: {rec.reason}")
            lines.append("")

    lines.append("-" * 60)
    lines.append("Escalation commands:")
    lines.append("")
    lines.append("  Local fast check:")
    lines.append("    ./scripts/verify_all.sh --fast")
    lines.append("")
    lines.append("  Merge-grade verification:")
    lines.append("    ./scripts/verify_all.sh --full")
    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Recommend verification checks based on changed files"
    )
    parser.add_argument(
        "--diff",
        metavar="PATH",
        help="Read changed files from diff file (or '-' for stdin)",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Recommend checks for staged files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--list-mappings",
        action="store_true",
        help="List all path-to-step mappings",
    )

    args = parser.parse_args()

    if args.list_mappings:
        print("Path-to-step mappings:")
        print()
        for mapping in sorted(PATH_MAPPINGS, key=lambda m: -m.priority):
            print(f"  Priority {mapping.priority}:")
            print(f"    Patterns: {', '.join(mapping.patterns)}")
            print(f"    Steps: {', '.join(mapping.recommended_steps)}")
            print()
        return 0

    # Get changed files
    if args.diff:
        if args.diff == "-":
            diff_content = sys.stdin.read()
            files = [f.strip() for f in diff_content.strip().split("\n") if f.strip()]
        else:
            with open(args.diff) as f:
                files = [f.strip() for line in f for f in [line.strip()] if f]
    elif args.staged:
        files = get_staged_files()
    else:
        files = get_changed_files()

    if not files:
        print("No changed files found.", file=sys.stderr)
        # Don't fail - just show empty recommendations
        files = []

    # Generate recommendations
    rec_set = recommend_for_files(files)

    # Output
    print(format_recommendations(rec_set, json_output=args.json))

    # Return 0 always (recommendations, not execution result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
