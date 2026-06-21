#!/usr/bin/env python3
"""
Verification profile definitions and executor.

This module defines verification profiles and their composition,
serving as the authoritative source of truth for what each profile runs.

Profile Selection Logic:
    - --fast: local default / high-signal smoke and policy checks (target ≤45s, hard ceiling ≤60s)
    - --full: current exhaustive merge-grade verification behavior
    - --changed: recommend and/or run checks relevant to changed files
    - lane scopes (--python-only, etc.): preserve existing focused lane support

Usage:
    python scripts/verify_profiles.py --list           # List all profiles
    python scripts/verify_profiles.py --profile fast  # Show fast profile steps
    python scripts/verify_profiles.py --validate      # Validate profile contracts
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


# =============================================================================
# Profile Definitions
# =============================================================================


class Profile(Enum):
    """Verification profile names."""
    FAST = "fast"
    FULL = "full"
    CHANGED = "changed"


class StepCategory(Enum):
    """Step execution category."""
    POLICY = "policy"          # Linting, typing, doctrine checks
    SMOKE = "smoke"            # Quick smoke tests
    FULL_SUITE = "full_suite"  # Expensive full test suites
    BUILD = "build"            # Build and packaging
    DOCS = "docs"              # Documentation checks


@dataclass(frozen=True)
class VerificationStep:
    """A single verification step."""
    id: str                          # Unique step identifier (e.g., "ruff-lint")
    command: str                     # Command to execute
    lane: str                        # Execution lane: "python", "frontend", "helm"
    category: StepCategory           # Step category for filtering
    description: str = ""            # Human-readable description
    timeout_seconds: int = 300       # Max execution time before warning
    is_expensive: bool = False      # If True, excluded from fast profile

    @property
    def is_fast_candidate(self) -> bool:
        """Return True if this step can run in fast profile."""
        return not self.is_expensive


@dataclass
class VerificationProfile:
    """A verification profile definition."""
    name: str
    description: str
    target_time_seconds: int = 60
    ideal_time_seconds: int = 45
    includes: list[str] = field(default_factory=list)  # Step IDs to include
    excludes: list[str] = field(default_factory=list)   # Step IDs to exclude
    escalation_command: str = ""                         # Command for merge-grade verification


# =============================================================================
# Step Registry
# =============================================================================


def get_all_steps() -> list[VerificationStep]:
    """Return all known verification steps."""
    steps = []

    # --- Python Policy Steps (fast candidates) ---
    steps.extend([
        VerificationStep(
            id="ruff-lint",
            command="python -m ruff check src tests",
            lane="python",
            category=StepCategory.POLICY,
            description="Ruff linting",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="mypy",
            command="python -m mypy src/k8s_diag_agent",
            lane="python",
            category=StepCategory.POLICY,
            description="Mypy type checking on main package",
            timeout_seconds=120,
        ),
        VerificationStep(
            id="mypy-tests",
            command="python -m mypy tests/__init__.py tests/path_helper.py tests/test_*.py",
            lane="python",
            category=StepCategory.POLICY,
            description="Mypy type checking on tests",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="llm-friendly",
            command="python scripts/check_llm_friendly_files.py --quiet",
            lane="python",
            category=StepCategory.POLICY,
            description="File size check for LLM-friendliness",
            timeout_seconds=30,
        ),
        VerificationStep(
            id="doctrine",
            command="bash scripts/verify_factory_doctrine.sh",
            lane="python",
            category=StepCategory.POLICY,
            description="Factory doctrine verification",
            timeout_seconds=30,
        ),
        VerificationStep(
            id="dockerhub-base-images",
            command="bash scripts/verify_dockerhub_base_images.sh",
            lane="python",
            category=StepCategory.POLICY,
            description="Dockerfile base image verification",
            timeout_seconds=30,
        ),
        VerificationStep(
            id="docker-workflow-hygiene",
            command="bash scripts/verify_docker_workflow_hygiene.sh",
            lane="python",
            category=StepCategory.POLICY,
            description="Docker workflow registry hygiene",
            timeout_seconds=30,
        ),
        VerificationStep(
            id="helm-workflow-hygiene",
            command="bash scripts/verify_helm_workflow_hygiene.sh",
            lane="python",
            category=StepCategory.POLICY,
            description="Helm version pin hygiene verification",
            timeout_seconds=30,
        ),
        VerificationStep(
            id="docker-build-locality",
            command="bash scripts/verify_docker_build_locality.sh",
            lane="python",
            category=StepCategory.POLICY,
            description="Docker build locality hygiene",
            timeout_seconds=30,
        ),
        VerificationStep(
            id="structured-output",
            command="bash scripts/verify_health_loop_structured_output.sh",
            lane="python",
            category=StepCategory.POLICY,
            description="Health loop structured output hygiene",
            timeout_seconds=30,
        ),
        VerificationStep(
            id="agent-pipeline",
            command="python scripts/verify_agentic_pipeline.py",
            lane="python",
            category=StepCategory.POLICY,
            description="Agentic pipeline doctrine verification",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="llm-evidence-boundaries",
            command="python scripts/verify_llm_evidence_boundaries.py",
            lane="python",
            category=StepCategory.POLICY,
            description="LLM evidence boundaries verification",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="llm-semantic-injection",
            command="python scripts/verify_llm_semantic_injection_detection.py",
            lane="python",
            category=StepCategory.POLICY,
            description="Semantic injection detection verification",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="ci-gate-drift",
            command="python scripts/verify_ci_gate_drift.py",
            lane="python",
            category=StepCategory.POLICY,
            description="CI workflow gate mapping drift check",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="incident-report-quality",
            command="python scripts/verify_incident_report_quality.py",
            lane="python",
            category=StepCategory.POLICY,
            description="Incident report quality invariants",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="artifact-immutability",
            command="python scripts/verify_artifact_immutability.py",
            lane="python",
            category=StepCategory.POLICY,
            description="Artifact immutability enforcement",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="production-readiness-disclaimer",
            command="python scripts/verify_production_readiness_disclaimer.py",
            lane="python",
            category=StepCategory.POLICY,
            description="Production readiness disclaimers",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="discovery-logging-hygiene",
            command="python scripts/verify_discovery_logging_hygiene.py",
            lane="python",
            category=StepCategory.POLICY,
            description="Discovery strategy logging hygiene",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="next-check-sanitization",
            command="python scripts/verify_next_check_sanitization_hygiene.py",
            lane="python",
            category=StepCategory.POLICY,
            description="Next-check sanitization hygiene",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="operator-projection-hygiene",
            command="python scripts/verify_operator_projection_hygiene.py",
            lane="python",
            category=StepCategory.POLICY,
            description="Operator projection sanitization hygiene",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="pvc-rollout-policy",
            command="python scripts/verify_pvc_rollout_policy.py",
            lane="python",
            category=StepCategory.POLICY,
            description="PVC rollout policy verification (Recreate for single-writer)",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="shared-pvc-colocation",
            command="python scripts/verify_shared_pvc_colocation.py",
            lane="python",
            category=StepCategory.POLICY,
            description="Shared PVC colocation policy",
            timeout_seconds=60,
        ),
    ])

    # --- Python Full-Suite Steps (expensive) ---
    steps.extend([
        VerificationStep(
            id="unit-tests",
            command="bash scripts/run_unit_tests.sh",
            lane="python",
            category=StepCategory.FULL_SUITE,
            description="Full Python unit test suite",
            timeout_seconds=600,
            is_expensive=True,
        ),
    ])

    # --- Python Docs Steps ---
    steps.extend([
        VerificationStep(
            id="docs-inventory",
            command="python scripts/verify_docs_inventory.py",
            lane="python",
            category=StepCategory.DOCS,
            description="Docs inventory integrity",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="docs-claims-registry",
            command="python scripts/verify_docs_claims_registry.py",
            lane="python",
            category=StepCategory.DOCS,
            description="Docs claims registry integrity",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="docs-claim-traceability",
            command="python scripts/verify_docs_claim_traceability.py",
            lane="python",
            category=StepCategory.DOCS,
            description="Docs claim traceability matrix",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="docs-claim-candidates",
            command="python scripts/scan_docs_claim_candidates.py",
            lane="python",
            category=StepCategory.DOCS,
            description="Docs claim candidate scanning",
            timeout_seconds=120,
        ),
        VerificationStep(
            id="docs-claim-candidate-coverage",
            command="python scripts/verify_docs_claim_candidate_coverage.py",
            lane="python",
            category=StepCategory.DOCS,
            description="Docs claim candidate coverage verification",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="docs-claim-candidate-dispositions",
            command="python scripts/verify_docs_claim_candidate_dispositions.py",
            lane="python",
            category=StepCategory.DOCS,
            description="Docs claim candidate dispositions verification",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="docs-claim-disposition-csv-integrity",
            command="python scripts/verify_docs_claim_disposition_csv_integrity.py",
            lane="python",
            category=StepCategory.DOCS,
            description="Disposition shard CSV integrity verification",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="docs-claim-disposition-semantic-diff-self-test",
            command="python scripts/diff_docs_claim_dispositions.py --self-test",
            lane="python",
            category=StepCategory.DOCS,
            description="Disposition semantic diff self-test",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="docs-claim-candidate-backlog-report-self-test",
            command="python scripts/run_backlog_report.py --self-test",
            lane="python",
            category=StepCategory.DOCS,
            description="Claim candidate backlog report self-test",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="data-model-docs",
            command="python scripts/verify_data_model_docs.py",
            lane="python",
            category=StepCategory.DOCS,
            description="Data model documentation hygiene",
            timeout_seconds=60,
        ),
    ])

    # --- Frontend Steps ---
    steps.extend([
        VerificationStep(
            id="npm-ci",
            command="npm ci",
            lane="frontend",
            category=StepCategory.BUILD,
            description="Install frontend dependencies",
            timeout_seconds=180,
            is_expensive=True,
        ),
        VerificationStep(
            id="npm-test-ui",
            command="bash scripts/run_frontend_ui_tests.sh",
            lane="frontend",
            category=StepCategory.SMOKE,
            description="Frontend UI tests (smoke)",
            timeout_seconds=300,
            is_expensive=True,
        ),
        VerificationStep(
            id="npm-build",
            command="npm run build",
            lane="frontend",
            category=StepCategory.BUILD,
            description="Frontend production build",
            timeout_seconds=120,
            is_expensive=True,
        ),
    ])

    # --- Helm Steps ---
    steps.extend([
        VerificationStep(
            id="helm-chart",
            command="bash scripts/verify_helm_chart.sh",
            lane="helm",
            category=StepCategory.POLICY,
            description="Helm chart verification",
            timeout_seconds=60,
        ),
        VerificationStep(
            id="helm-oci-login",
            command="bash scripts/verify_helm_oci_login.sh",
            lane="helm",
            category=StepCategory.POLICY,
            description="Helm OCI dual-login workaround verification",
            timeout_seconds=30,
        ),
    ])

    return steps


# =============================================================================
# Profile Definitions
# =============================================================================


def get_profiles() -> dict[str, VerificationProfile]:
    """Return all verification profile definitions."""

    # Fast profile: policy + smoke checks, no full suites
    fast_includes = [
        # Core linting and typing
        "ruff-lint",
        "mypy",
        "mypy-tests",
        # Policy/doctrine checks
        "doctrine",
        "dockerhub-base-images",
        "docker-workflow-hygiene",
        "helm-workflow-hygiene",
        "docker-build-locality",
        "structured-output",
        "agent-pipeline",
        "llm-evidence-boundaries",
        "llm-semantic-injection",
        "ci-gate-drift",
        "incident-report-quality",
        "artifact-immutability",
        "production-readiness-disclaimer",
        "discovery-logging-hygiene",
        "next-check-sanitization",
        "operator-projection-hygiene",
        "pvc-rollout-policy",
        "shared-pvc-colocation",
        # File size check
        "llm-friendly",
        # Helm quick checks
        "helm-chart",
        "helm-oci-login",
        # Docs basic checks
        "docs-inventory",
        "docs-claims-registry",
    ]

    # Full profile: everything
    full_includes = [step.id for step in get_all_steps()]

    return {
    "fast": VerificationProfile(
        name="fast",
        description="Local default profile - high-signal policy and smoke checks",
        target_time_seconds=60,
        ideal_time_seconds=45,
        includes=fast_includes,
        excludes=[
            # Explicitly exclude expensive full suites
            "unit-tests",
            "npm-ci",
            "npm-test-ui",
            "npm-build",
            # Docs heavy scans (can be slow)
            "docs-claim-traceability",
            "docs-claim-candidates",
            "data-model-docs",
            # Additional docs claim checks (shell is conservative)
            "docs-claim-candidate-coverage",
            "docs-claim-candidate-dispositions",
            "docs-claim-disposition-csv-integrity",
            "docs-claim-disposition-semantic-diff-self-test",
            "docs-claim-candidate-backlog-report-self-test",
        ],
        escalation_command="./scripts/verify_all.sh --full",
    ),
        "full": VerificationProfile(
            name="full",
            description="Exhaustive merge-grade verification",
            target_time_seconds=300,
            ideal_time_seconds=180,
            includes=full_includes,
            excludes=[],
            escalation_command="",
        ),
    }


# =============================================================================
# Profile Resolution
# =============================================================================


def resolve_profile(profile_name: str, step_filter: Optional[list[str]] = None) -> tuple[list[VerificationStep], list[str]]:
    """
    Resolve a profile name to a list of steps to run.

    Returns:
        Tuple of (steps_to_run, steps_skipped)
    """
    all_steps = {step.id: step for step in get_all_steps()}
    profiles = get_profiles()

    if profile_name not in profiles:
        raise ValueError(f"Unknown profile: {profile_name}. Available: {list(profiles.keys())}")

    profile = profiles[profile_name]

    # Start with all steps or filtered subset
    if step_filter:
        steps_to_run = {sid: all_steps[sid] for sid in step_filter if sid in all_steps}
        all_step_ids = set(all_steps.keys())
        steps_skipped = sorted(all_step_ids - set(steps_to_run.keys()))
    else:
        steps_to_run = dict(all_steps)
        steps_skipped = []

    # Apply profile excludes
    for exclude_id in profile.excludes:
        if exclude_id in steps_to_run:
            del steps_to_run[exclude_id]
            steps_skipped.append(exclude_id)

    # Apply profile includes (intersection)
    if profile.includes:
        included = set(profile.includes)
        to_run_ids = set(steps_to_run.keys()) & included
        steps_to_run = {sid: steps_to_run[sid] for sid in to_run_ids}
        # Track explicitly excluded from fast
        if profile_name == "fast":
            explicitly_excluded = included - to_run_ids
            for sid in sorted(explicitly_excluded):
                if sid not in steps_skipped:
                    steps_skipped.append(sid)

    return list(steps_to_run.values()), sorted(steps_skipped)


def get_profile_summary(profile_name: str) -> dict:
    """Get a summary of a profile for display."""
    steps, skipped = resolve_profile(profile_name)

    return {
        "profile": profile_name,
        "profile_description": get_profiles()[profile_name].description,
        "target_time_seconds": get_profiles()[profile_name].target_time_seconds,
        "ideal_time_seconds": get_profiles()[profile_name].ideal_time_seconds,
        "steps_count": len(steps),
        "steps": [
            {
                "id": step.id,
                "command": step.command,
                "lane": step.lane,
                "category": step.category.value,
                "description": step.description,
            }
            for step in sorted(steps, key=lambda s: (s.lane, s.id))
        ],
        "skipped_count": len(skipped),
        "skipped": skipped,
        "escalation_command": get_profiles()[profile_name].escalation_command,
    }


# =============================================================================
# CLI Interface
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Verification profile definitions and executor"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available profiles",
    )
    parser.add_argument(
        "--profile",
        choices=["fast", "full"],
        help="Show steps for a specific profile",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate profile contracts",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    if args.list:
        profiles = get_profiles()
        if args.json:
            output = {
                "profiles": {
                    name: {
                        "description": p.description,
                        "target_time_seconds": p.target_time_seconds,
                        "ideal_time_seconds": p.ideal_time_seconds,
                    }
                    for name, p in profiles.items()
                }
            }
            print(json.dumps(output, indent=2))
        else:
            print("Available verification profiles:")
            print()
            for name, profile in profiles.items():
                print(f"  {name}: {profile.description}")
                print(f"    Target: ≤{profile.target_time_seconds}s (ideal: ≤{profile.ideal_time_seconds}s)")
                print()
        return 0

    if args.profile:
        summary = get_profile_summary(args.profile)
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"Profile: {summary['profile']}")
            print(f"Description: {summary['profile_description']}")
            print(f"Target time: ≤{summary['target_time_seconds']}s (ideal: ≤{summary['ideal_time_seconds']}s)")
            print()
            print(f"Steps ({summary['steps_count']}):")
            for step in summary['steps']:
                print(f"  [{step['lane']}] {step['id']} - {step['description']}")
                print(f"    Command: {step['command']}")
            print()
            if summary['skipped']:
                print(f"Skipped ({summary['skipped_count']}):")
                for sid in summary['skipped']:
                    print(f"  - {sid}")
                print()
            if summary['escalation_command']:
                print(f"For merge-grade verification:")
                print(f"  {summary['escalation_command']}")
        return 0

    if args.validate:
        errors = validate_profiles()
        if errors:
            print("Profile validation errors:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return 1
        print("Profile validation: PASSED")
        return 0

    parser.print_help()
    return 0


def validate_profiles() -> list[str]:
    """Validate profile definitions."""
    errors = []
    all_steps = {step.id for step in get_all_steps()}
    profiles = get_profiles()

    for profile_name, profile in profiles.items():
        # Check includes exist
        for step_id in profile.includes:
            if step_id not in all_steps:
                errors.append(f"{profile_name}: includes unknown step '{step_id}'")

        # Check excludes exist
        for step_id in profile.excludes:
            if step_id not in all_steps:
                errors.append(f"{profile_name}: excludes unknown step '{step_id}'")

        # Fast profile should not include expensive steps
        if profile_name == "fast":
            expensive_steps = {s.id for s in get_all_steps() if s.is_expensive}
            fast_includes = set(profile.includes) - set(profile.excludes)
            expensive_in_fast = fast_includes & expensive_steps
            if expensive_in_fast:
                errors.append(
                    f"fast: should not include expensive steps: {sorted(expensive_in_fast)}"
                )

        # Full profile should include all non-excluded steps
        if profile_name == "full":
            full_includes = set(profile.includes)
            excluded_from_full = set(profile.excludes)
            expected_full = all_steps - excluded_from_full
            missing = expected_full - full_includes
            if missing:
                errors.append(f"full: missing steps: {sorted(missing)}")

    return errors


if __name__ == "__main__":
    sys.exit(main())
