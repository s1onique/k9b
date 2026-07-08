"""Helm test helpers for internal API configuration.

This module provides common Helm --set values that satisfy the internal API
validation requirements in the k9b chart.

Usage:
    from tests.helm_test_helpers import COMMON_INTERNAL_API_SET

    result = subprocess.run(
        ["helm", "template", "k9b", "charts/k9b", *COMMON_INTERNAL_API_SET],
        ...
    )
"""

from __future__ import annotations

# Common internal API set for tests that don't test incident promotion validation
COMMON_INTERNAL_API_SET: list[str] = [
    "--set", "backend.internalApi.existingSecret=k9b-internal-api",
    "--set", "scheduler.incidentPromotion.internalApi.existingSecret=k9b-internal-api",
    "--set", "scheduler.incidentPromotion.internalApi.backendUrl=http://k9b-backend.k9b.svc.cluster.local:8080",
]

# Minimal internal API set for basic render tests
MINIMAL_INTERNAL_API_SET: list[str] = [
    "--set", "backend.internalApi.existingSecret=k9b-internal-api",
]


def helm_template_args(*extra: str) -> list[str]:
    """Generate helm template command args with internal API defaults.

    Args:
        extra: Additional --set or -f arguments

    Returns:
        List of command arguments for helm template
    """
    return [
        "helm",
        "template",
        "k9b",
        "charts/k9b",
        "--namespace",
        "k9b",
        *COMMON_INTERNAL_API_SET,
        *extra,
    ]
