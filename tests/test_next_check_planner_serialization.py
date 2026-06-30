"""Tests for next-check planner serialization and failure context."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.next_check_planner import plan_next_checks
from tests.helpers.next_check_planner_helpers import _write_review


def _build_truncated_enrichment_artifact(run_id: str) -> ExternalAnalysisArtifact:
    """Build a FAILED enrichment artifact simulating truncation."""
    return ExternalAnalysisArtifact(
        tool_name="llamacpp",
        run_id=run_id,
        cluster_label="status-run",
        summary="LLM response truncated",
        status=ExternalAnalysisStatus.FAILED,
        artifact_path="external-analysis/enrichment.json",
        provider="llamacpp",
        error_summary="LLM response ended with finish_reason=length before producing parseable JSON",
        failure_metadata={
            "failure_class": "llm_completion_truncated",
            "exception_type": "LLMResponseParseError",
            "finish_reason": "length",
            "completion_stopped_by_length": True,
            "max_tokens": 1200,
        },
    )


def test_truncated_enrichment_returns_plan_with_upstream_failure_context(tmp_path: Path) -> None:
    """Regression test: plan_next_checks attaches upstream_failure_context when enrichment fails."""
    run_id = "run-truncated"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [{"label": "cluster-a", "context": "cluster-a", "reasons": ["test"]}],
    )
    artifact = _build_truncated_enrichment_artifact(run_id)

    plan = plan_next_checks(review_path, run_id, artifact)

    # Must return a plan (not None) even on failure
    assert plan is not None, "Plan must not be None when enrichment fails"
    # Candidates must be empty - we don't invent checks from truncated enrichment
    assert plan.candidates == (), "Candidates must be empty for failed enrichment"
    # Upstream failure context MUST be attached
    assert plan.upstream_failure_context is not None, "upstream_failure_context must be attached"

    ctx = plan.upstream_failure_context
    assert ctx["source_enrichment_status"] == "failed"
    assert ctx["source_status"] == "failed"
    assert ctx["source_failure_class"] == "llm_completion_truncated"
    assert ctx["source_failure_class_normalized"] == "llm_completion_truncated"
    assert ctx["source_finish_reason"] == "length"
    assert ctx["source_completion_stopped_by_length"] is True
    assert "LLM response ended" in str(ctx["source_error_summary"])


def test_truncated_enrichment_payload_includes_upstream_failure_context(tmp_path: Path) -> None:
    """Regression test: to_payload() includes upstream_failure_context in serialized output."""
    run_id = "run-truncated-payload"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [{"label": "cluster-a", "context": "cluster-a", "reasons": ["test"]}],
    )
    artifact = _build_truncated_enrichment_artifact(run_id)

    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None

    payload = plan.to_payload()
    assert "upstream_failure_context" in payload, "Payload must include upstream_failure_context"

    ctx = payload["upstream_failure_context"]
    assert isinstance(ctx, dict), "upstream_failure_context must be a dict"
    ctx = cast(dict[str, object], ctx)
    assert ctx["source_enrichment_status"] == "failed"
    assert ctx["source_failure_class"] == "llm_completion_truncated"
    assert ctx["source_completion_stopped_by_length"] is True


def test_failure_class_case_insensitive_normalization(tmp_path: Path) -> None:
    """Regression test: failure_class_normalized is lowercased regardless of input case."""
    run_id = "run-uppercase"
    root = tmp_path / "runs" / "health"
    review_path = _write_review(
        root,
        run_id,
        [{"label": "cluster-a", "context": "cluster-a", "reasons": ["test"]}],
    )
    # Build artifact with UPPERCASE failure_class
    artifact = ExternalAnalysisArtifact(
        tool_name="llamacpp",
        run_id=run_id,
        cluster_label="status-run",
        summary="LLM response truncated",
        status=ExternalAnalysisStatus.FAILED,
        artifact_path="external-analysis/enrichment.json",
        provider="llamacpp",
        error_summary="truncated",
        failure_metadata={
            "failure_class": "LLM_COMPLETION_TRUNCATED",  # Uppercase
            "exception_type": "LLMResponseParseError",
            "completion_stopped_by_length": True,
        },
    )

    plan = plan_next_checks(review_path, run_id, artifact)
    assert plan is not None
    assert plan.upstream_failure_context is not None

    ctx = plan.upstream_failure_context
    # Original case preserved
    assert ctx["source_failure_class"] == "LLM_COMPLETION_TRUNCATED"
    # Normalized is lowercase
    assert ctx["source_failure_class_normalized"] == "llm_completion_truncated"
