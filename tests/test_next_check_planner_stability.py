"""Tests for next-check planner stability and idempotence."""

from __future__ import annotations

from pathlib import Path

from k8s_diag_agent.external_analysis.next_check_planner import plan_next_checks
from tests.helpers.next_check_planner_helpers import _build_enrichment_artifact, _write_review


def test_candidate_id_is_stable(tmp_path: Path) -> None:
    """Test that candidate IDs are stable across multiple planning calls."""
    run_id = "run-stable"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [
            {
                "label": "cluster-stable",
                "context": "cluster-stable",
                "reasons": ["missing_metrics"],
            }
        ],
    )
    artifact = _build_enrichment_artifact(run_id, ("kubectl logs deployment/stable",))
    ids: list[str | None] = []
    for _ in range(2):
        plan = plan_next_checks(review_path, run_id, artifact)
        assert plan is not None
        assert plan.candidates
        ids.append(plan.candidates[0].candidate_id)
    assert ids[0]
    assert all(candidate_id == ids[0] for candidate_id in ids)
