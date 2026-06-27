"""Classification logic for incident discovery gate.

Provides classification functions to determine failure modes when incident
discovery fails.
"""

from __future__ import annotations

import json
from typing import Any


def classify_api_response_shape(response_body: str) -> str:
    """Classify the shape of the incidents API response.

    Args:
        response_body: Raw response body from /api/incidents

    Returns:
        Shape classification: "valid", "invalid_json", "empty", "missing_incidents_key",
        "malformed", "unknown"
    """
    if not response_body:
        return "empty"

    try:
        data = json.loads(response_body)
    except json.JSONDecodeError:
        return "invalid_json"

    # Check for "incidents" key (current contract)
    if "incidents" in data:
        if isinstance(data["incidents"], list):
            if len(data["incidents"]) > 0:
                return "valid"
            return "valid_but_empty"
        return "malformed"

    # Check for alternative shapes
    if "items" in data:
        return "items_key"
    if "data" in data:
        return "data_key"
    if isinstance(data, list):
        return "top_level_array"

    return "unknown_shape"


def classify_fixture_failure(
    pod_status: dict[str, Any],
    fixture_name: str,
    fixture_namespace: str,
) -> str | None:
    """Classify why the fixture is not producing a candidate.

    Args:
        pod_status: Status from get_pod_status
        fixture_name: Expected fixture name
        fixture_namespace: Expected fixture namespace

    Returns:
        Failure class constant or None if fixture is failing correctly
    """
    if not pod_status.get("found"):
        return "incident_fixture_missing"

    # Check namespace mismatch
    actual_namespace = pod_status.get("namespace", "")
    if actual_namespace != fixture_namespace:
        return "incident_fixture_namespace_mismatch"

    # Check if pod is healthy (all containers ready)
    container_statuses = pod_status.get("container_statuses", [])
    all_ready = all(cs.get("ready", False) for cs in container_statuses)

    if all_ready:
        return "incident_fixture_healthy_unexpectedly"

    # Pod is failing as expected - return None to indicate fixture is correct
    return None


def classify_candidate_detection(
    pod_status: dict[str, Any],
    recent_events: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Classify whether a candidate was detected from fixture state.

    Args:
        pod_status: Status from get_pod_status
        recent_events: Recent namespace events

    Returns:
        Tuple of (candidate_detected, candidate_type)
    """
    if not pod_status.get("found"):
        return False, ""

    phase = pod_status.get("phase", "")
    container_statuses = pod_status.get("container_statuses", [])
    conditions = pod_status.get("conditions", [])

    # Check for readiness failure (our fixture pattern)
    containers_not_ready = any(not cs.get("ready", False) for cs in container_statuses)

    # Check for readiness condition
    readiness_condition = next(
        (c for c in conditions if c.get("type") == "Ready"),
        None
    )
    readiness_false = readiness_condition and readiness_condition.get("status") == "False"

    # Check events for failure indicators
    failure_events = [
        e for e in recent_events
        if e.get("reason") in [
            "Unhealthy",
            "Failed",
            "BackOff",
            "FailedScheduling",
            "FailedCreate",
            "FailedAttach",
        ]
    ]

    if containers_not_ready or readiness_false:
        # This is the expected candidate type from our fixture
        return True, "readiness_failure"

    # Check for other failure modes
    if phase == "Pending":
        return True, "pending"

    if phase == "Failed":
        return True, "failed"

    # Check for crash/restart patterns
    restarts = sum(cs.get("restartCount", 0) for cs in container_statuses)
    if restarts > 3:
        return True, "restart_loop"

    # Check events for failure patterns
    if failure_events:
        reason = failure_events[0].get("reason", "")
        if "BackOff" in reason:
            return True, "crash_loop"
        if "Failed" in reason:
            return True, "scheduling_failure"

    return False, ""


def classify_incident_promotion(
    candidate_detected: bool,
    candidate_type: str,
    api_has_incidents: bool,
) -> str | None:
    """Classify why candidate is not being promoted to incident.

    Args:
        candidate_detected: Whether a candidate was detected
        candidate_type: Type of candidate detected
        api_has_incidents: Whether API returned any incidents

    Returns:
        Failure class constant or None if promotion is working
    """
    if not candidate_detected:
        return "incident_candidate_not_detected"

    if candidate_detected and not api_has_incidents:
        return "incident_candidate_not_promoted"

    return None


def classify_api_contract_issue(
    response_body: str,
    http_status: int,
) -> str | None:
    """Classify API contract issues.

    Args:
        response_body: Raw response body
        http_status: HTTP status code

    Returns:
        Failure class constant or None if no contract issue
    """
    if http_status != 200:
        return None  # Not a contract issue, HTTP error

    shape = classify_api_response_shape(response_body)

    if shape in ["invalid_json", "malformed", "unknown_shape", "items_key", "data_key", "top_level_array"]:
        return "incident_api_contract_mismatch"

    return None


def sanitize_api_response_for_logging(response_body: str, max_length: int = 500) -> str:
    """Sanitize API response for safe logging.

    Args:
        response_body: Raw response body
        max_length: Maximum length to preserve

    Returns:
        Sanitized response (structure only, no sensitive values)
    """
    if not response_body:
        return "(empty)"

    try:
        data = json.loads(response_body)
    except json.JSONDecodeError:
        # Not JSON - truncate and note
        if len(response_body) > max_length:
            return response_body[:max_length] + "...(truncated)"
        return response_body

    # Extract structure only
    if isinstance(data, dict):
        if "incidents" in data:
            incidents = data["incidents"]
            if isinstance(incidents, list):
                return f'{{"incidents": [{len(incidents)} items]}}'
            return f'{{"incidents": {type(incidents).__name__}}}'
        return f'{{keys: {list(data.keys())}}}'

    if isinstance(data, list):
        return f"[array with {len(data)} items]"

    return str(type(data))


def extract_incident_id_from_response(response_body: str) -> str:
    """Extract incident ID from API response.

    Args:
        response_body: Raw response body

    Returns:
        First incident ID or empty string if none found
    """
    if not response_body:
        return ""

    try:
        data = json.loads(response_body)
    except json.JSONDecodeError:
        return ""

    incidents = data.get("incidents", [])
    if incidents and len(incidents) > 0:
        incident = incidents[0]
        if isinstance(incident, dict):
            return str(incident.get("incident_id", ""))
        # List of strings
        if isinstance(incident, str):
            return incident

    return ""
