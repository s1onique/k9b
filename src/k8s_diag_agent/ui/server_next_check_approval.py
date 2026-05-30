"""Next-check approval handler for the UI server.

This module contains the approval mutation handler for next-check workflows.

Architecture: This module imports from server_next_checks for shared utilities.
server_next_checks imports this module for backward compatibility.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server_next_checks import HealthUIRequestHandler

logger = logging.getLogger(__name__)


def handle_next_check_approval(handler: HealthUIRequestHandler) -> None:
    """Handle next-check approval request (POST /api/next-check-approval).

    Args:
        handler: The HealthUIRequestHandler instance
    """
    from ..external_analysis.next_check_approval import log_next_check_approval_event, record_next_check_approval
    from .server_next_check_utils import (
        find_candidate_in_all_plan_artifacts,
        relative_path,
        resolve_plan_candidate,
    )
    from .server_shared import _validate_json_mutation_request

    context = handler._load_context()
    if context is None:
        return
    plan = context.run.next_check_plan
    if not plan or not plan.artifact_path:
        handler._send_json({"error": "Next-check plan unavailable"}, 400)
        return

    # Validate Content-Type and request size, parse JSON body
    payload = _validate_json_mutation_request(handler)
    if payload is None:
        return

    candidate_index_raw = payload.get("candidateIndex")
    candidate_index = candidate_index_raw if isinstance(candidate_index_raw, int) else None
    if candidate_index_raw is not None and candidate_index is None:
        handler._send_json({"error": "candidateIndex must be an integer"}, 400)
        return
    request_cluster = payload.get("clusterLabel")
    if not isinstance(request_cluster, str) or not request_cluster:
        handler._send_json({"error": "clusterLabel is required"}, 400)
        return
    candidate_id_raw = payload.get("candidateId")
    candidate_id = candidate_id_raw if isinstance(candidate_id_raw, str) and candidate_id_raw else None
    if candidate_id is None and candidate_index is None:
        handler._send_json({"error": "candidateId or candidateIndex is required"}, 400)
        return

    candidate_entry: dict[str, object] | None = None
    resolved_index: int | None = None

    plan_path = (handler._health_root / plan.artifact_path).resolve()
    if str(plan_path).startswith(str(handler.runs_dir.resolve())) and plan_path.exists():
        try:
            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
            candidates = plan_data.get("candidates")
            raw_entry, resolved_index = resolve_plan_candidate(
                candidates if isinstance(candidates, Sequence) else (),
                candidate_id,
                candidate_index,
            )
            if raw_entry is not None and resolved_index is not None:
                candidate_entry = dict(raw_entry)
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    if candidate_entry is None or resolved_index is None:
        fallback_entry, fallback_index, _ = find_candidate_in_all_plan_artifacts(
            handler._health_root,
            context.run.run_id,
            candidate_id,
            candidate_index,
        )
        if fallback_entry is not None and fallback_index is not None:
            candidate_entry = fallback_entry
            resolved_index = fallback_index

    if candidate_entry is None or resolved_index is None:
        if candidate_id and candidate_index is not None:
            handler._send_json({"error": "Candidate not found. The queue may have changed since the page was loaded. Please refresh the page."}, 400)
        elif candidate_id:
            handler._send_json({"error": "Candidate not found by ID. The queue may have changed since the page was loaded. Please refresh the page."}, 400)
        else:
            handler._send_json({"error": "Candidate not found at specified index. The queue may have changed since the page was loaded. Please refresh the page."}, 400)
        return
    candidate = candidate_entry
    raw_candidate_id_value = candidate.get("candidateId")
    candidate_id_value = (
        raw_candidate_id_value if isinstance(raw_candidate_id_value, str) else None
    )
    candidate_index = resolved_index
    target_cluster = candidate.get("targetCluster")
    if target_cluster and target_cluster != request_cluster:
        handler._send_json({"error": "Candidate target cluster mismatch"}, 400)
        return
    requires_approval = bool(candidate.get("requiresOperatorApproval"))
    if not requires_approval:
        log_next_check_approval_event(
            severity="WARNING",
            message="Approval rejected because candidate does not require approval",
            run_label=context.run.run_label,
            run_id=context.run.run_id,
            plan_artifact_path=plan.artifact_path,
            candidate_index=candidate_index,
            candidate_description=str(candidate.get("description") or ""),
            target_cluster=request_cluster,
            event="approval-rejected",
        )
        handler._send_json({"error": "Candidate does not require approval"}, 400)
        return
    if candidate.get("duplicateOfExistingEvidence"):
        log_next_check_approval_event(
            severity="WARNING",
            message="Approval rejected because candidate duplicates existing evidence",
            run_label=context.run.run_label,
            run_id=context.run.run_id,
            plan_artifact_path=plan.artifact_path,
            candidate_index=candidate_index,
            candidate_description=str(candidate.get("description") or ""),
            target_cluster=request_cluster,
            event="approval-rejected",
        )
        handler._send_json({"error": "Candidate duplicates deterministic evidence"}, 400)
        return
    if target_cluster is None and request_cluster and request_cluster not in {cluster.label for cluster in context.clusters}:
        pass
    plan_candidate_description = str(candidate.get("description") or "")
    log_next_check_approval_event(
        severity="INFO",
        message="Operator requested approval for next-check candidate",
        run_label=context.run.run_label,
        run_id=context.run.run_id,
        plan_artifact_path=plan.artifact_path,
        candidate_index=candidate_index,
        candidate_id=candidate_id_value,
        candidate_description=plan_candidate_description,
        target_cluster=request_cluster,
        event="approval-requested",
    )
    try:
        artifact = record_next_check_approval(
            runs_dir=handler.runs_dir,
            run_id=context.run.run_id,
            run_label=context.run.run_label,
            plan_artifact_path=plan.artifact_path,
            candidate_index=candidate_index,
            candidate_id=candidate_id_value,
            candidate_description=plan_candidate_description,
            target_cluster=request_cluster,
        )
    except (FileExistsError, OSError) as exc:
        logger.error(
            "Failed to persist approval artifact",
            extra={
                "run_id": context.run.run_id,
                "candidate_id": candidate_id_value,
                "candidate_index": candidate_index,
                "cluster_label": request_cluster,
                "error": str(exc),
            },
            exc_info=True,
        )
        handler._send_json({"error": f"Approval failed: {exc}"}, 500)
        return
    artifact_path = relative_path(handler.runs_dir, artifact.artifact_path)
    response = {
        "status": artifact.status.value,
        "summary": artifact.summary,
        "artifactPath": artifact_path,
        "durationMs": artifact.duration_ms,
        "candidateIndex": candidate_index,
        "approvalTimestamp": artifact.timestamp.isoformat(),
    }
    handler._send_json(response)
