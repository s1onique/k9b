"""Domain exceptions for incident diagnosis review packet operations.

This module provides a single, focused exception type for the review packet
subsystem, enabling callers to handle expected unavailability without broad
exception catching.
"""

from __future__ import annotations


class AutomaticDiagnosisReviewPacketUnavailable(Exception):
    """Raised when an existing review packet cannot be loaded safely.

    Missing review packets are represented as None by the loader. This exception
    is reserved for expected fail-soft load failures such as I/O errors,
    malformed JSON, or missing required packet fields.
    """

    pass
