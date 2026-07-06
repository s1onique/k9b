"""API trace exerciser for k9b backend trace capture lab.

This module provides functions to exercise representative API endpoints
and trigger both HTTP and internal spans for trace capture.

The exerciser targets:
- GET /api/health/details
- GET /api/incidents
- GET /api/incidents/{incident_id}
- POST diagnosis/review/handoff endpoints that trigger internal spans
"""

from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class APIExerciseConfig:
    """Configuration for API trace exerciser."""

    base_url: str = "http://localhost:8080"
    timeout_seconds: float = 10.0
    incident_id: str | None = None  # Use existing incident if provided


# =============================================================================
# HTTP Client Helpers
# =============================================================================


def _make_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 10.0,
) -> tuple[int, bytes]:
    """Make an HTTP request.

    Args:
        method: HTTP method
        url: Full URL
        headers: Optional headers
        body: Optional request body
        timeout: Request timeout in seconds

    Returns:
        Tuple of (status_code, response_body)
    """
    req_headers = headers or {}
    req_headers.setdefault("Accept", "application/json")
    req_headers.setdefault("Content-Type", "application/json")

    request = urllib.request.Request(
        url,
        method=method,
        headers=req_headers,
        data=body,
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return (response.status, response.read())
    except urllib.error.HTTPError as e:
        return (e.code, e.read() if e.fp else b"")
    except urllib.error.URLError as e:
        logger.warning("Request failed: %s", e.reason)
        return (0, str(e.reason).encode())


# =============================================================================
# API Exercise Functions
# =============================================================================


def exercise_health_details(config: APIExerciseConfig) -> dict[str, Any]:
    """Exercise GET /api/health/details endpoint.

    Args:
        config: API exercise configuration

    Returns:
        Result dictionary with status and response
    """
    url = f"{config.base_url}/api/health/details"
    status, body = _make_request("GET", url, timeout=config.timeout_seconds)

    result: dict[str, Any] = {
        "endpoint": "/api/health/details",
        "method": "GET",
        "status_code": status,
        "success": status == 200,
    }

    if body:
        try:
            result["response"] = json.loads(body)
        except json.JSONDecodeError:
            result["response_text"] = body.decode(errors="replace")[:200]

    return result


def exercise_incident_list(config: APIExerciseConfig) -> dict[str, Any]:
    """Exercise GET /api/incidents endpoint.

    Args:
        config: API exercise configuration

    Returns:
        Result dictionary with status and response
    """
    url = f"{config.base_url}/api/incidents"
    status, body = _make_request("GET", url, timeout=config.timeout_seconds)

    result: dict[str, Any] = {
        "endpoint": "/api/incidents",
        "method": "GET",
        "status_code": status,
        "success": status == 200,
    }

    if body:
        try:
            data = json.loads(body)
            result["response"] = data
            # Extract first incident ID for detail exercise
            if isinstance(data, dict) and "incidents" in data:
                incidents = data["incidents"]
                if incidents and isinstance(incidents, list):
                    first = incidents[0]
                    if isinstance(first, dict) and "incident_id" in first:
                        config.incident_id = first["incident_id"]
        except json.JSONDecodeError:
            result["response_text"] = body.decode(errors="replace")[:200]

    return result


def exercise_incident_detail(config: APIExerciseConfig) -> dict[str, Any]:
    """Exercise GET /api/incidents/{incident_id} endpoint.

    Args:
        config: API exercise configuration (may have incident_id pre-set)

    Returns:
        Result dictionary with status and response
    """
    if not config.incident_id:
        return {
            "endpoint": "/api/incidents/{incident_id}",
            "method": "GET",
            "status_code": None,
            "success": False,
            "error": "No incident_id available",
        }

    url = f"{config.base_url}/api/incidents/{config.incident_id}"
    status, body = _make_request("GET", url, timeout=config.timeout_seconds)

    result: dict[str, Any] = {
        "endpoint": f"/api/incidents/{config.incident_id}",
        "method": "GET",
        "status_code": status,
        "success": status == 200,
    }

    if body:
        try:
            result["response"] = json.loads(body)
        except json.JSONDecodeError:
            result["response_text"] = body.decode(errors="replace")[:200]

    return result


def exercise_diagnosis_handoff(config: APIExerciseConfig) -> dict[str, Any]:
    """Exercise POST diagnosis review handoff endpoint.

    This exercises the automatic diagnosis review handoff which triggers
    internal spans for artifact reading and review packet loading.

    Args:
        config: API exercise configuration

    Returns:
        Result dictionary with status and response
    """
    if not config.incident_id:
        return {
            "endpoint": "/api/incidents/{incident_id}/automatic-diagnosis-review/handoff",
            "method": "POST",
            "status_code": None,
            "success": False,
            "error": "No incident_id available",
        }

    url = f"{config.base_url}/api/incidents/{config.incident_id}/automatic-diagnosis-review/handoff"
    body = json.dumps({}).encode()
    status, response_body = _make_request(
        "POST", url, body=body, timeout=config.timeout_seconds
    )

    result: dict[str, Any] = {
        "endpoint": f"/api/incidents/{config.incident_id}/automatic-diagnosis-review/handoff",
        "method": "POST",
        "status_code": status,
        "success": status in (200, 201, 204),
    }

    if response_body:
        try:
            result["response"] = json.loads(response_body)
        except json.JSONDecodeError:
            result["response_text"] = response_body.decode(errors="replace")[:200]

    return result


def exercise_all_endpoints(config: APIExerciseConfig) -> list[dict[str, Any]]:
    """Exercise all representative API endpoints.

    Args:
        config: API exercise configuration

    Returns:
        List of exercise results for each endpoint
    """
    results: list[dict[str, Any]] = []

    # Exercise in order: health -> list -> detail -> handoff
    results.append(exercise_health_details(config))
    results.append(exercise_incident_list(config))
    results.append(exercise_incident_detail(config))
    results.append(exercise_diagnosis_handoff(config))

    return results


# =============================================================================
# Main
# =============================================================================


def main() -> None:
    """CLI entry point for API exerciser."""
    import argparse

    parser = argparse.ArgumentParser(description="Exercise k9b backend API for trace capture")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8080",
        help="Backend base URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Request timeout in seconds (default: 10.0)",
    )
    parser.add_argument(
        "--incident-id",
        help="Use specific incident ID instead of discovering from list",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    config = APIExerciseConfig(
        base_url=args.base_url,
        timeout_seconds=args.timeout,
        incident_id=args.incident_id,
    )

    results = exercise_all_endpoints(config)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("API Exercise Results:")
        print("-" * 60)
        for result in results:
            status = "✓" if result["success"] else "✗"
            endpoint = result["endpoint"]
            code = result.get("status_code", "N/A")
            print(f"  {status} {result['method']} {endpoint} -> {code}")


if __name__ == "__main__":
    main()
