"""Backend health endpoint for provider-smoke health gate.

This endpoint provides a simple health check that the provider-smoke
Kubernetes liveness/readiness probe can use.

It evaluates backend health using the safe evaluator and returns:
- HTTP 200 when healthy
- HTTP 500 when unhealthy (for Kubernetes probe compatibility)

The response is designed to be:
- Simple: minimal payload for probe compatibility
- Sanitized: no secrets, no raw IPs, no provider URLs

This endpoint is used by the backend health gate script via:
kubectl exec deploy/k9b-backend -c backend -- curl http://localhost:8080/api/health
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from .api_health_details import evaluate_backend_health
from .protocols import JsonResponseSender

logger = logging.getLogger(__name__)


def handle_health(handler: JsonResponseSender) -> None:
    """Handle GET /api/health route.
    
    This endpoint is used by the provider-smoke Kubernetes probe.
    It evaluates backend health using the safe evaluator and returns:
    - HTTP 200 when all dependencies are healthy
    - HTTP 500 when any dependency is unhealthy
    
    Response schema:
    {
        "healthy": bool,
        "timestamp": str,
        "primary_failure_class": str,
    }
    """
    # safe_evaluate_backend_health catches exceptions internally
    evaluation = evaluate_backend_health()
    
    if evaluation.healthy:
        # All dependencies healthy - return 200
        response = {
            "healthy": True,
            "timestamp": datetime.now(UTC).isoformat(),
            "primary_failure_class": "",
        }
        handler._send_json(response, code=200)
    else:
        # Some dependency unhealthy - return 500 for Kubernetes probe
        response = {
            "healthy": False,
            "timestamp": datetime.now(UTC).isoformat(),
            "primary_failure_class": evaluation.primary_failure_class,
        }
        handler._send_json(response, code=500)


def handle_health_route(handler: JsonResponseSender) -> None:
    """Handle GET /api/health route.
    
    Public endpoint (no auth required) for Kubernetes liveness/readiness probes.
    
    Args:
        handler: The HTTP request handler instance
    """
    handle_health(handler)
