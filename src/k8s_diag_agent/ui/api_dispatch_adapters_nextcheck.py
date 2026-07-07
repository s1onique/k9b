"""Next-check and AlertManager dispatch adapters.

Split from api_dispatch_adapters.py to keep file sizes below LLM-friendly thresholds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler


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
    """Dispatch adapter for POST /api/runs/{run_id}/alertmanager-sources/{source_id}/action."""
    from urllib.parse import unquote

    from .server_alertmanager import handle_alertmanager_source_action

    run_id = path_params.get("run_id", "")
    source_id = path_params.get("source_id", "")
    # Decode URL-encoded source_id
    source_id = unquote(source_id)
    handle_alertmanager_source_action(handler, run_id, source_id)


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
    """Dispatch adapter for GET /api/runs/{run_id}/alertmanager-sources/{source_id}/debug-packet."""
    from urllib.parse import unquote

    from .server_alertmanager import handle_alertmanager_source_debug_packet

    run_id = path_params.get("run_id", "")
    source_id = path_params.get("source_id", "")
    # Decode URL-encoded source_id
    source_id = unquote(source_id)
    handle_alertmanager_source_debug_packet(handler, run_id, source_id)


def handle_alertmanager_source_debug_packet_probe_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for POST /api/runs/{run_id}/alertmanager-sources/{source_id}/debug-packet/probe."""
    from urllib.parse import unquote

    from .server_alertmanager import handle_alertmanager_source_debug_packet

    run_id = path_params.get("run_id", "")
    source_id = path_params.get("source_id", "")
    # Decode URL-encoded source_id
    source_id = unquote(source_id)
    handle_alertmanager_source_debug_packet(handler, run_id, source_id, probe_now=True)


def handle_alertmanager_source_promotion_review_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/runs/{run_id}/alertmanager-sources/{source_id}/promotion-review."""
    from urllib.parse import unquote

    from .server_alertmanager import handle_alertmanager_source_promotion_review

    run_id = path_params.get("run_id", "")
    source_id = path_params.get("source_id", "")
    # Decode URL-encoded source_id
    source_id = unquote(source_id)
    handle_alertmanager_source_promotion_review(handler, run_id, source_id)
