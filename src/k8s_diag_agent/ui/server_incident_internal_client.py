"""Scheduler client for internal API communication.

Client for scheduler to submit promotion requests to backend.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from .server_incident_internal_models import PromotionResponse

_logger = logging.getLogger(__name__)


def create_scheduler_client(base_url: str, token: str | None = None) -> SchedulerClient:
    """Create a scheduler client for posting to backend internal API.

    Args:
        base_url: Base URL of the k9b-backend service
        token: Optional internal API token

    Returns:
        SchedulerClient instance
    """
    return SchedulerClient(base_url, token)


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
        self._base_url = base_url.rstrip("/")
        self._token = token

    def promote_candidates(
        self,
        candidates: list[dict[str, Any]],
        observed_at: datetime,
        snapshot_bundle_id: str | None = None,
        timeout: float = 30.0,
    ) -> PromotionResponse:
        """Promote candidates via backend internal API.

        Args:
            candidates: List of candidate dicts
            observed_at: When candidates were observed
            snapshot_bundle_id: Optional snapshot bundle ID
            timeout: Request timeout in seconds

        Returns:
            PromotionResponse from backend
        """
        import urllib.error
        import urllib.request

        url = f"{self._base_url}/api/internal/incidents/promote-candidates"
        payload = {
            "candidates": candidates,
            "observed_at": observed_at.isoformat(),
        }
        if snapshot_bundle_id:
            payload["snapshot_bundle_id"] = snapshot_bundle_id

        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        req = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method="POST",
        )

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
                return PromotionResponse(
                    ok=False,
                    errors=1,
                    error_messages=[str(e)],
                )
        except Exception as e:
            return PromotionResponse(
                ok=False,
                errors=1,
                error_messages=[str(e)],
            )

    def promote_alert_signals(
        self,
        candidates: list[dict[str, Any]],
        observed_at: datetime,
        snapshot_bundle_id: str | None = None,
        timeout: float = 30.0,
    ) -> PromotionResponse:
        """Promote alert signals via backend internal API.

        Args:
            candidates: List of candidate dicts
            observed_at: When signals were observed
            snapshot_bundle_id: Optional snapshot bundle ID
            timeout: Request timeout in seconds

        Returns:
            PromotionResponse from backend
        """
        import urllib.error
        import urllib.request

        url = f"{self._base_url}/api/internal/incidents/promote-alert-signals"
        payload = {
            "candidates": candidates,
            "observed_at": observed_at.isoformat(),
        }
        if snapshot_bundle_id:
            payload["snapshot_bundle_id"] = snapshot_bundle_id

        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        req = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method="POST",
        )

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
                return PromotionResponse(
                    ok=False,
                    errors=1,
                    error_messages=[str(e)],
                )
        except Exception as e:
            return PromotionResponse(
                ok=False,
                errors=1,
                error_messages=[str(e)],
            )
