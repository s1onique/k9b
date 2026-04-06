"""Recommendation logic for next evidence and actions."""
from __future__ import annotations

from collections.abc import Iterable

from ..models import Hypothesis, NextCheck, RecommendedAction, SafetyLevel


def propose_next_steps(hypotheses: Iterable[Hypothesis]) -> list[NextCheck]:
    checks: list[NextCheck] = []
    for idx, hypothesis in enumerate(hypotheses):
        checks.append(
            NextCheck(
                description="Gather detailed pod logs and describe the most recent restart.",
                owner="platform engineer",
                method="kubectl",
                evidence_needed=["logs", "events"],
            )
        )
        if idx == 0:
            break
    if not checks:
        checks.append(
            NextCheck(
                description="Collect cluster node conditions and observability data.",
                owner="platform engineer",
                method="kubectl",
            )
        )
    return checks


def build_recommended_action() -> RecommendedAction:
    return RecommendedAction(
        type="observation",
        description="Inspect the pod logs and describe output before restarting or rolling back.",
        references=["CrashLoopBackOff", "missing logs"],
        safety_level=SafetyLevel.LOW_RISK,
    )
