"""Feedback mutation handlers for the UI server.

This module contains the POST/mutation handlers for feedback workflows:
- usefulness feedback (POST /api/next-check-execution-usefulness)
- alertmanager relevance feedback (POST /api/alertmanager-relevance-feedback)

Functions here accept the request handler instance as the first argument.

Architecture: This module imports from server.py for shared helpers (which are
safe to import at module level as they don't depend on handler instance state).
server.py imports this module, so we must avoid circular imports at module load.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

logger = logging.getLogger(__name__)


def handle_usefulness_feedback(handler: HealthUIRequestHandler) -> None:
    """Handle operator feedback on next-check execution usefulness.

    Accepts artifactPath, usefulnessClass (useful|partial|noisy|empty),
    and optional usefulnessSummary, then creates a separate review artifact
    to preserve the immutable execution artifact.

    This follows the same pattern as Alertmanager relevance feedback.

    Args:
        handler: The HealthUIRequestHandler instance
    """
    from ..external_analysis.artifact import ExternalAnalysisPurpose, UsefulnessClass

    content_length = int(handler.headers.get("Content-Length") or 0)
    if content_length <= 0:
        handler._send_json({"error": "Request body required"}, 400)
        return
    try:
        raw_payload = handler.rfile.read(content_length).decode("utf-8")
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError):
        handler._send_json({"error": "Invalid JSON payload"}, 400)
        return

    # Ensure payload is a dict (defensive against non-object JSON)
    if not isinstance(payload, dict):
        handler._send_json({"error": "Invalid JSON payload"}, 400)
        return

    # Validate required fields
    artifact_path_rel = payload.get("artifactPath")
    if not isinstance(artifact_path_rel, str) or not artifact_path_rel:
        handler._send_json({"error": "artifactPath is required"}, 400)
        return

    usefulness_class_raw = payload.get("usefulnessClass")
    if not isinstance(usefulness_class_raw, str) or not usefulness_class_raw:
        handler._send_json({"error": "usefulnessClass is required"}, 400)
        return

    # Validate usefulness class - only allow the 4 contract values
    try:
        usefulness_class = UsefulnessClass(usefulness_class_raw)
    except ValueError:
        handler._send_json(
            {
                "error": "Invalid usefulnessClass. Must be one of: useful, partial, noisy, empty"
            },
            400,
        )
        return

    # Optional summary
    usefulness_summary = payload.get("usefulnessSummary")
    if usefulness_summary is not None and not isinstance(usefulness_summary, str):
        handler._send_json({"error": "usefulnessSummary must be a string"}, 400)
        return

    # Optional context fields for stage-aware feedback
    review_stage = payload.get("reviewStage")
    if review_stage is not None and not isinstance(review_stage, str):
        handler._send_json({"error": "reviewStage must be a string"}, 400)
        return
    workstream = payload.get("workstream")
    if workstream is not None and not isinstance(workstream, str):
        handler._send_json({"error": "workstream must be a string"}, 400)
        return
    problem_class = payload.get("problemClass")
    if problem_class is not None and not isinstance(problem_class, str):
        handler._send_json({"error": "problemClass must be a string"}, 400)
        return
    judgment_scope = payload.get("judgmentScope")
    if judgment_scope is not None and not isinstance(judgment_scope, str):
        handler._send_json({"error": "judgmentScope must be a string"}, 400)
        return
    reviewer_confidence = payload.get("reviewerConfidence")
    if reviewer_confidence is not None and not isinstance(reviewer_confidence, str):
        handler._send_json({"error": "reviewerConfidence must be a string"}, 400)
        return

    # Resolve artifact path securely
    try:
        artifact_path = (handler.runs_dir / artifact_path_rel).resolve()
    except (OSError, ValueError):
        handler._send_json({"error": "Invalid artifact path"}, 400)
        return

    # Verify path is within runs_dir
    if not str(artifact_path).startswith(str(handler.runs_dir.resolve())):
        handler._send_json({"error": "Artifact path must be within runs directory"}, 400)
        return

    if not artifact_path.exists():
        handler._send_json({"error": "Execution artifact not found"}, 404)
        return

    # Read the execution artifact to extract metadata
    try:
        execution_artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.error(
            "Unable to read execution artifact for usefulness feedback",
            extra={
                "artifact_rel": artifact_path_rel,
                "run_id": artifact_path_rel,
                "error": str(exc),
            },
            exc_info=True,
        )
        handler._send_json({"error": "Unable to read execution artifact"}, 500)
        return

    # Extract execution metadata for the review artifact
    run_id = execution_artifact.get("run_id", "")
    cluster_label = execution_artifact.get("cluster_label", "")
    tool_name = execution_artifact.get("tool_name", "")
    status = execution_artifact.get("status", "")
    timestamp = execution_artifact.get("timestamp", datetime.now(UTC).isoformat())

    # Generate unique review artifact filename and artifact_id (single source of truth)
    review_uuid = str(uuid.uuid4())[:8]
    review_filename = f"{run_id}-next-check-execution-usefulness-review-{review_uuid}.json"
    artifact_id = f"usefulness-review-{review_uuid}"

    # Write review artifact to external-analysis directory
    external_analysis_dir = handler._health_root / "external-analysis"
    external_analysis_dir.mkdir(parents=True, exist_ok=True)
    review_path = external_analysis_dir / review_filename

    # Build review artifact with all context fields
    review_artifact: dict[str, object] = {
        "purpose": ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_USEFULNESS_REVIEW.value,
        "tool_name": tool_name,
        "run_id": run_id,
        "run_label": execution_artifact.get("run_label", ""),
        "cluster_label": cluster_label,
        "status": status,
        "timestamp": timestamp,
        "reviewed_at": datetime.now(UTC).isoformat(),
        # Immutable artifact instance identity for provenance/debugging
        "artifact_id": artifact_id,
        # Link back to original execution artifact
        "source_artifact": str(artifact_path.relative_to(handler._health_root.resolve())),
        # Usefulness judgment
        "usefulness_class": usefulness_class.value,
        "usefulness_summary": usefulness_summary,
        # Include execution summary for context
        "summary": execution_artifact.get("summary"),
        "duration_ms": execution_artifact.get("duration_ms"),
    }

    # Add optional context fields if provided
    if review_stage:
        review_artifact["review_stage"] = review_stage
    if workstream:
        review_artifact["workstream"] = workstream
    if problem_class:
        review_artifact["problem_class"] = problem_class
    if judgment_scope:
        review_artifact["judgment_scope"] = judgment_scope
    if reviewer_confidence:
        review_artifact["reviewer_confidence"] = reviewer_confidence

    try:
        review_path.write_text(json.dumps(review_artifact, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.error(
            "Unable to persist usefulness review artifact",
            extra={
                "review_filename": review_filename,
                "source_artifact_rel": artifact_path_rel,
                "usefulness_class": usefulness_class.value,
                "error": str(exc),
            },
            exc_info=True,
        )
        handler._send_json({"error": "Unable to persist review artifact"}, 500)
        return

    logger.info(
        "Operator recorded usefulness feedback",
        extra={
            "review_filename": review_filename,
            "source_artifact_rel": artifact_path_rel,
            "usefulness_class": usefulness_class.value,
            # NOTE: usefulness_summary intentionally excluded from logs
        },
    )

    # Invalidate UI caches so the new review shows up immediately
    ui_index_path = handler.runs_dir / "health" / "ui-index.json"
    if ui_index_path.exists():
        try:
            ui_index_path.touch()
        except OSError:
            pass  # Non-fatal

    handler._send_json({
        "status": "success",
        "summary": "Usefulness feedback recorded",
        "usefulnessClass": usefulness_class.value,
        "usefulnessSummary": usefulness_summary,
        "reviewArtifactPath": str(review_path.relative_to(handler._health_root.resolve())),
    })


def handle_alertmanager_relevance_feedback(handler: HealthUIRequestHandler) -> None:
    """Handle operator feedback on next-check execution Alertmanager relevance.

    Accepts artifactPath, alertmanagerRelevance (relevant|not_relevant|noisy|unsure),
    and optional alertmanagerRelevanceSummary, then creates a separate review artifact
    to preserve the immutable execution artifact.

    Note: provenance is read from the execution artifact itself, not accepted from
    the client, to preserve provenance integrity.

    Args:
        handler: The HealthUIRequestHandler instance
    """
    from ..external_analysis.artifact import AlertmanagerRelevanceClass, ExternalAnalysisPurpose

    content_length = int(handler.headers.get("Content-Length") or 0)
    if content_length <= 0:
        handler._send_json({"error": "Request body required"}, 400)
        return
    try:
        raw_payload = handler.rfile.read(content_length).decode("utf-8")
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError):
        handler._send_json({"error": "Invalid JSON payload"}, 400)
        return

    # Ensure payload is a dict (defensive against non-object JSON)
    if not isinstance(payload, dict):
        handler._send_json({"error": "Invalid JSON payload"}, 400)
        return

    # Validate required fields
    artifact_path_rel = payload.get("artifactPath")
    if not isinstance(artifact_path_rel, str) or not artifact_path_rel:
        handler._send_json({"error": "artifactPath is required"}, 400)
        return

    relevance_raw = payload.get("alertmanagerRelevance")
    if not isinstance(relevance_raw, str) or not relevance_raw:
        handler._send_json({"error": "alertmanagerRelevance is required"}, 400)
        return

    # Validate relevance class - only allow the 4 contract values
    try:
        relevance = AlertmanagerRelevanceClass(relevance_raw)
    except ValueError:
        handler._send_json(
            {
                "error": "Invalid alertmanagerRelevance. Must be one of: relevant, not_relevant, noisy, unsure"
            },
            400,
        )
        return

    # Optional summary
    relevance_summary = payload.get("alertmanagerRelevanceSummary")
    if relevance_summary is not None and not isinstance(relevance_summary, str):
        handler._send_json({"error": "alertmanagerRelevanceSummary must be a string"}, 400)
        return

    # Resolve artifact path securely
    try:
        artifact_path = (handler.runs_dir / artifact_path_rel).resolve()
    except (OSError, ValueError):
        handler._send_json({"error": "Invalid artifact path"}, 400)
        return

    # Verify path is within runs_dir
    if not str(artifact_path).startswith(str(handler.runs_dir.resolve())):
        handler._send_json({"error": "Artifact path must be within runs directory"}, 400)
        return

    if not artifact_path.exists():
        handler._send_json({"error": "Execution artifact not found"}, 404)
        return

    # Read the execution artifact to extract provenance and metadata
    try:
        execution_artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.error(
            "Unable to read execution artifact for alertmanager relevance feedback",
            extra={
                "artifact_rel": artifact_path_rel,
                "run_id": artifact_path_rel,
                "error": str(exc),
            },
            exc_info=True,
        )
        handler._send_json({"error": "Unable to read execution artifact"}, 500)
        return

    # Extract provenance from execution artifact (server-owned, not client-supplied)
    # This preserves provenance integrity - operator cannot alter evidence
    provenance = execution_artifact.get("alertmanager_provenance")

    # Extract execution metadata for the review artifact
    run_id = execution_artifact.get("run_id", "")
    cluster_label = execution_artifact.get("cluster_label", "")
    tool_name = execution_artifact.get("tool_name", "")
    status = execution_artifact.get("status", "")
    timestamp = execution_artifact.get("timestamp", datetime.now(UTC).isoformat())

    # Generate unique review artifact filename
    # Pattern: {run_id}-next-check-execution-alertmanager-review-{uuid}.json
    review_uuid = str(uuid.uuid4())[:8]
    review_filename = f"{run_id}-next-check-execution-alertmanager-review-{review_uuid}.json"

    # Write review artifact to external-analysis directory
    external_analysis_dir = handler._health_root / "external-analysis"
    external_analysis_dir.mkdir(parents=True, exist_ok=True)
    review_path = external_analysis_dir / review_filename

    review_artifact = {
        "purpose": ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW.value,
        "tool_name": tool_name,
        "run_id": run_id,
        "run_label": execution_artifact.get("run_label", ""),
        "cluster_label": cluster_label,
        "status": status,
        "timestamp": timestamp,
        "reviewed_at": datetime.now(UTC).isoformat(),
        # Link back to original execution artifact
        "source_artifact": str(artifact_path.relative_to(handler._health_root.resolve())),
        # Alertmanager relevance judgment
        "alertmanager_relevance": relevance.value,
        "alertmanager_relevance_summary": relevance_summary,
        # Preserve provenance from execution artifact (server-owned)
        "alertmanager_provenance": provenance,
        # Include execution summary for context
        "summary": execution_artifact.get("summary"),
        "duration_ms": execution_artifact.get("duration_ms"),
    }

    try:
        review_path.write_text(json.dumps(review_artifact, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.error(
            "Unable to persist alertmanager relevance review artifact",
            extra={
                "review_filename": review_filename,
                "source_artifact_rel": artifact_path_rel,
                "alertmanager_relevance": relevance.value,
                "error": str(exc),
            },
            exc_info=True,
        )
        handler._send_json({"error": "Unable to persist review artifact"}, 500)
        return

    logger.info(
        "Operator recorded Alertmanager relevance feedback",
        extra={
            "review_filename": review_filename,
            "source_artifact_rel": artifact_path_rel,
            "alertmanager_relevance": relevance.value,
            # NOTE: alertmanager_relevance_summary intentionally excluded from logs
        },
    )

    # Invalidate UI caches so the new review shows up immediately
    ui_index_path = handler.runs_dir / "health" / "ui-index.json"
    if ui_index_path.exists():
        try:
            ui_index_path.touch()
        except OSError:
            pass  # Non-fatal

    handler._send_json({
        "status": "success",
        "summary": "Alertmanager relevance feedback recorded",
        "alertmanagerRelevance": relevance.value,
        "alertmanagerRelevanceSummary": relevance_summary,
        "reviewArtifactPath": str(review_path.relative_to(handler._health_root.resolve())),
    })
