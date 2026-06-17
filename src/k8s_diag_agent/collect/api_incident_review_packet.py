"""API handlers for incident review packet generation.

This module provides the backend API for generating incident review packets
from captured incident bundles. The packet is an internal k9b product artifact.

Hard constraint: End-state must be k9b-only and self-contained.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..security import sanitize_exception_message
from .incident_review_packet import generate_incident_review_packet_from_dict

_logger = logging.getLogger(__name__)


@dataclass
class IncidentReviewPacketRequest:
    """Request shape for incident review packet API."""

    bundle: dict[str, Any]
    """The incident evidence bundle dict from snapshot capture."""

    format: str = "markdown"
    """Output format. Currently only 'markdown' is supported."""


@dataclass
class IncidentReviewPacketResponse:
    """Response shape for incident review packet API."""

    bundle_id: str
    """Bundle ID from the source bundle."""

    packet: str
    """Generated review packet text."""

    format: str
    """Output format (echoed from request)."""

    error: str | None = None
    """Error message if packet generation failed."""

    # Incident state updates after successful packet generation
    incident_updates: dict[str, Any] | None = None
    """Summary of incident state updates (ready_for_review_count, incident_ids)."""

    @classmethod
    def from_error(
        cls,
        message: str,
        bundle_id: str = "",
    ) -> IncidentReviewPacketResponse:
        """Create an error response with sanitized error message."""
        return cls(
            bundle_id=bundle_id,
            packet="",
            format="markdown",
            error=message,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "bundle_id": self.bundle_id,
            "packet": self.packet,
            "format": self.format,
        }
        if self.error is not None:
            result["error"] = self.error
        if self.incident_updates is not None:
            result["incident_updates"] = self.incident_updates
        return result


def _update_incident_state_for_bundle(
    bundle_id: str,
) -> dict[str, Any]:
    """Update incident state after successful review packet generation.

    This function finds incidents with the matching bundle_id and marks them
    as ready_for_review. It is separated from the main handler to enable
    deterministic testing and clean error handling.

    Protected status rule: Does not update SUPPRESSED, DUPLICATE, or RESOLVED
    incidents. These are considered terminal-ish states.

    Args:
        bundle_id: The snapshot bundle ID to match

    Returns:
        Dict with ready_for_review_count and incident_ids
    """
    from .incident_store_provider import get_incident_store

    store = get_incident_store()
    updated_incidents = store.mark_ready_for_review_by_bundle_id(
        snapshot_bundle_id=bundle_id,
        review_packet_id=bundle_id,  # Use bundle_id as review_packet_id
    )

    return {
        "ready_for_review_count": len(updated_incidents),
        "incident_ids": [inc.incident_id for inc in updated_incidents],
    }


def handle_incident_review_packet(
    request: IncidentReviewPacketRequest,
) -> IncidentReviewPacketResponse:
    """Generate an incident review packet from a captured bundle.

    Args:
        request: IncidentReviewPacketRequest with bundle data

    Returns:
        IncidentReviewPacketResponse with generated packet or error
    """
    # Extract bundle_id for response (safe extraction before any processing)
    bundle_data = request.bundle
    metadata = bundle_data.get("metadata", {})
    bundle_id = metadata.get("bundle_id", "unknown")

    try:
        # Validate bundle has required structure
        if not bundle_data.get("metadata"):
            _logger.warning("Review packet request missing metadata")
            return IncidentReviewPacketResponse.from_error(
                message="Bundle missing required metadata",
                bundle_id=bundle_id,
            )

        if not bundle_data.get("pods"):
            _logger.warning("Review packet request missing pods")
            return IncidentReviewPacketResponse.from_error(
                message="Bundle missing pods data",
                bundle_id=bundle_id,
            )

        # Generate the packet
        packet = generate_incident_review_packet_from_dict(bundle_data)

        # Update incident state to mark ready_for_review
        # This is best-effort: failures here should not fail the response
        incident_updates: dict[str, Any] | None = None
        try:
            incident_updates = _update_incident_state_for_bundle(bundle_id)
        except Exception as exc:
            # Log but don't fail - packet generation succeeded
            sanitized_message = sanitize_exception_message(exc, max_length=200)
            _logger.warning(
                "Failed to update incident state for bundle %s: %s",
                bundle_id,
                sanitized_message,
            )

        return IncidentReviewPacketResponse(
            bundle_id=bundle_id,
            packet=packet,
            format=request.format,
            incident_updates=incident_updates,
        )

    except (ValueError, KeyError) as exc:
        # Handle validation/parsing errors
        sanitized_message = sanitize_exception_message(exc, max_length=200)
        _logger.warning(
            "Review packet validation failed for %s: %s",
            bundle_id,
            sanitized_message,
        )
        return IncidentReviewPacketResponse.from_error(
            message=f"Validation error: {sanitized_message}",
            bundle_id=bundle_id,
        )

    except (TypeError, AttributeError) as exc:
        # Handle type errors (e.g., None.value)
        sanitized_message = sanitize_exception_message(exc, max_length=200)
        _logger.warning(
            "Review packet type error for %s: %s",
            bundle_id,
            sanitized_message,
        )
        return IncidentReviewPacketResponse.from_error(
            message=f"Type error: {sanitized_message}",
            bundle_id=bundle_id,
        )

    except OSError as exc:
        # Handle file system errors
        sanitized_message = sanitize_exception_message(exc, max_length=200)
        _logger.warning(
            "Review packet I/O error for %s: %s",
            bundle_id,
            sanitized_message,
        )
        return IncidentReviewPacketResponse.from_error(
            message=f"I/O error: {sanitized_message}",
            bundle_id=bundle_id,
        )

    except RuntimeError as exc:
        # Handle runtime errors from collection
        sanitized_message = sanitize_exception_message(exc, max_length=200)
        _logger.warning(
            "Review packet runtime error for %s: %s",
            bundle_id,
            sanitized_message,
        )
        return IncidentReviewPacketResponse.from_error(
            message=f"Runtime error: {sanitized_message}",
            bundle_id=bundle_id,
        )


__all__ = [
    "IncidentReviewPacketRequest",
    "IncidentReviewPacketResponse",
    "handle_incident_review_packet",
]
