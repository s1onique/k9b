"""Feedback useful fixture helpers for incident report adaptation tests.

Fixtures:
- _fixture_useful_result_hypothesis_strengthened: useful feedback strengthens hypothesis
"""

from __future__ import annotations

from typing import cast

from tests.fixtures.incident_report_fixtures_base import JsonObject


def _fixture_useful_result_hypothesis_strengthened() -> dict[str, object]:
    """Build a UI index with useful feedback that strengthens the leading hypothesis."""
    from tests.fixtures.incident_report_fixtures_worklist import (
        _fixture_executed_with_usefulness,
    )

    index = _fixture_executed_with_usefulness()
    run_entry = cast(JsonObject, index["run"])

    history = cast(list[dict[str, object]], run_entry["next_check_execution_history"])
    if history:
        history[0]["usefulnessClass"] = "useful"
        history[0]["usefulnessSummary"] = "Found key crash events confirming CrashLoopBackOff pattern"
        history[0]["resultClass"] = "useful-signal"
        history[0]["resultSummary"] = "Captured pod events showing repeated crash restarts."

    queue = cast(list[dict[str, object]], run_entry["next_check_queue"])
    if queue:
        queue[0]["usefulnessClass"] = "useful"
        queue[0]["usefulnessSummary"] = "Found key crash events"
        queue[0]["resultClass"] = "useful-signal"
        queue[0]["resultSummary"] = "Captured pod events showing repeated crash restarts."
        queue[0]["executionState"] = "executed-success"
        queue[0]["queueStatus"] = "completed"

    return index
