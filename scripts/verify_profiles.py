#!/usr/bin/env python3
"""
Verification profile definitions.

This module provides verification profile definitions for reference and testing.
The authoritative profile resolution logic lives in:
- verify_profile_model.py: Step registry and profile definitions
- verify_profile_plan.py: Profile resolution and plan generation

Usage:
    python scripts/verify_profiles.py --list           # List all profiles
    python scripts/verify_profiles.py --profile fast    # Show fast profile steps
    python scripts/verify_profiles.py --validate       # Validate profile contracts

Note: For profile resolution and step plan generation, use:
    python scripts/verify_profile_executor.py --resolve --profile fast
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# Import from the authoritative modules
from verify_profile_model import (
    STEPS,
    FAST_EXCLUDES,
    StepCategory,
)
from verify_profile_plan import (
    resolve_profile as plan_resolve_profile,
    get_profile_metadata as plan_get_profile_metadata,
)


# =============================================================================
# Profile Enums and Dataclasses (for backward compatibility)
# =============================================================================


class Profile(Enum):
    """Verification profile names."""
    FAST = "fast"
    FULL = "full"
    CHANGED = "changed"


@dataclass(frozen=True)
class VerificationStep:
    """A single verification step."""
    id: str
    command: str
    lane: str
    category: StepCategory
    description: str = ""
    timeout_seconds: int = 300
    is_expensive: bool = False

    @classmethod
    def from_registry(cls, step_id: str) -> "VerificationStep":
        """Create VerificationStep from registry."""
        step_def = STEPS[step_id]
        return cls(
            id=step_id,
            command=step_def["command"],
            lane=step_def["lane"],
            category=step_def["category"],
            description=step_def["description"],
            is_expensive=step_def["is_expensive"],
        )

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
    includes: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)
    escalation_command: str = ""


# =============================================================================
# Step Registry
# =============================================================================


def get_all_steps() -> list[VerificationStep]:
    """Return all known verification steps."""
    return [VerificationStep.from_registry(step_id) for step_id in STEPS]


# =============================================================================
# Profile Definitions
# =============================================================================


def get_profiles() -> dict[str, VerificationProfile]:
    """Return all verification profile definitions."""

    # Fast profile includes
    fast_includes = [
        "ruff-lint", "mypy", "mypy-tests",
        "doctrine", "dockerhub-base-images", "docker-workflow-hygiene",
        "helm-workflow-hygiene", "docker-build-locality", "structured-output",
        "agent-pipeline", "llm-evidence-boundaries", "llm-semantic-injection",
        "ci-gate-drift", "incident-report-quality", "artifact-immutability",
        "production-readiness-disclaimer", "discovery-logging-hygiene",
        "next-check-sanitization", "operator-projection-hygiene",
        "pvc-rollout-policy", "shared-pvc-colocation",
        "llm-friendly", "shell-containment",
        "helm-chart", "helm-oci-login",
        "docs-inventory", "docs-claims-registry",
    ]

    return {
        "fast": VerificationProfile(
            name="fast",
            description="Local default profile - high-signal policy and smoke checks",
            target_time_seconds=60,
            ideal_time_seconds=45,
            includes=fast_includes,
            excludes=list(FAST_EXCLUDES),
            escalation_command="./scripts/verify_all.sh --full",
        ),
        "full": VerificationProfile(
            name="full",
            description="Exhaustive merge-grade verification",
            target_time_seconds=300,
            ideal_time_seconds=180,
            includes=[step.id for step in get_all_steps()],
            excludes=[],
            escalation_command="",
        ),
    }


# =============================================================================
# Profile Resolution
# =============================================================================


def resolve_profile(profile_name: str, step_filter: Optional[list[str]] = None) -> tuple[list[VerificationStep], list[str]]:
    """Resolve a profile name to a list of steps."""
    all_steps = {step.id: step for step in get_all_steps()}
    profiles = get_profiles()

    if profile_name not in profiles:
        raise ValueError(f"Unknown profile: {profile_name}. Available: {list(profiles.keys())}")

    profile = profiles[profile_name]

    if step_filter:
        steps_to_run = {sid: all_steps[sid] for sid in step_filter if sid in all_steps}
        steps_skipped = sorted(set(all_steps.keys()) - set(steps_to_run.keys()))
    else:
        steps_to_run = dict(all_steps)
        steps_skipped = []

    for exclude_id in profile.excludes:
        if exclude_id in steps_to_run:
            del steps_to_run[exclude_id]
            steps_skipped.append(exclude_id)

    if profile.includes:
        included = set(profile.includes)
        to_run_ids = set(steps_to_run.keys()) & included
        steps_to_run = {sid: steps_to_run[sid] for sid in to_run_ids}
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
    parser = argparse.ArgumentParser(description="Verification profile definitions")
    parser.add_argument("--list", action="store_true", help="List all available profiles")
    parser.add_argument("--profile", choices=["fast", "full"], help="Show steps for a profile")
    parser.add_argument("--validate", action="store_true", help="Validate profile contracts")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.list:
        profiles = get_profiles()
        if args.json:
            print(json.dumps({
                "profiles": {
                    name: {"description": p.description, "target_time_seconds": p.target_time_seconds, "ideal_time_seconds": p.ideal_time_seconds}
                    for name, p in profiles.items()
                }
            }, indent=2))
        else:
            print("Available verification profiles:")
            for name, profile in profiles.items():
                print(f"  {name}: {profile.description}")
                print(f"    Target: ≤{profile.target_time_seconds}s (ideal: ≤{profile.ideal_time_seconds}s)")
        return 0

    if args.profile:
        summary = get_profile_summary(args.profile)
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"Profile: {summary['profile']}")
            print(f"Description: {summary['profile_description']}")
            print(f"Steps ({summary['steps_count']}):")
            for step in summary['steps']:
                print(f"  [{step['lane']}] {step['id']} - {step['description']}")
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
        for step_id in profile.includes:
            if step_id not in all_steps:
                errors.append(f"{profile_name}: includes unknown step '{step_id}'")
        for step_id in profile.excludes:
            if step_id not in all_steps:
                errors.append(f"{profile_name}: excludes unknown step '{step_id}'")

    return errors


if __name__ == "__main__":
    sys.exit(main())
