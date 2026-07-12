"""Next-check and AlertManager dispatch adapters.

Split from api_dispatch_adapters.py to keep file sizes below LLM-friendly thresholds.

All AlertManager-source dispatch adapters parse ``sourceId`` from non-path
locations to support opaque identifiers that contain ``/``:

* ``perform_alertmanager_source_action``  -> JSON request body.
* ``probe_alertmanager_source``            -> JSON request body.
* ``get_alertmanager_source_debug_packet`` -> required ``sourceId`` query param.
* ``get_alertmanager_source_promotion_review`` -> required ``sourceId`` query param.

No URL-encoded path parameters are used. ``urllib.parse.unquote`` is no longer
needed because the path itself does not carry the source identifier.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import parse_qs

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler


def _query_first_value(query: str, key: str) -> str | None:
    """Return the first decoded query value for ``key``.

    ``parse_qs`` parses standard ``application/x-www-form-urlencoded`` data
    and transparently percent-decodes values (e.g. ``%2F`` -> ``/``). No
    additional manual ``unquote`` pass is applied afterwards, which avoids
    double decoding while still surfacing the canonical identifier at the
    HTTP boundary. Returns ``None`` if the key is missing or empty.
    """
    if not query:
        return None
    values = parse_qs(query, keep_blank_values=False).get(key)
    if not values:
        return None
    first = values[0]
    return first if first else None


# Next-check adapters (POST routes)
# =============================================================================


def handle_deterministic_promotion_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for POST /api/deterministic-next-check/promote."""
    from .server_next_checks import handle_deterministic_promotion

    handle_deterministic_promotion(handler)


def handle_next_check_execution_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for POST /api/next-check-execution."""
    from .server_next_checks import handle_next_check_execution

    handle_next_check_execution(handler)


def handle_next_check_approval_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for POST /api/next-check-approval."""
    from .server_next_checks import handle_next_check_approval

    handle_next_check_approval(handler)


def handle_usefulness_feedback_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for POST /api/next-check-execution-usefulness."""
    from .server_feedback import handle_usefulness_feedback

    handle_usefulness_feedback(handler)


def handle_alertmanager_relevance_feedback_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for POST /api/alertmanager-relevance-feedback."""
    from .server_feedback import handle_alertmanager_relevance_feedback

    handle_alertmanager_relevance_feedback(handler)


def handle_batch_next_check_execution_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for POST /api/run-batch-next-check-execution."""
    from .server_batch_execution import handle_run_batch_next_check_execution

    handle_run_batch_next_check_execution(handler)


# AlertManager source adapters
# =============================================================================


def handle_alertmanager_source_action_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for POST /api/runs/{run_id}/alertmanager-sources/action.

    Note: sourceId is read from the request body (not the URL path) to support
    slashes in source identifiers like 'crd:monitoring/kube-prometheus-stack-alertmanager'.
    """
    from .server_alertmanager import handle_alertmanager_source_action
    from .server_shared import _validate_json_mutation_request

    run_id = path_params.get("run_id", "")

    # Validate Content-Type and parse JSON body
    payload = _validate_json_mutation_request(handler)
    if payload is None:
        return

    # Read source_id from body
    source_id = payload.get("sourceId")
    if not isinstance(source_id, str) or not source_id:
        handler._send_json({"error": "sourceId is required in request body"}, 400)
        return

    # Pass the already-parsed payload to avoid double-reading the request body
    handle_alertmanager_source_action(handler, run_id, source_id, payload)


def handle_alertmanager_sources_review_packet_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/runs/{run_id}/alertmanager-sources/review-packet."""
    from .server_alertmanager import handle_alertmanager_sources_review_packet

    run_id = path_params.get("run_id", "")
    handle_alertmanager_sources_review_packet(handler, run_id)


def handle_alertmanager_source_debug_packet_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/runs/{run_id}/alertmanager-sources/debug-packet.

    The source identifier is supplied via the required ``sourceId`` query
    parameter. The URL path does not contain ``{source_id}`` so ``unquote`` is
    no longer required and slash-containing identifiers pass through unchanged.
    """
    from .server_alertmanager import handle_alertmanager_source_debug_packet

    run_id = path_params.get("run_id", "")
    source_id = _query_first_value(query, "sourceId")
    if not source_id:
        handler._send_json(
            {"error": "sourceId query parameter is required"},
            400,
        )
        return
    handle_alertmanager_source_debug_packet(handler, run_id, source_id)


def handle_alertmanager_source_debug_packet_probe_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for POST /api/runs/{run_id}/alertmanager-sources/debug-packet/probe.

    The source identifier is supplied in the JSON request body so the POST path
    stays stable regardless of the identifier content.
    """
    from .server_alertmanager import handle_alertmanager_source_debug_packet
    from .server_shared import _validate_json_mutation_request

    run_id = path_params.get("run_id", "")

    payload = _validate_json_mutation_request(handler)
    if payload is None:
        return

    source_id = payload.get("sourceId")
    if not isinstance(source_id, str) or not source_id:
        handler._send_json({"error": "sourceId is required in request body"}, 400)
        return

    handle_alertmanager_source_debug_packet(handler, run_id, source_id, probe_now=True)


def handle_alertmanager_source_promotion_review_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/runs/{run_id}/alertmanager-sources/promotion-review.

    The source identifier is supplied via the required ``sourceId`` query
    parameter. The URL path does not contain ``{source_id}`` so ``unquote`` is
    no longer required and slash-containing identifiers pass through unchanged.
    """
    from .server_alertmanager import handle_alertmanager_source_promotion_review

    run_id = path_params.get("run_id", "")
    source_id = _query_first_value(query, "sourceId")
    if not source_id:
        handler._send_json(
            {"error": "sourceId query parameter is required"},
            400,
        )
        return
    handle_alertmanager_source_promotion_review(handler, run_id, source_id)
