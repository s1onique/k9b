"""Backend URL helpers for P4c K8s diagnosis phase.

This module provides URL building helpers for backend-targeted diagnosis.
Uses namespace-qualified Kubernetes Service DNS to ensure the backend
is reachable from any namespace (e.g., from the lab-artifacts runner).
"""

from __future__ import annotations

import urllib.parse


def _build_backend_url(namespace: str, incident_id: str, backend_port: int) -> tuple[str, str, str]:
    """Build the backend URL and components for incident fetch.

    Uses namespace-qualified Kubernetes Service DNS to ensure the backend
    is reachable from any namespace (e.g., from the lab-artifacts runner).

    Returns:
        Tuple of (url, api_path, encoded_incident_id)
    """
    encoded_id = urllib.parse.quote(incident_id, safe="")
    api_path = f"/api/incidents/{encoded_id}"
    # Use namespace-qualified Service DNS for namespace-safe addressing
    # This ensures connectivity even when the caller runs outside the k9b namespace
    service_host = f"k9b-backend.{namespace}.svc.cluster.local"
    url = f"http://{service_host}:{backend_port}{api_path}"
    return url, api_path, encoded_id


def _build_targeted_diagnosis_url(
    namespace: str, incident_id: str, backend_port: int
) -> tuple[str, str]:
    """Build the targeted diagnosis URL and API path.

    Uses namespace-qualified Kubernetes Service DNS for namespace-safe addressing.

    Returns:
        Tuple of (url, api_path)
    """
    encoded_id = urllib.parse.quote(incident_id, safe="")
    api_path = f"/api/incidents/{encoded_id}/automatic-diagnosis-loop/one-pass"
    service_host = f"k9b-backend.{namespace}.svc.cluster.local"
    url = f"http://{service_host}:{backend_port}{api_path}"
    return url, api_path
