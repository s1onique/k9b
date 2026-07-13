"""Incident fetch via internal API.

This module provides the get_incident method for fetching individual incidents
from the backend via the internal API. Extracted from server_incident_internal_client.py
to keep file sizes manageable.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, cast
from urllib.parse import urlencode

from .server_incident_internal_models import PromotionResponse

_logger = logging.getLogger(__name__)


class SchedulerBackendPromotionError(Exception):
    """Error when backend URL is not configured."""

    pass


def create_scheduler_client(base_url: str, token: str | None = None) -> SchedulerClient:
    """Create a scheduler client for posting to backend internal API.

    Args:
        base_url: Base URL of the k9b-backend service
        token: Optional internal API token

    Returns:
        SchedulerClient instance
    """
    return SchedulerClient(base_url, token)


def _serialize_datetime(dt: Any) -> str:
    """Serialize datetime to ISO format string.

    Args:
        dt: datetime object or similar with isoformat method

    Returns:
        ISO format datetime string
    """
    if hasattr(dt, "isoformat"):
        return str(dt.isoformat())
    return str(dt)


class SchedulerClient:
    """Client for scheduler to submit promotion requests to backend.

    Usage:
        client = create_scheduler_client("http://k9b-backend:8080", "token")
        response = client.promote_candidates(candidates, observed_at)
    """

    def __init__(self, base_url: str, token: str | None = None) -> None:
        """Initialize scheduler client.

        Args:
            base_url: Base URL of k9b-backend service
            token: Internal API token
        """
        self._base_url = base_url.rstrip("/") if base_url else ""
        self._token = token

    def _require_backend_url(self) -> str:
        """Validate and return the backend URL.

        Raises:
            SchedulerBackendPromotionError: If backend URL is not configured
        """
        backend_url = (self._base_url or "").strip()
        if not backend_url:
            raise SchedulerBackendPromotionError(
                "backend internal API URL is not configured"
            )
        return backend_url

    def promote_candidates(
        self,
        candidates: list[dict[str, Any]],
        observed_at: Any,  # datetime
        snapshot_bundle_id: str | None = None,
        timeout: float = 30.0,
    ) -> PromotionResponse:
        """Promote candidates via backend internal API."""
        try:
            self._require_backend_url()
        except SchedulerBackendPromotionError as e:
            return PromotionResponse(ok=False, errors=1, error_messages=[str(e)])

        url = f"{self._base_url}/api/internal/incidents/promote-candidates"
        payload = {
            "candidates": candidates,
            "observed_at": _serialize_datetime(observed_at),
        }
        if snapshot_bundle_id:
            payload["snapshot_bundle_id"] = snapshot_bundle_id

        data = json.dumps(payload).encode("utf-8")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                result = json.loads(body)
                return PromotionResponse(**result)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            try:
                err_data = json.loads(body)
                return PromotionResponse(
                    ok=False,
                    errors=1,
                    error_messages=[err_data.get("message", str(e))],
                )
            except json.JSONDecodeError:
                return PromotionResponse(ok=False, errors=1, error_messages=[str(e)])
        except Exception as e:
            return PromotionResponse(ok=False, errors=1, error_messages=[str(e)])

    def promote_alert_signals(
        self,
        candidates: list[dict[str, Any]],
        observed_at: Any,  # datetime
        snapshot_bundle_id: str | None = None,
        timeout: float = 30.0,
    ) -> PromotionResponse:
        """Promote alert signals via backend internal API (legacy batch)."""
        try:
            self._require_backend_url()
        except SchedulerBackendPromotionError as e:
            return PromotionResponse(ok=False, errors=1, error_messages=[str(e)])

        url = f"{self._base_url}/api/internal/incidents/promote-alert-signals"
        payload = {
            "candidates": candidates,
            "observed_at": _serialize_datetime(observed_at),
        }
        if snapshot_bundle_id:
            payload["snapshot_bundle_id"] = snapshot_bundle_id

        data = json.dumps(payload).encode("utf-8")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                result = json.loads(body)
                return PromotionResponse(**result)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            try:
                err_data = json.loads(body)
                return PromotionResponse(
                    ok=False,
                    errors=1,
                    error_messages=[err_data.get("message", str(e))],
                )
            except json.JSONDecodeError:
                return PromotionResponse(ok=False, errors=1, error_messages=[str(e)])
        except Exception as e:
            return PromotionResponse(ok=False, errors=1, error_messages=[str(e)])

    def promote_alert_signals_scoped(
        self,
        *,
        run_id: str,
        source_identity: str,
        signal_ids: list[str],
        timeout: float = 30.0,
    ) -> dict[str, Any] | PromotionResponse:
        """Submit the explicit current-run promotion scope.

        Returns the raw response dict so the scheduler can read the new
        ``actionableIncidentIds`` projection without losing the legacy
        ``PromotionResponse`` compatibility surface. Errors fall through
        as the standard ``PromotionResponse(ok=False, ...)`` shape so
        the dispatcher can keep its existing error handling.
        """
        try:
            self._require_backend_url()
        except SchedulerBackendPromotionError as e:
            return PromotionResponse(ok=False, errors=1, error_messages=[str(e)])

        url = f"{self._base_url}/api/internal/incidents/promote-alert-signals"
        payload = {
            "runId": run_id,
            "sourceIdentity": source_identity,
            "signalIds": list(signal_ids),
        }
        data = json.dumps(payload).encode("utf-8")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                return cast("dict[str, Any]", json.loads(body))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            try:
                err_data = json.loads(err_body)
                return PromotionResponse(
                    ok=False,
                    errors=1,
                    error_messages=[err_data.get("message", str(e))],
                )
            except json.JSONDecodeError:
                return PromotionResponse(ok=False, errors=1, error_messages=[str(e)])
        except Exception as e:
            return PromotionResponse(ok=False, errors=1, error_messages=[str(e)])

    def list_incidents(
        self,
        status: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        active_only: bool = False,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """List incidents from backend via internal API.

        This method enables the automatic diagnosis loop to read incidents
        from the backend SQLite store when running in backend-api mode.

        Uses the canonical internal API path: GET /api/internal/incidents

        Args:
            status: Optional status filter (e.g., "open", "collecting_evidence")
            limit: Optional maximum number of incidents to return
            cursor: Optional cursor token for keyset pagination
            active_only: If True, only return active incidents
            timeout: Request timeout in seconds

        Returns:
            Dict with "incidents" list, "nextCursor", "hasMore", and "total", or error dict
            Error dict includes:
            - error: Error message
            - error_type: Classified error type (unauthorized, timeout, etc.)
            - status_code: HTTP status code if available
            - incidents: Empty list
            - nextCursor: None
            - hasMore: False
            - total: 0
        """
        # Validate backend URL first - return bounded error if not configured
        try:
            self._require_backend_url()
        except SchedulerBackendPromotionError as e:
            return {
                "error": str(e),
                "error_type": "missing_backend_url",
                "status_code": None,
                "incidents": [],
                "nextCursor": None,
                "hasMore": False,
                "total": 0,
            }

        # Check for missing token
        if not self._token:
            return {
                "error": "Internal API token is not configured",
                "error_type": "missing_internal_token",
                "status_code": None,
                "incidents": [],
                "nextCursor": None,
                "hasMore": False,
                "total": 0,
            }

        # Canonical internal API path with proper query encoding
        url = f"{self._base_url}/api/internal/incidents"
        params: dict[str, str | int] = {}
        if status is not None:
            params["status"] = status
        if limit is not None:
            params["limit"] = limit
        if cursor is not None:
            params["cursor"] = cursor
        if active_only:
            params["activeOnly"] = "true"
        if params:
            url = f"{url}?{urlencode(params)}"

        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        req = urllib.request.Request(url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                decoded = json.loads(body)
                # Validate response shape
                if not isinstance(decoded, dict):
                    return {
                        "error": "Unexpected response: expected dict, got " + type(decoded).__name__,
                        "error_type": "unexpected_shape",
                        "status_code": None,
                        "incidents": [],
                        "nextCursor": None,
                        "hasMore": False,
                        "total": 0,
                    }
                if "incidents" not in decoded:
                    return {
                        "error": "Unexpected response: missing 'incidents' field",
                        "error_type": "unexpected_shape",
                        "status_code": None,
                        "incidents": [],
                        "nextCursor": None,
                        "hasMore": False,
                        "total": 0,
                    }
                if not isinstance(decoded["incidents"], list):
                    return {
                        "error": "Unexpected response: 'incidents' is not a list",
                        "error_type": "unexpected_shape",
                        "status_code": None,
                        "incidents": [],
                        "nextCursor": None,
                        "hasMore": False,
                        "total": 0,
                    }
                # Return with default values for backward compatibility
                return {
                    "incidents": decoded.get("incidents", []),
                    "nextCursor": decoded.get("nextCursor"),
                    "hasMore": decoded.get("hasMore", False),
                    "total": decoded.get("total", len(decoded.get("incidents", []))),
                }
        except json.JSONDecodeError:
            return {
                "error": "Invalid JSON in response",
                "error_type": "invalid_json",
                "status_code": None,
                "incidents": [],
                "nextCursor": None,
                "hasMore": False,
                "total": 0,
            }
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            # Classify the error based on status code
            error_type = "unknown"
            if e.code == 401:
                error_type = "unauthorized"
            elif e.code == 403:
                error_type = "forbidden"
            elif e.code == 404:
                error_type = "not_found"
            elif e.code >= 500:
                error_type = "backend_error"
            else:
                error_type = "bad_response"

            try:
                err_data = json.loads(body)
                # Parse error from "message" or "error" field
                error_msg = err_data.get("message") or err_data.get("error") or str(e)
                return {
                    "error": error_msg,
                    "error_type": error_type,
                    "status_code": e.code,
                    "incidents": [],
                    "nextCursor": None,
                    "hasMore": False,
                    "total": 0,
                }
            except json.JSONDecodeError:
                return {
                    "error": str(e),
                    "error_type": error_type,
                    "status_code": e.code,
                    "incidents": [],
                    "nextCursor": None,
                    "hasMore": False,
                    "total": 0,
                }
        except TimeoutError:
            return {
                "error": "Request timed out",
                "error_type": "timeout",
                "status_code": None,
                "incidents": [],
                "nextCursor": None,
                "hasMore": False,
                "total": 0,
            }
        except Exception as e:
            # Classify the error based on exception type
            error_type = "unknown"
            exc_str = str(e).lower()
            if "timeout" in exc_str:
                error_type = "timeout"
            elif "connection refused" in exc_str or "unreachable" in exc_str:
                error_type = "backend_unreachable"

            return {
                "error": str(e),
                "error_type": error_type,
                "status_code": None,
                "incidents": [],
                "nextCursor": None,
                "hasMore": False,
                "total": 0,
            }

    def get_incident(
        self,
        incident_id: str,
        timeout: float = 30.0,
    ) -> dict[str, Any] | None:
        """Get a single incident from backend via internal API."""
        try:
            self._require_backend_url()
        except SchedulerBackendPromotionError:
            return None

        url = f"{self._base_url}/api/internal/incidents/{incident_id}"

        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        req = urllib.request.Request(url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                return dict(json.loads(body))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            body = e.read().decode("utf-8")
            try:
                err_data = json.loads(body)
                _logger.warning(
                    "Failed to fetch incident from backend",
                    extra={
                        "event": "fetch-incident-backend-error",
                        "incident_id": incident_id,
                        "error": err_data.get("message", str(e)),
                    },
                )
                return None
            except json.JSONDecodeError:
                return None
        except Exception as e:
            _logger.warning(
                "Failed to fetch incident from backend",
                extra={
                    "event": "fetch-incident-backend-error",
                    "incident_id": incident_id,
                    "error": str(e),
                },
            )
            return None
