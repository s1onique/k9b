"""Regression fixtures for artifact filtering provenance quality (BETA-G7).

This module provides fixture builders that construct synthetic artifacts
with specific filtering characteristics for testing:

- Skipped artifacts (should be filtered)
- Placeholder artifacts (adapter-not-registered)
- Useful artifacts (should be preserved)
- Partial artifacts (should be preserved)
- Empty artifacts (should be filtered)
- Mixed refs (only some filtered)

Usage:
    from tests.fixtures.incident_report_filtering_fixtures import (
        _fixture_skipped_external_analysis,
        _fixture_adapter_not_registered,
        _fixture_useful_execution_artifact,
        _fixture_partial_diagnostic_artifact,
        _fixture_empty_placeholder,
    )

    # Use with filter_artifact_links
    from k8s_diag_agent.ui.api_incident_report_filtering import filter_artifact_links

    result = filter_artifact_links(links, runs_dir)
"""

from __future__ import annotations

import json
from pathlib import Path

from k8s_diag_agent.external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus


def _fixture_skipped_external_analysis(
    run_id: str = "run-filtering-test",
    cluster_label: str = "cluster-a",
    skip_reason: str = "Adapter not configured for external analysis",
) -> dict[str, object]:
    """Create a skipped external-analysis artifact fixture.

    This artifact has status=skipped and should be filtered from provenance.
    """
    artifact = ExternalAnalysisArtifact(
        tool_name="k8sgpt",
        run_id=run_id,
        cluster_label=cluster_label,
        status=ExternalAnalysisStatus.SKIPPED,
        skip_reason=skip_reason,
        summary="Skipped: adapter not configured",
    )
    return artifact.to_dict()


def _fixture_adapter_not_registered(
    run_id: str = "run-filtering-test",
    cluster_label: str = "cluster-a",
) -> dict[str, object]:
    """Create an adapter-not-registered review-enrichment artifact fixture.

    This artifact has a placeholder summary indicating no meaningful evidence.
    Should be filtered from provenance.
    """
    artifact = ExternalAnalysisArtifact(
        tool_name="review-enrichment",
        run_id=run_id,
        cluster_label=cluster_label,
        status=ExternalAnalysisStatus.SKIPPED,
        summary="Adapter is not registered for review enrichment",
        skip_reason="Adapter is not registered",
    )
    return artifact.to_dict()


def _fixture_useful_execution_artifact(
    run_id: str = "run-filtering-test",
    cluster_label: str = "cluster-a",
) -> dict[str, object]:
    """Create a useful execution artifact with diagnostic content.

    This artifact has actual evidence content and should be preserved in provenance.
    """
    artifact = ExternalAnalysisArtifact(
        tool_name="kubectl-logs",
        run_id=run_id,
        cluster_label=cluster_label,
        status=ExternalAnalysisStatus.SUCCESS,
        summary="Collected pod logs showing CrashLoopBackOff pattern",
        raw_output="""2026-01-01 10:00:00 Pod my-pod started
2026-01-01 10:00:05 Container exited with code 1
2026-01-01 10:00:10 Back-off restarting failed container
2026-01-01 10:00:15 CrashLoopBackOff confirmed""",
        findings=("CrashLoopBackOff pattern detected",),
        suggested_next_checks=("Check container image", "Review resource limits"),
    )
    return artifact.to_dict()


def _fixture_partial_diagnostic_artifact(
    run_id: str = "run-filtering-test",
    cluster_label: str = "cluster-a",
) -> dict[str, object]:
    """Create a partial diagnostic artifact with partial evidence.

    This artifact has partial evidence but still provides diagnostic value.
    Should be preserved in provenance.
    """
    artifact = ExternalAnalysisArtifact(
        tool_name="kubectl-top",
        run_id=run_id,
        cluster_label=cluster_label,
        status=ExternalAnalysisStatus.SUCCESS,
        summary="Partial metrics: CPU available, memory unknown",
        payload={
            "cpu_usage_millicores": 450,
            "memory_usage_mb": None,  # Not available
            "note": "Memory metrics server returned partial data",
        },
    )
    return artifact.to_dict()


def _fixture_failed_with_diagnostic_context(
    run_id: str = "run-filtering-test",
    cluster_label: str = "cluster-a",
) -> dict[str, object]:
    """Create a failed artifact with diagnostic context.

    This artifact failed but contains useful error context.
    Should be preserved in provenance.
    """
    artifact = ExternalAnalysisArtifact(
        tool_name="kubectl-logs",
        run_id=run_id,
        cluster_label=cluster_label,
        status=ExternalAnalysisStatus.FAILED,
        error_summary="Pod not found in namespace production; check deployment status",
        failure_metadata={
            "failure_class": "not_found",
            "namespace": "production",
            "suggested_next_move": "Check if deployment exists and pod is scheduled",
        },
    )
    return artifact.to_dict()


def _fixture_empty_placeholder(
    run_id: str = "run-filtering-test",
    cluster_label: str = "cluster-a",
) -> dict[str, object]:
    """Create an empty placeholder artifact.

    This artifact has no content and should be filtered from provenance.
    """
    artifact = ExternalAnalysisArtifact(
        tool_name="placeholder",
        run_id=run_id,
        cluster_label=cluster_label,
        status=ExternalAnalysisStatus.SUCCESS,
        # No summary, no raw_output, no payload
    )
    return artifact.to_dict()


def _fixture_mixed_refs_with_filtering(
    tmpdir: Path,
    run_id: str = "run-filtering-test",
) -> list[dict[str, object]]:
    """Create a mixed refs scenario with some to filter and some to preserve.

    Returns a list of (link_dict, artifact_dict) tuples for testing.
    """
    links_and_artifacts = []

    # 1. Useful artifact - should be preserved
    useful_artifact = ExternalAnalysisArtifact(
        tool_name="kubectl-logs",
        run_id=run_id,
        cluster_label="cluster-a",
        status=ExternalAnalysisStatus.SUCCESS,
        summary="Found crash events",
        raw_output="CrashLoopBackOff: Exit code 1",
    )
    useful_path = tmpdir / f"runs/{run_id}/external-analysis/useful-logs.json"
    useful_path.parent.mkdir(parents=True, exist_ok=True)
    useful_path.write_text(json.dumps(useful_artifact.to_dict()))

    links_and_artifacts.append({
        "link": {"label": "Useful Logs", "path": str(useful_path.relative_to(tmpdir))},
        "artifact": useful_artifact,
        "should_preserve": True,
    })

    # 2. Skipped artifact - should be filtered
    skipped_artifact = ExternalAnalysisArtifact(
        tool_name="k8sgpt",
        run_id=run_id,
        cluster_label="cluster-a",
        status=ExternalAnalysisStatus.SKIPPED,
        skip_reason="Adapter not configured",
    )
    skipped_path = tmpdir / f"runs/{run_id}/external-analysis/skipped-k8sgpt.json"
    skipped_path.parent.mkdir(parents=True, exist_ok=True)
    skipped_path.write_text(json.dumps(skipped_artifact.to_dict()))

    links_and_artifacts.append({
        "link": {"label": "Skipped K8sGPT", "path": str(skipped_path.relative_to(tmpdir))},
        "artifact": skipped_artifact,
        "should_preserve": False,
    })

    # 3. Placeholder enrichment - should be filtered
    placeholder_artifact = ExternalAnalysisArtifact(
        tool_name="review-enrichment",
        run_id=run_id,
        cluster_label="cluster-a",
        status=ExternalAnalysisStatus.SKIPPED,
        summary="Adapter is not registered",
    )
    placeholder_path = tmpdir / f"runs/{run_id}/external-analysis/placeholder-enrichment.json"
    placeholder_path.parent.mkdir(parents=True, exist_ok=True)
    placeholder_path.write_text(json.dumps(placeholder_artifact.to_dict()))

    links_and_artifacts.append({
        "link": {"label": "Placeholder Enrichment", "path": str(placeholder_path.relative_to(tmpdir))},
        "artifact": placeholder_artifact,
        "should_preserve": False,
    })

    # 4. Failed with diagnostic context - should be preserved
    failed_artifact = ExternalAnalysisArtifact(
        tool_name="kubectl-top",
        run_id=run_id,
        cluster_label="cluster-a",
        status=ExternalAnalysisStatus.FAILED,
        error_summary="Metrics server unavailable",
        failure_metadata={
            "failure_class": "upstream_timeout",
            "suggested_next_move": "Check metrics-server pod health",
        },
    )
    failed_path = tmpdir / f"runs/{run_id}/external-analysis/failed-metrics.json"
    failed_path.parent.mkdir(parents=True, exist_ok=True)
    failed_path.write_text(json.dumps(failed_artifact.to_dict()))

    links_and_artifacts.append({
        "link": {"label": "Failed Metrics", "path": str(failed_path.relative_to(tmpdir))},
        "artifact": failed_artifact,
        "should_preserve": True,
    })

    return links_and_artifacts


def write_fixture_artifact(tmpdir: Path, artifact_dict: dict[str, object], relative_path: str) -> Path:
    """Write an artifact fixture to a temp directory.

    Args:
        tmpdir: Temporary directory to write to
        artifact_dict: Artifact dict from to_dict()
        relative_path: Relative path for the artifact file

    Returns:
        Path to the written artifact file
    """
    path = tmpdir / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact_dict))
    return path