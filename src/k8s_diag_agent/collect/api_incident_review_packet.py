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
        return result


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

        return IncidentReviewPacketResponse(
            bundle_id=bundle_id,
            packet=packet,
            format=request.format,
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
