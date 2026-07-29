"""Dispatcher configuration and mode resolution.

ACT-K9B-HULK-PROMOTION-DISPATCHER-RESPONSIBILITY-SPLIT01.

This module owns the SINGLE source of truth for the dispatch
configuration and the closed dispatch-mode resolution.  Every other
dispatcher module imports :data:`IncidentPromotionDispatchConfig`
from here so the dataclass, the environment resolver, and the
mode-resolution helpers all live in one cycle-free module.

Hard constraints enforced:

* ``IncidentPromotionDispatchConfig.resolved_mode`` collapses the
  ``auto`` mode to a concrete ``local`` / ``backend-api`` value so
  callers never branch on the ``auto`` value at runtime.
* ``is_config_valid`` rejects backend-api mode without a backend URL
  OR without an internal API token so the dispatcher fails closed.
* ``can_use_local`` rejects the local path when the process role is
  scheduler and the store backend is sqlite.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal

from .incident_promotion_dispatch_constants import (
    INCIDENT_ACCESS_MODE_BACKEND,
    INCIDENT_ACCESS_MODE_LOCAL,
    MODE_AUTO,
    MODE_BACKEND_API,
    MODE_LOCAL,
)

_logger = logging.getLogger(__name__)

# Environment variables
ENV_PROMOTION_MODE = "K9B_INCIDENT_PROMOTION_MODE"
ENV_BACKEND_URL = "K9B_BACKEND_INTERNAL_URL"
ENV_INTERNAL_API_TOKEN = "K9B_INTERNAL_API_TOKEN"
ENV_STORE_BACKEND = "K9B_INCIDENT_STORE_BACKEND"
ENV_PROCESS_ROLE = "K9B_PROCESS_ROLE"

# Process roles
ROLE_BACKEND = "backend"
ROLE_SCHEDULER = "scheduler"


def _incident_access_mode_for_promotion_mode(
    promotion_mode: Literal["local", "backend-api"],
) -> str:
    """Derive the canonical incident access mode for a promotion mode."""
    return (
        INCIDENT_ACCESS_MODE_LOCAL
        if promotion_mode == MODE_LOCAL
        else INCIDENT_ACCESS_MODE_BACKEND
    )


@dataclass(frozen=True)
class IncidentPromotionDispatchConfig:
    """Configuration for incident promotion dispatcher."""

    mode: Literal["local", "backend-api", "auto"]
    backend_url: str | None
    internal_api_token: str | None
    store_backend: str
    process_role: str

    def resolved_mode(self) -> Literal["local", "backend-api"]:
        """Resolve auto mode to concrete mode."""
        if self.mode == MODE_LOCAL:
            return MODE_LOCAL
        if self.mode == MODE_BACKEND_API:
            return MODE_BACKEND_API
        # Auto mode
        if self.store_backend == "sqlite":
            return MODE_BACKEND_API
        if self.process_role == ROLE_SCHEDULER:
            return MODE_BACKEND_API
        return MODE_LOCAL

    def resolved_incident_access_mode(self) -> str:
        """Resolve the access mode that corresponds to the resolved mode."""
        return _incident_access_mode_for_promotion_mode(self.resolved_mode())

    def requires_backend_api(self) -> bool:
        """Check if backend API is required for promotion."""
        return self.resolved_mode() == MODE_BACKEND_API

    def can_use_local(self) -> bool:
        """Check if local promotion is allowed."""
        resolved = self.resolved_mode()
        if resolved == MODE_LOCAL:
            if self.process_role == ROLE_SCHEDULER and self.store_backend == "sqlite":
                return False
            return True
        return False

    def is_config_valid(self) -> tuple[bool, str | None]:
        """Validate configuration for the resolved mode."""
        if self.resolved_mode() == MODE_BACKEND_API:
            if not self.backend_url:
                return False, "missing_backend_url"
            if not self.internal_api_token:
                return False, "missing_internal_api_token"
        return True, None


def _get_dispatch_config() -> IncidentPromotionDispatchConfig:
    """Get the current dispatch configuration from environment."""
    return IncidentPromotionDispatchConfig(
        mode=os.environ.get(ENV_PROMOTION_MODE, MODE_AUTO).lower(),  # type: ignore[arg-type]
        backend_url=os.environ.get(ENV_BACKEND_URL),
        internal_api_token=os.environ.get(ENV_INTERNAL_API_TOKEN),
        store_backend=os.environ.get(ENV_STORE_BACKEND, "memory").lower(),
        process_role=os.environ.get(ENV_PROCESS_ROLE, "").lower(),
    )


def log_promotion_config() -> None:
    """Log the current promotion configuration at startup."""
    config = _get_dispatch_config()
    resolved = config.resolved_mode()
    is_valid, error = config.is_config_valid()

    if is_valid:
        _logger.info(
            "Incident promotion configured",
            extra={
                "event": "incident-promotion-configured",
                "promotion_mode": resolved,
                "backend_url": config.backend_url or "none",
                "store_backend": config.store_backend,
                "process_role": config.process_role or "unset",
            },
        )
    else:
        _logger.error(
            "Incident promotion configuration invalid",
            extra={
                "event": "incident-promotion-config-invalid",
                "reason": error,
                "promotion_mode": resolved,
                "backend_url": config.backend_url or "none",
                "store_backend": config.store_backend,
                "process_role": config.process_role or "unset",
            },
        )


__all__ = [
    "IncidentPromotionDispatchConfig",
    "_get_dispatch_config",
    "_incident_access_mode_for_promotion_mode",
    "log_promotion_config",
]