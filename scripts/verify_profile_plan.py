#!/usr/bin/env python3
"""
Profile plan resolution - generates step execution plans.

This module handles profile resolution and plan generation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from verify_profile_model import (
    STEPS,
    FAST_EXCLUDES,
    LANE_SCOPES,
    StepPlan,
    ProfileMetadata,
    get_skipped_reasons,
)


def resolve_profile(
    profile: str,
    scope: str = "all",
) -> StepPlan:
    """
    Resolve a profile and scope to a step plan.
    """
    if not profile or profile == "fast":
        effective_profile = "fast"
    elif profile == "full":
        effective_profile = "full"
    else:
        raise ValueError(f"Unknown profile: {profile}")
    
    is_full_lane = scope in LANE_SCOPES
    if is_full_lane:
        effective_profile = "full"
    
    steps_to_run = []
    steps_skipped = []
    
    for step_id, step_def in STEPS.items():
        if scope != "all" and step_def["lane"] != scope:
            continue
        
        if effective_profile == "fast" and step_id in FAST_EXCLUDES:
            steps_skipped.append(step_id)
        else:
            steps_to_run.append({
                "id": step_id,
                "lane": step_def["lane"],
                "command": step_def["command"],
                "description": step_def["description"],
            })
    
    return StepPlan(
        profile=effective_profile,
        scope=scope,
        steps=steps_to_run,
        skipped=steps_skipped,
        is_full_lane=is_full_lane,
    )


def get_profile_metadata(profile: str, scope: str = "all") -> ProfileMetadata:
    """Get metadata for a profile."""
    if profile == "full":
        return ProfileMetadata(
            name="full",
            description="Exhaustive merge-grade verification",
            target_time_seconds=300,
            ideal_time_seconds=180,
            escalation_command="",
            is_full_gate=True,
        )
    elif profile == "fast":
        scope_note = f" ({scope} lane)" if scope != "all" else ""
        return ProfileMetadata(
            name="fast",
            description=f"Local default profile - high-signal policy and smoke checks{scope_note}",
            target_time_seconds=60,
            ideal_time_seconds=45,
            escalation_command="./scripts/verify_all.sh --full",
            is_full_gate=False,
        )
    else:
        raise ValueError(f"Unknown profile: {profile}")


def emit_full_plan(profile: str, scope: str) -> dict:
    """Emit the full execution plan for shell consumption."""
    plan = resolve_profile(profile, scope)
    reasons = get_skipped_reasons()
    
    # Organize steps by lane in execution order
    lanes = {"python": [], "frontend": [], "helm": []}
    for step in plan.steps:
        lane = step["lane"]
        if lane in lanes:
            lanes[lane].append(step)
    
    return {
        "profile": plan.profile,
        "scope": plan.scope,
        "is_full_gate": plan.profile == "full",
        "is_full_lane": plan.is_full_lane,
        "metadata": get_profile_metadata(plan.profile, plan.scope).__dict__,
        "lanes": lanes,
        "skipped": [
            {"id": s, "reason": reasons.get(s, "Excluded by profile")}
            for s in sorted(plan.skipped)
        ],
        "step_count": len(plan.steps),
        "skipped_count": len(plan.skipped),
    }


def emit_json_plan(plan: StepPlan) -> dict:
    """Emit JSON representation of the step plan."""
    skipped_reasons = get_skipped_reasons()
    
    return {
        "profile": plan.profile,
        "scope": plan.scope,
        "is_full_gate": plan.profile == "full",
        "is_full_lane": plan.is_full_lane,
        "metadata": get_profile_metadata(plan.profile, plan.scope).__dict__,
        "steps": plan.steps,
        "skipped": [
            {"id": s, "reason": skipped_reasons.get(s, "Excluded by profile")}
            for s in sorted(plan.skipped)
        ],
    }
