"""Next-check mutation handlers for the UI server.

This module contains the POST/mutation handlers for next-check workflows:
- next-check execution
- deterministic promotion
- next-check approval

Functions here accept the request handler instance as the first argument.

Architecture: This module imports from server.py for shared helpers (which are
safe to import at module level as they don't depend on handler instance state).
server.py imports this module, so we must avoid circular imports at module load.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Import execute_manual_next_check at module level so it can be mocked by tests
# This import is re-exported from server.py for backward compatibility
from ..external_analysis.manual_next_check import execute_manual_next_check  # noqa: F401

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

logger = logging.getLogger(__name__)


def handle_next_check_execution(handler: HealthUIRequestHandler) -> None:
    """Handle next-check execution request (POST /api/next-check-execution).

    Args:
        handler: The HealthUIRequestHandler instance
    """
    from ..external_analysis.artifact import PackRefreshStatus
    from ..external_analysis.manual_next_check import ManualNextCheckError
    from ..health.ui_next_check_execution import _derive_outcome_status
    from ..structured_logging import emit_structured_log
    from .server import _compute_health_root, _relative_path

    context = handler._load_context()
    if context is None:
        return
    plan = context.run.next_check_plan
    if not plan or not plan.artifact_path:
        handler._send_json({"error": "Next-check plan unavailable"}, 400)
        return
    content_length = int(handler.headers.get("Content-Length") or 0)
    if content_length <= 0:
        handler._send_json({"error": "Request body required"}, 400)
        return
    try:
        raw_payload = handler.rfile.read(content_length).decode("utf-8")
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        handler._send_json({"error": "Invalid JSON payload"}, 400)
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

    plan_artifact_path_from_request = payload.get("planArtifactPath")
    cluster_label = payload.get("clusterLabel")

    health_root = _compute_health_root(handler.runs_dir)
    runs_root = handler.runs_dir.resolve()
    health_root_resolved = health_root.resolve()

    candidate_entry: dict[str, object] | None = None
    resolved_index: int | None = None
    plan_path_used: Path | None = None

    def _log_resolution_attempt(
        stage: str,
        candidate_id_val: str | None,
        candidate_index_val: int | None,
        path_attempted: Path | None,
        found: bool,
    ) -> None:
        logger.debug(
            f"Next-check resolution {stage}",
            extra={
                "run_id": context.run.run_id,
                "candidate_id": candidate_id_val,
                "candidate_index": candidate_index_val,
                "cluster_label": cluster_label,
                "request_plan_artifact_path": plan_artifact_path_from_request,
                "path_attempted": str(path_attempted) if path_attempted else None,
                "path_exists": path_attempted.exists() if path_attempted else None,
                "found": found,
                "stage": stage,
            },
        )

    index_plan_artifact_path = plan.artifact_path if plan else None
    index_plan_artifact_exists = False
    resolved_index_plan_artifact_path: Path | None = None
    if index_plan_artifact_path:
        resolved_index_plan_artifact_path = (health_root / index_plan_artifact_path).resolve()
        index_plan_artifact_exists = resolved_index_plan_artifact_path.exists()

    request_plan_artifact_path_raw = plan_artifact_path_from_request
    resolved_request_plan_artifact_path: Path | None = None
    request_plan_artifact_exists = False
    request_plan_artifact_within_health_root = False

    if request_plan_artifact_path_raw and isinstance(request_plan_artifact_path_raw, str):
        resolved_request_plan_artifact_path = (health_root / request_plan_artifact_path_raw).resolve()
        request_plan_artifact_within_health_root = str(resolved_request_plan_artifact_path).startswith(str(health_root_resolved))
        request_plan_artifact_exists = resolved_request_plan_artifact_path.exists()

        emit_structured_log(
            component="next-check-execution",
            message="Next-check plan artifact resolution starting",
            run_label=context.run.run_label,
            run_id=context.run.run_id,
            severity="INFO",
            metadata={
                "runs_root": str(runs_root),
                "health_root": str(health_root_resolved),
                "request_plan_artifact_path_raw": request_plan_artifact_path_raw,
                "resolved_request_plan_artifact_path": str(resolved_request_plan_artifact_path) if resolved_request_plan_artifact_path else None,
                "index_plan_artifact_path": index_plan_artifact_path,
                "resolved_index_plan_artifact_path": str(resolved_index_plan_artifact_path) if resolved_index_plan_artifact_path else None,
            },
        )

        if request_plan_artifact_within_health_root and request_plan_artifact_exists:
            plan_path = resolved_request_plan_artifact_path
            _log_resolution_attempt("explicit_path_valid", candidate_id, candidate_index, plan_path, True)
        else:
            emit_structured_log(
                component="next-check-execution",
                message="Next-check plan artifact path invalid, falling back to index",
                run_label=context.run.run_label,
                run_id=context.run.run_id,
                severity="WARNING",
                metadata={
                    "requested_path": request_plan_artifact_path_raw,
                    "resolved_request_path": str(resolved_request_plan_artifact_path) if resolved_request_plan_artifact_path else None,
                    "request_path_valid": request_plan_artifact_exists,
                    "request_path_within_health_root": request_plan_artifact_within_health_root,
                    "fallback_index_path": plan.artifact_path,
                    "resolved_fallback_path": str(resolved_index_plan_artifact_path) if resolved_index_plan_artifact_path else None,
                },
            )
            plan_path = resolved_index_plan_artifact_path
            _log_resolution_attempt("explicit_path_invalid_fallback", candidate_id, candidate_index, plan_path, False)
    else:
        plan_path = resolved_index_plan_artifact_path

    candidate_found_in_request_artifact = False
    candidate_found_in_index_artifact = False
    fallback_search_attempted = False
    fallback_matched_artifact_path: str | None = None

    if plan_path and str(plan_path).startswith(str(health_root_resolved)) and plan_path.exists():
        index_plan_artifact_exists = True
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
                plan_path_used = plan_path
                if request_plan_artifact_path_raw and request_plan_artifact_exists:
                    candidate_found_in_request_artifact = True
                else:
                    candidate_found_in_index_artifact = True
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    if candidate_entry is None or resolved_index is None:
        fallback_search_attempted = True
        fallback_entry, fallback_index, fallback_path = find_candidate_in_all_plan_artifacts(
            health_root,
            context.run.run_id,
            candidate_id,
            candidate_index,
        )
        if fallback_entry is not None and fallback_index is not None:
            candidate_entry = fallback_entry
            resolved_index = fallback_index
            plan_path_used = fallback_path
            if fallback_path:
                fallback_matched_artifact_path = str(fallback_path)

    if candidate_entry is None or resolved_index is None:
        emit_structured_log(
            component="next-check-execution",
            message="Next-check candidate resolution failed",
            run_label=context.run.run_label,
            run_id=context.run.run_id,
            severity="ERROR",
            metadata={
                "candidate_id": candidate_id,
                "candidate_index_requested": candidate_index,
                "candidate_index_resolved": None,
                "cluster_label": cluster_label,
                "request_plan_artifact_path_raw": request_plan_artifact_path_raw,
                "resolved_request_plan_artifact_path": str(resolved_request_plan_artifact_path) if resolved_request_plan_artifact_path else None,
                "request_plan_artifact_exists": request_plan_artifact_exists,
                "request_plan_artifact_within_health_root": request_plan_artifact_within_health_root,
                "index_plan_artifact_path": index_plan_artifact_path,
                "resolved_index_plan_artifact_path": str(resolved_index_plan_artifact_path) if resolved_index_plan_artifact_path else None,
                "index_plan_artifact_exists": index_plan_artifact_exists,
                "runs_root": str(runs_root),
                "health_root": str(health_root_resolved),
                "candidate_found_in_request_artifact": candidate_found_in_request_artifact,
                "candidate_found_in_index_artifact": candidate_found_in_index_artifact,
                "fallback_search_attempted": fallback_search_attempted,
                "fallback_matched_artifact_path": fallback_matched_artifact_path,
                "final_resolution_source": (
                    "explicit_request_path" if candidate_found_in_request_artifact
                    else "index_path" if candidate_found_in_index_artifact
                    else "fallback_search" if fallback_matched_artifact_path
                    else "none"
                ),
                "error_summary": "Candidate not found after checking all resolution paths",
            },
        )
        logger.warning(
            "Next-check candidate not found during execution",
            extra={
                "run_id": context.run.run_id,
                "candidate_id": candidate_id,
                "candidate_index": candidate_index,
                "plan_path_used": str(plan_path) if plan_path else None,
                "plan_artifact_path_from_request": plan_artifact_path_from_request,
                "fallback_search_attempted": True,
            },
        )
        if candidate_id and candidate_index is not None:
            handler._send_json({"error": "Candidate not found. The queue may have changed since the page was loaded. Please refresh the page."}, 400)
        elif candidate_id:
            handler._send_json({"error": "Candidate not found by ID. The queue may have changed since the page was loaded. Please refresh the page."}, 400)
        else:
            handler._send_json({"error": "Candidate not found at specified index. The queue may have changed since the page was loaded. Please refresh the page."}, 400)
        return

    candidate = candidate_entry
    candidate_index = resolved_index

    if plan_path_used is not None and not plan_path_used.is_absolute():
        plan_path_used = handler.runs_dir / plan_path_used
    effective_plan_path = plan_path_used if plan_path_used else plan_path
    if not effective_plan_path or not str(effective_plan_path).startswith(str(handler.runs_dir.resolve())):
        handler._send_json({"error": "Plan artifact path invalid"}, 400)
        return

    candidate_view = None
    plan_view = context.run.next_check_plan
    if plan_view:
        for entry in plan_view.candidates:
            if entry.candidate_index == candidate_index:
                candidate_view = entry
                break
    if candidate_view:
        enriched_candidate = dict(candidate)
        if candidate_view.approval_status:
            enriched_candidate["approvalStatus"] = candidate_view.approval_status
        if candidate_view.approval_artifact_path:
            enriched_candidate["approvalArtifactPath"] = candidate_view.approval_artifact_path
        if candidate_view.approval_timestamp:
            enriched_candidate["approvalTimestamp"] = candidate_view.approval_timestamp
        candidate = enriched_candidate
    if not isinstance(candidate, Mapping):
        handler._send_json({"error": "Invalid candidate record"}, 500)
        return
    target_cluster = candidate.get("targetCluster")
    if not isinstance(target_cluster, str) or not target_cluster:
        handler._send_json({"error": "Candidate target cluster missing"}, 400)
        return
    if target_cluster != request_cluster:
        handler._send_json({"error": "Candidate target cluster mismatch"}, 400)
        return
    cluster_context = None
    for cluster in context.clusters:
        if cluster.label == target_cluster:
            cluster_context = cluster.context
            break
    if not cluster_context:
        handler._send_json({"error": "Cluster context unavailable"}, 400)
        return
    try:
        artifact = execute_manual_next_check(
            health_root=handler._health_root,
            run_id=context.run.run_id,
            run_label=context.run.run_label,
            plan_artifact_path=effective_plan_path,
            candidate_index=candidate_index,
            candidate=candidate,
            target_context=cluster_context,
            target_cluster=target_cluster,
        )
    except ManualNextCheckError as exc:
        error_payload: dict[str, object] = {"error": str(exc)}
        blocking_reason = getattr(exc, "blocking_reason", None)
        if blocking_reason is not None:
            error_payload["blockingReason"] = blocking_reason.value
        handler._send_json(error_payload, 400)
        return
    except Exception as exc:
        handler._send_json({"error": f"Execution failed: {exc}"}, 500)
        return
    artifact_path = _relative_path(handler.runs_dir, artifact.artifact_path)

    execution_state = determine_execution_state_from_artifact(artifact)
    approval_status = str(candidate.get("approvalStatus") or candidate.get("approvalState") or "not-required")
    outcome_status = _derive_outcome_status(approval_status, execution_state)

    response_payload = {
        "status": artifact.status.value,
        "summary": artifact.summary,
        "artifactPath": artifact_path,
        "durationMs": artifact.duration_ms,
        "command": artifact.payload.get("command") if isinstance(artifact.payload, Mapping) else None,
        "targetCluster": target_cluster,
        "planCandidateIndex": candidate_index,
        "rawOutput": artifact.raw_output,
        "errorSummary": artifact.error_summary,
        "timedOut": artifact.timed_out,
        "stdoutTruncated": artifact.stdout_truncated,
        "stderrTruncated": artifact.stderr_truncated,
        "outputBytesCaptured": artifact.output_bytes_captured,
        "executionState": execution_state,
        "outcomeStatus": outcome_status,
        "latestArtifactPath": artifact_path,
        "latestTimestamp": artifact.timestamp.isoformat() if artifact.timestamp else None,
    }

    # Import pack refresh helper from server.py
    from .server import _refresh_diagnostic_pack_latest

    refresh_status: PackRefreshStatus = PackRefreshStatus.SUCCEEDED
    refresh_warning: str | None = None
    refresh_ok = _refresh_diagnostic_pack_latest(context.run.run_id, handler.runs_dir)
    if not refresh_ok:
        refresh_status = PackRefreshStatus.FAILED
        refresh_warning = "Execution artifact saved. Pack refresh failed; queue/review state may be stale until next refresh."
        response_payload["warning"] = refresh_warning

    if artifact.artifact_path:
        artifact_path_obj = Path(artifact.artifact_path)
        if artifact_path_obj.exists():
            try:
                artifact_data = json.loads(artifact_path_obj.read_text(encoding="utf-8"))
                artifact_data["pack_refresh_status"] = refresh_status.value
                artifact_data["pack_refresh_warning"] = refresh_warning
                artifact_path_obj.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")
                response_payload["packRefreshStatus"] = refresh_status.value
                response_payload["packRefreshWarning"] = refresh_warning
            except (OSError, json.JSONDecodeError, TypeError) as exc:
                logger.warning(
                    "Failed to persist pack refresh status to artifact",
                    extra={
                        "artifact": artifact_path_obj.name,
                        "run_id": context.run.run_id,
                        "error": str(exc),
                    },
                )

    emit_structured_log(
        component="next-check-execution",
        message="Next-check candidate resolved and executed",
        run_label=context.run.run_label,
        run_id=context.run.run_id,
        severity="INFO",
        metadata={
            "candidate_id": candidate_id,
            "candidate_index_requested": candidate_index,
            "candidate_index_resolved": resolved_index,
            "cluster_label": cluster_label,
            "explicit_request_path_provided": request_plan_artifact_path_raw is not None,
            "explicit_request_path_raw": request_plan_artifact_path_raw,
            "resolved_request_plan_artifact_path": str(resolved_request_plan_artifact_path) if resolved_request_plan_artifact_path else None,
            "explicit_request_path_exists": request_plan_artifact_exists,
            "explicit_request_path_validated": request_plan_artifact_within_health_root and request_plan_artifact_exists if request_plan_artifact_path_raw else None,
            "index_plan_artifact_path": index_plan_artifact_path,
            "resolved_index_plan_artifact_path": str(resolved_index_plan_artifact_path) if resolved_index_plan_artifact_path else None,
            "index_plan_artifact_exists": index_plan_artifact_exists,
            "runs_root": str(runs_root),
            "health_root": str(health_root_resolved),
            "candidate_found_in_request_artifact": candidate_found_in_request_artifact,
            "candidate_found_in_index_artifact": candidate_found_in_index_artifact,
            "fallback_search_attempted": fallback_search_attempted,
            "fallback_matched_artifact_path": fallback_matched_artifact_path,
            "final_source": (
                "explicit_request_path" if candidate_found_in_request_artifact
                else "index_path" if candidate_found_in_index_artifact
                else "fallback_search" if fallback_matched_artifact_path
                else "unknown"
            ),
            "execution_status": artifact.status.value,
            "execution_duration_ms": artifact.duration_ms,
            "execution_timed_out": artifact.timed_out,
            "refresh_status": refresh_status.value,
        },
    )

    ui_index_path = handler.runs_dir / "health" / "ui-index.json"
    try:
        index_data = json.loads(ui_index_path.read_text(encoding="utf-8"))
        run_entry = index_data.get("run") or {}
        history_list: list[dict[str, object]] = list(run_entry.get("next_check_execution_history") or [])
        history_entry: dict[str, object] = {
            "timestamp": artifact.timestamp.isoformat() if hasattr(artifact, "timestamp") and artifact.timestamp else datetime.now(UTC).isoformat(),
            "clusterLabel": target_cluster if target_cluster else cluster_label,
            "candidateDescription": candidate.get("description") if candidate else None,
            "commandFamily": candidate.get("suggestedCommandFamily") if candidate else None,
            "status": artifact.status.value,
            "durationMs": artifact.duration_ms,
            "artifactPath": str(artifact_path) if artifact_path else None,
            "timedOut": artifact.timed_out or False,
            "stdoutTruncated": artifact.stdout_truncated or False,
            "stderrTruncated": artifact.stderr_truncated or False,
        }
        history_list.append(history_entry)
        run_entry["next_check_execution_history"] = history_list
        index_data["run"] = run_entry
        ui_index_path.write_text(json.dumps(index_data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.debug(
            "Persisted execution history to ui-index.json",
            extra={"ui_index": str(ui_index_path), "run_id": context.run.run_id, "history_count": len(history_list)},
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        # Fallback: attempt touch-only invalidation to signal UI refresh needed
        logger.warning(
            "Failed to persist execution history to ui-index.json, falling back to touch-only invalidation",
            extra={
                "ui_index": ui_index_path.name,
                "run_id": context.run.run_id,
                "candidate_index": candidate_index,
                "error": str(exc),
            },
            exc_info=True,
        )
        try:
            ui_index_path.touch()
        except OSError as touch_exc:
            logger.warning(
                "Failed to touch ui-index.json for invalidation",
                extra={
                    "ui_index": ui_index_path.name,
                    "run_id": context.run.run_id,
                    "error": str(touch_exc),
                },
                exc_info=True,
            )

    handler._send_json(response_payload)


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

    context = handler._load_context()
    if context is None:
        return
    content_length = int(handler.headers.get("Content-Length") or 0)
    if content_length <= 0:
        handler._send_json({"error": "Request body required"}, 400)
        return
    try:
        raw_payload = handler.rfile.read(content_length).decode("utf-8")
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        handler._send_json({"error": "Invalid JSON payload"}, 400)
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
    target_context = payload.get("context") if isinstance(payload.get("context"), str) else None
    if not target_context and matching_cluster:
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


def handle_next_check_approval(handler: HealthUIRequestHandler) -> None:
    """Handle next-check approval request (POST /api/next-check-approval).

    Args:
        handler: The HealthUIRequestHandler instance
    """
    from ..external_analysis.next_check_approval import log_next_check_approval_event, record_next_check_approval
    from .server import _relative_path

    context = handler._load_context()
    if context is None:
        return
    plan = context.run.next_check_plan
    if not plan or not plan.artifact_path:
        handler._send_json({"error": "Next-check plan unavailable"}, 400)
        return
    content_length = int(handler.headers.get("Content-Length") or 0)
    if content_length <= 0:
        handler._send_json({"error": "Request body required"}, 400)
        return
    try:
        raw_payload = handler.rfile.read(content_length).decode("utf-8")
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        handler._send_json({"error": "Invalid JSON payload"}, 400)
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
    artifact_path = _relative_path(handler.runs_dir, artifact.artifact_path)
    response = {
        "status": artifact.status.value,
        "summary": artifact.summary,
        "artifactPath": artifact_path,
        "durationMs": artifact.duration_ms,
        "candidateIndex": candidate_index,
        "approvalTimestamp": artifact.timestamp.isoformat(),
    }
    handler._send_json(response)


def resolve_plan_candidate(
    candidates: Sequence[object],
    requested_candidate_id: str | None,
    requested_candidate_index: int | None,
) -> tuple[Mapping[str, object] | None, int | None]:
    """Resolve a plan candidate by ID or index.

    Args:
        candidates: Sequence of candidate dicts
        requested_candidate_id: Optional candidate ID to find
        requested_candidate_index: Optional candidate index to find

    Returns:
        Tuple of (candidate_entry, resolved_index) if found, else (None, None)
    """
    if not isinstance(candidates, Sequence):
        return None, None
    entries = list(candidates)
    found_entry: Mapping[str, object] | None = None
    found_position: int | None = None
    if requested_candidate_id:
        for idx, entry in enumerate(entries):
            if not isinstance(entry, Mapping):
                continue
            entry_id = entry.get("candidateId")
            if isinstance(entry_id, str) and entry_id == requested_candidate_id:
                found_entry = dict(entry)
                found_position = idx
                break
    if found_entry is None and requested_candidate_index is not None:
        if 0 <= requested_candidate_index < len(entries):
            entry = entries[requested_candidate_index]
            if isinstance(entry, Mapping):
                found_entry = dict(entry)
                found_position = requested_candidate_index
    if found_entry is None:
        return None, None
    candidate_index_value: int | None = None
    explicit_index = found_entry.get("candidateIndex")
    if isinstance(explicit_index, int):
        candidate_index_value = explicit_index
    elif found_position is not None:
        candidate_index_value = found_position
    elif requested_candidate_index is not None:
        candidate_index_value = requested_candidate_index
    return found_entry, candidate_index_value


def find_candidate_in_all_plan_artifacts(
    health_root: Path,
    run_id: str,
    candidate_id: str | None,
    candidate_index: int | None,
) -> tuple[dict[str, object] | None, int | None, Path | None]:
    """Search for a candidate across all planner artifacts for the given run.

    This handles cases where the plan artifact path in the queue may differ from
    the current next_check_plan.artifact_path (e.g., due to plan regeneration).

    Args:
        health_root: Path to the health root directory (runs/health/)
        run_id: The run ID
        candidate_id: Optional candidate ID to find
        candidate_index: Optional candidate index to find

    Returns:
        Tuple of (candidate_entry, resolved_index, plan_path) if found.
    """
    from ..external_analysis.deterministic_next_check_promotion import collect_promoted_queue_entries
    from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id

    # SECURITY: Validate run_id before using in glob pattern to prevent path traversal
    try:
        validated_run_id = validate_run_id(run_id)
    except SecurityError:
        # Invalid run_id - cannot safely search, return empty result
        return None, None, None

    glob_pattern = safe_run_artifact_glob(validated_run_id, "-next-check-plan*.json")
    promotions = collect_promoted_queue_entries(health_root, validated_run_id)
    if promotions:
        entry, idx = resolve_plan_candidate(
            promotions,
            candidate_id,
            candidate_index,
        )
        if entry is not None and idx is not None:
            return dict(entry), idx, None

    external_analysis_dir = health_root / "external-analysis"
    if external_analysis_dir.exists():
        for artifact_file in external_analysis_dir.glob(glob_pattern):
            try:
                artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
                purpose = artifact_data.get("purpose")
                if purpose != "next-check-planning":
                    continue

                payload = artifact_data.get("payload", {})
                candidates = payload.get("candidates", [])
                entry, idx = resolve_plan_candidate(
                    candidates if isinstance(candidates, Sequence) else (),
                    candidate_id,
                    candidate_index,
                )
                if entry is not None and idx is not None:
                    return dict(entry), idx, Path("external-analysis") / artifact_file.name
            except (OSError, json.JSONDecodeError, ValueError):
                continue

    return None, None, None


def determine_execution_state_from_artifact(artifact: Any) -> str:
    """Determine execution state from an execution artifact.

    Args:
        artifact: The execution artifact from manual next-check execution.

    Returns:
        Execution state string: "executed-success", "executed-failed", or "timed-out".
    """
    from ..external_analysis.artifact import ExternalAnalysisStatus

    if artifact.timed_out:
        return "timed-out"
    if artifact.status == ExternalAnalysisStatus.SUCCESS:
        return "executed-success"
    return "executed-failed"
