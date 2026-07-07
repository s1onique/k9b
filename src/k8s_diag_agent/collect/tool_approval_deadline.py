"""Approval deadline checking.

This module contains deadline checking functionality:
- check_approval_deadline: Checks if an approval request has exceeded its deadline

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-APPROVAL-STREAM01
"""
from __future__ import annotations

import time

from .tool_approval_types import ApprovalRequest


def check_approval_deadline(
    request: ApprovalRequest,
    current_time_seconds: float | None = None,
) -> tuple[bool, str]:
    """Check if an approval request has exceeded its deadline.

    Args:
        request: The approval request to check
        current_time_seconds: Current time in seconds (defaults to time.time())

    Returns:
        Tuple of (is_expired, time_remaining_or_expired)
    """
    if current_time_seconds is None:
        current_time_seconds = time.time()

    # Parse creation time
    from ..datetime_utils import parse_iso_to_utc

    created = parse_iso_to_utc(request.created_at)
    if created is None:
        return True, "invalid_created_at"

    created_seconds = created.timestamp()
    deadline = created_seconds + request.deadline_seconds

    if current_time_seconds > deadline:
        return True, "expired"

    remaining = deadline - current_time_seconds
    return False, str(int(remaining))


__all__ = [
    "check_approval_deadline",
]
