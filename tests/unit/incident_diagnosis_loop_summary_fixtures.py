"""Fixtures for diagnosis loop summary tests.

This module provides shared test helpers for diagnosis loop summary projection tests.
Kept minimal and explicit - no clever factories that obscure payload shapes.
"""

from __future__ import annotations


def make_event(
    event_id: str,
    event_type: str,
    occurred_at: str,
    data: dict | None = None,
) -> dict:
    """Create a diagnosis loop event dict.

    Args:
        event_id: Unique identifier for the event
        event_type: One of diagnosis_loop_started, diagnosis_loop_completed,
                   diagnosis_loop_failed
        occurred_at: ISO 8601 timestamp string
        data: Optional event metadata dict

    Returns:
        Event dict with required fields for build_automatic_diagnosis_loop_summary
    """
    return {
        "event_id": event_id,
        "incident_id": "test-incident",
        "event_type": event_type,
        "actor": "system",
        "occurred_at": occurred_at,
        "message": f"Test {event_type}",
        "data": data,
    }
