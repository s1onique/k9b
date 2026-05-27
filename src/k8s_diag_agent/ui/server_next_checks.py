"""Next-check mutation handlers for the UI server.

This module contains the POST/mutation handlers for next-check workflows:
- next-check execution (extracted to server_next_check_execution.py)
- deterministic promotion
- next-check approval (extracted to server_next_check_approval.py)

Functions here accept the request handler instance as the first argument.

Architecture: This module is a compatibility surface. Handlers are extracted to
focused sibling modules:
- server_next_check_execution.py: next-check execution
- server_next_check_approval.py: next-check approval
server.py imports this module for route registration and backward compatibility.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

# Import execute_manual_next_check at module level so it can be mocked by tests
# This import is re-exported from server.py for backward compatibility
from ..external_analysis.manual_next_check import execute_manual_next_check  # noqa: F401

# Import extracted handlers
from .server_next_check_approval import handle_next_check_approval  # noqa: F401
from .server_next_check_execution import handle_next_check_execution  # noqa: F401
from .server_next_check_utils import find_candidate_in_all_plan_artifacts  # noqa: F401

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

logger = logging.getLogger(__name__)


def handle_deterministic_promotion(handler: HealthUIRequestHandler) -> None:
    """Handle deterministic next-check promotion request (POST /api/deterministic-next-check/promote).

    Args:
        handler: The HealthUIRequestHandler instance
    """
    from ..external_analysis.deterministic_next_check_promotion import (
        build_promoted_candidate_id,
        collect_promoted_queue_entries,
        write_deterministic_next_check_promotion,
    )
    from .server_shared import _validate_json_mutation_request

    # Validate Content-Type and request size, parse JSON body
    payload = _validate_json_mutation_request(handler)
    if payload is None:
        return

    context = handler._load_context()
    if context is None:
        return
    cluster_label = payload.get("clusterLabel")
    if not isinstance(cluster_label, str) or not cluster_label:
        handler._send_json({"error": "clusterLabel is required"}, 400)
        return
    description = payload.get("description")
    if not isinstance(description, str) or not description.strip():
        handler._send_json({"error": "description is required"}, 400)
        return
    matching_cluster = next(
        (cluster for cluster in context.clusters if cluster.label == cluster_label),
        None,
    )
    if matching_cluster is None:
        handler._send_json({"error": "Cluster label is not part of this run."}, 400)
        return
    workstream = payload.get("workstream") if isinstance(payload.get("workstream"), str) else None
    urgency = payload.get("urgency") if isinstance(payload.get("urgency"), str) else None
    why_now = payload.get("whyNow") if isinstance(payload.get("whyNow"), str) else None
    top_problem = payload.get("topProblem") if isinstance(payload.get("topProblem"), str) else None
    method = payload.get("method") if isinstance(payload.get("method"), str) else None
    raw_evidence = payload.get("evidenceNeeded")
    evidence = [str(item) for item in raw_evidence or [] if isinstance(item, str)]
    priority_score = payload.get("priorityScore")
    priority_value: int | None = None
    if isinstance(priority_score, (int, float)):
        priority_value = int(priority_score)
    elif isinstance(priority_score, str):
        try:
            priority_value = int(priority_score)
        except ValueError:
            priority_value = None
    target_context: str | None = None
    payload_context = payload.get("context")
    if isinstance(payload_context, str):
        target_context = payload_context
    if not target_context and matching_cluster and isinstance(matching_cluster.context, str):
        target_context = matching_cluster.context
    summary = {
        "description": description.strip(),
        "method": method,
        "evidenceNeeded": evidence,
        "workstream": workstream,
        "urgency": urgency,
        "whyNow": why_now,
        "topProblem": top_problem,
        "priorityScore": priority_value,
    }
    promotions = collect_promoted_queue_entries(handler._health_root, context.run.run_id)
    candidate_id = build_promoted_candidate_id(
        description, cluster_label, context.run.run_id
    )
    existing_ids = {entry.get("candidateId") for entry in promotions if entry.get("candidateId")}
    if candidate_id in existing_ids:
        handler._send_json(
            {"error": "A similar deterministic check has already been promoted."},
            409,
        )
        return
    try:
        artifact, _ = write_deterministic_next_check_promotion(
            runs_dir=handler.runs_dir,
            run_id=context.run.run_id,
            run_label=context.run.run_label,
            cluster_label=cluster_label,
            target_context=target_context,
            summary=summary,
        )
    except (FileExistsError, OSError) as exc:
        logger.error(
            "Failed to persist deterministic promotion artifact",
            extra={
                "run_id": context.run.run_id,
                "candidate_id": candidate_id,
                "cluster_label": cluster_label,
                "error": str(exc),
            },
            exc_info=True,
        )
        handler._send_json({"error": f"Unable to persist promotion: {exc}"}, 500)
        return
    response = {
        "status": "success",
        "summary": "Deterministic next check promoted to the queue.",
        "artifactPath": artifact.artifact_path,
        "candidateId": candidate_id,
    }
    handler._send_json(response)
