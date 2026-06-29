"""Common k9b live-lab gates.

This package provides shared health and provider preflight gates for both
CNPG and OTel demo labs. It ensures both labs use the same k9b platform
contracts for:

- Provider status parsing (supports both legacy flattened and dependencies[] formats)
- Provider preflight gate (P0b)
- Common failure classification and defaults

Usage:
    from scripts.lab_common.provider_preflight import run_provider_preflight
    from scripts.lab_common.constants import DEFAULT_K9B_NAMESPACE, DEFAULT_K9B_BACKEND_PORT

Both CNPG and OTel labs should import from this package instead of
implementing their own health/provider parsing logic.
"""

from scripts.lab_common.provider_preflight import (
    FAILURE_PROVIDER_CONFIG_ERROR,
    FAILURE_PROVIDER_CONNECTION_FAILED,
    FAILURE_PROVIDER_DISABLED_REQUIRED,
    FAILURE_PROVIDER_NOT_INITIALIZED,
    FAILURE_PROVIDER_UNAVAILABLE,
    ProviderPreflightResult,
    run_provider_preflight,
)
from scripts.lab_common.provider_status import ProviderStatus, parse_provider_status_from_health_details

__all__ = [
    # Provider status parsing
    "ProviderStatus",
    "parse_provider_status_from_health_details",
    # Provider preflight
    "ProviderPreflightResult",
    "run_provider_preflight",
    "FAILURE_PROVIDER_DISABLED_REQUIRED",
    "FAILURE_PROVIDER_UNAVAILABLE",
    "FAILURE_PROVIDER_NOT_INITIALIZED",
    "FAILURE_PROVIDER_CONNECTION_FAILED",
    "FAILURE_PROVIDER_CONFIG_ERROR",
]
