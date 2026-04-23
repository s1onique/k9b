"""Alertmanager source-action mutation handlers for the UI server.

This module contains the POST/mutation handlers for Alertmanager source workflows:
- source action (promote/disable)

Functions here accept the request handler instance as the first argument.

Architecture: This module imports from server.py for shared helpers (which are
safe to import at module level as they don't depend on handler instance state).
server.py imports this module, so we must avoid circular imports at module load.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

logger = logging.getLogger(__name__)


def handle_alertmanager_source_action(
    handler: HealthUIRequestHandler, run_id: str, source_key: str
) -> None:
    """Handle operator request to promote or disable an Alertmanager source.

    Route: POST /api/runs/{run_id}/alertmanager-sources/{source_id}/action
    Body: { "action": "promote"|"disable", "reason": "..." (optional) }

    The run_id in the URL path is authoritative. The cluster_label is still
    required in the request body for override persistence (since overrides
    are per-cluster).

    Promotion converts a discovered/auto-tracked source to manual, making it
    authoritative and preventing it from being silently deleted.

    Disabling removes the source from auto-tracking, preventing it from
    being re-added on future discovery cycles.

    Args:
        handler: The HealthUIRequestHandler instance
        run_id: The run ID from the URL path
        source_key: The source key (URL-decoded source_id) from the URL path
    """
    from ..external_analysis.alertmanager_source_actions import (
        SourceAction,
        SourceOverride,
        write_source_action_artifact,
    )
    from ..external_analysis.alertmanager_source_registry import (
        AlertmanagerSourceRegistry,
        RegistryDesiredState,
        RegistryEntry,
        build_canonical_registry_key,
        read_source_registry,
        write_source_registry,
    )
    from .server import _run_payload_cache, _run_payload_cache_lock

    # Load context for the specific run_id from the URL path
    context = handler._load_context(requested_run_id=run_id)
    if context is None:
        # Fall back to loading from ui-index.json if specific run not found
        context = handler._load_context()
        if context is None:
            handler._send_json({"error": "Unable to load run context"}, 500)
            return
        # If run_id from path doesn't match, log warning but proceed
        if context.run.run_id != run_id:
            logger.warning(
                "Requested run_id not found, using latest",
                extra={"requested_run_id": run_id, "using_run_id": context.run.run_id},
            )

    # Parse request body
    content_length = int(handler.headers.get("Content-Length") or 0)
    if content_length <= 0:
        handler._send_json({"error": "Request body required"}, 400)
        return
    try:
        raw_payload = handler.rfile.read(content_length).decode("utf-8")
        payload = json.loads(raw_payload)
    except Exception:
        handler._send_json({"error": "Invalid JSON payload"}, 400)
        return

    # Validate action field (required in body)
    action_raw = payload.get("action")
    if not isinstance(action_raw, str) or not action_raw:
        handler._send_json({"error": "action is required in request body"}, 400)
        return

    # Parse action enum
    if action_raw == "promote":
        action = SourceAction.PROMOTE
    elif action_raw == "disable":
        action = SourceAction.DISABLE
    else:
        handler._send_json({"error": "action must be 'promote' or 'disable'"}, 400)
        return

    # Optional reason field for audit trail
    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        handler._send_json({"error": "reason must be a string"}, 400)
        return

    # Cluster label still required in body (for override persistence)
    cluster_label = payload.get("clusterLabel")
    if not isinstance(cluster_label, str) or not cluster_label:
        handler._send_json({"error": "clusterLabel is required in request body"}, 400)
        return

    # Validate source_id from path matches body if provided
    body_source_id = payload.get("sourceId")
    if body_source_id is not None and str(body_source_id) != source_key:
        handler._send_json(
            {"error": f"sourceId mismatch: path has '{source_key}', body has '{body_source_id}'"}, 400
        )
        return

    # Find the source in the alertmanager_sources inventory
    sources_view = context.alertmanager_sources
    if sources_view is None:
        handler._send_json({"error": "Alertmanager sources not available"}, 400)
        return

    source_view = None
    for s in sources_view.sources:
        if s.source_id == source_key:
            source_view = s
            break

    if source_view is None:
        handler._send_json({"error": f"Source not found: {source_key}"}, 404)
        return

    # Validate action is allowed based on source state
    if action == SourceAction.PROMOTE:
        if not source_view.can_promote:
            if source_view.is_manual:
                handler._send_json({"error": "Source is already manual"}, 400)
            else:
                handler._send_json(
                    {"error": f"Cannot promote source in state: {source_view.state}"}, 400
                )
            return
    elif action == SourceAction.DISABLE:
        if not source_view.can_disable:
            if source_view.is_manual:
                handler._send_json({"error": "Cannot disable manual source"}, 400)
            else:
                handler._send_json(
                    {"error": f"Cannot disable source in state: {source_view.state}"}, 400
                )
            return

    # Create the source override with reason if provided
    override = SourceOverride(
        source_id=source_key,
        action=action,
        endpoint=source_view.endpoint,
        namespace=source_view.namespace,
        name=source_view.name,
        original_origin=source_view.origin,
        original_state=source_view.state,
        reason=reason,
    )

    # Load existing overrides or create new
    # Overrides are stored in health root alongside the sources inventory artifact
    # (NOT in external-analysis/ which is for next-check planning artifacts)
    overrides_path = handler._health_root / f"{context.run.run_id}-alertmanager-source-overrides.json"

    from ..external_analysis.alertmanager_source_actions import AlertmanagerSourceOverrides

    existing_overrides = AlertmanagerSourceOverrides(cluster_context=cluster_label)
    if overrides_path.exists():
        try:
            raw = json.loads(overrides_path.read_text(encoding="utf-8"))
            existing_overrides = AlertmanagerSourceOverrides.from_dict(raw)
        except (json.JSONDecodeError, KeyError, ValueError):
            pass  # Start fresh if corrupted

    # Add/update the override
    existing_overrides.add_override(override)

    # Write the overrides artifact
    try:
        # Ensure health root directory exists
        handler._health_root.mkdir(parents=True, exist_ok=True)
        overrides_path.write_text(
            json.dumps(existing_overrides.to_dict(), indent=2), encoding="utf-8"
        )
    except Exception as exc:
        handler._send_json({"error": f"Failed to persist override: {exc}"}, 500)
        return

    # Also write to the durable cross-run registry for cross-run persistence
    # This ensures promote/disable actions survive beyond the current run
    existing_entry: RegistryEntry | None = None
    desired_state: RegistryDesiredState
    try:
        registry = read_source_registry(handler._health_root)
        if registry is None:
            registry = AlertmanagerSourceRegistry()

        # Build canonical registry key preferring cluster_label (stable) over cluster_context
        registry_key = build_canonical_registry_key(
            cluster_context=sources_view.cluster_context,
            cluster_label=cluster_label,
            canonical_identity=source_view.canonical_identity,
        )
        existing_entry = registry.entries.get(registry_key)

        if action == SourceAction.PROMOTE:
            desired_state = RegistryDesiredState.MANUAL
        else:
            desired_state = RegistryDesiredState.DISABLED

        # Create or update registry entry
        if existing_entry is None:
            # Create new registry entry for this source
            # Use cluster_label (stable, operator-facing) as primary identifier
            # because cluster_context can change with kubeconfig edits/renames
            entry_cluster_context = cluster_label or sources_view.cluster_context
            new_entry = RegistryEntry(
                cluster_context=entry_cluster_context,
                canonical_identity=source_view.canonical_identity,
                desired_state=desired_state,
                reason=reason,
                operator=None,  # Could be populated from auth context if available
                source_run_id=context.run.run_id,
                endpoint=getattr(source_view, "endpoint", None),
                namespace=source_view.namespace,
                name=source_view.name,
                original_origin=getattr(source_view, "origin", None),
                original_state=getattr(source_view, "state", None),
            )
            registry.add_entry(new_entry)
        else:
            # Update existing entry - create a new entry with updated values
            updated_entry = RegistryEntry(
                cluster_context=existing_entry.cluster_context,
                canonical_identity=existing_entry.canonical_identity,
                desired_state=desired_state,
                reason=reason or existing_entry.reason,
                operator=existing_entry.operator,
                updated_at=datetime.now(UTC),
                source_run_id=context.run.run_id,
                endpoint=existing_entry.endpoint,
                namespace=existing_entry.namespace,
                name=existing_entry.name,
                original_origin=existing_entry.original_origin,
                original_state=existing_entry.original_state,
            )
            registry.add_entry(updated_entry)

        write_source_registry(registry, handler._health_root)
    except Exception as exc:
        # Log warning but don't fail the request - override was written successfully
        logger.warning(
            "Failed to persist source to durable registry",
            extra={
                "source_id": source_key,
                "cluster_label": cluster_label,
                "action": action.value,
                "error": str(exc),
            },
        )

    # Write the immutable action artifact for audit trail
    # This creates an append-only record that survives beyond run-scoped overrides
    action_artifact_path: Path | None = None
    try:
        # Get previous desired state for the registry entry if it existed
        previous_desired_state: str | None = None
        if existing_entry is not None:
            previous_desired_state = existing_entry.desired_state.value if existing_entry.desired_state else None

        action_artifact_path = write_source_action_artifact(
            directory=handler._health_root,
            run_id=context.run.run_id,
            source_id=source_key,
            action=action,
            cluster_label=cluster_label,
            cluster_context=sources_view.cluster_context,
            canonical_identity=source_view.canonical_identity,
            endpoint=source_view.endpoint,
            namespace=source_view.namespace,
            name=source_view.name,
            original_origin=source_view.origin,
            original_state=source_view.state,
            resulting_state=desired_state.value,
            reason=reason,
            previous_desired_state=previous_desired_state,
        )
        logger.debug(
            "Wrote source action artifact",
            extra={
                "action_artifact": str(action_artifact_path),
                "source_id": source_key,
                "action": action.value,
            },
        )
    except Exception as exc:
        # Non-fatal: log warning but don't fail the request
        # The override and registry were already written successfully
        logger.warning(
            "Failed to write source action artifact",
            extra={
                "source_id": source_key,
                "cluster_label": cluster_label,
                "action": action.value,
                "error": str(exc),
            },
        )

    # Invalidate UI caches by touching ui-index.json
    # This ensures the next /api/run request rebuilds the payload with new source state
    ui_index_path = handler.runs_dir / "health" / "ui-index.json"
    if ui_index_path.exists():
        try:
            ui_index_path.touch()
        except Exception:
            pass  # Non-fatal

    # Also clear the in-memory cache for this run
    with _run_payload_cache_lock:
        # Remove entries for this run_id (any mtime) to force rebuild
        keys_to_remove = [k for k in _run_payload_cache if k[0] == context.run.run_id]
        for key in keys_to_remove:
            del _run_payload_cache[key]

    action_label = "promoted to manual" if action == SourceAction.PROMOTE else "disabled from auto-tracking"
    logger.info(
        f"Alertmanager source {action_label}",
        extra={
            "source_id": source_key,
            "endpoint": source_view.endpoint,
            "namespace": source_view.namespace,
            "name": source_view.name,
            "original_origin": source_view.origin,
            "original_state": source_view.state,
            "run_id": context.run.run_id,
            "reason": reason,
        },
    )

    # Build response with artifact paths
    response = {
        "status": "success",
        "summary": f"Source {source_key} {action_label}",
        "sourceId": source_key,
        "action": action.value,
        "artifactPath": str(overrides_path.relative_to(handler.runs_dir)),
        "reason": reason,
    }

    # Include action artifact path and id if it was written
    if action_artifact_path is not None:
        response["actionArtifactPath"] = str(action_artifact_path.relative_to(handler._health_root))
        # Extract artifact_id from the written artifact for identity surfacing
        try:
            artifact_content = json.loads(action_artifact_path.read_text(encoding="utf-8"))
            if "artifact_id" in artifact_content:
                response["actionArtifactId"] = artifact_content["artifact_id"]
        except Exception:
            # Non-fatal: log but don't fail the response
            logger.warning(
                "Failed to read artifact_id from action artifact",
                extra={"source_id": source_key, "artifact_path": str(action_artifact_path)},
            )

    handler._send_json(response)
