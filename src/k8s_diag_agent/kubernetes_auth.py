"""Kubernetes authentication mode resolution for kubectl commands.

This module provides auth mode detection and resolution for in-cluster and
kubeconfig-based authentication scenarios.

Auth modes:
- auto: Prefer explicit kubeconfig if present, otherwise use in-cluster auth (default)
- inCluster: Use Pod ServiceAccount token at /var/run/secrets/kubernetes.io/serviceaccount/token
- kubeconfig: Use explicit kubeconfig file (requires KUBECONFIG env or --kubeconfig flag)

Explicit modes (inCluster, kubeconfig) must have their prerequisites available
or they will raise an AuthError. Only 'auto' mode may fallback intelligently.
"""
from __future__ import annotations

import logging
import os
from enum import Enum
from pathlib import Path

# In-cluster auth detection paths
_IN_CLUSTER_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
_IN_CLUSTER_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

_logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Raised when Kubernetes authentication cannot be established."""

    pass


class AuthMode(Enum):
    """Kubernetes authentication mode."""

    AUTO = "auto"
    IN_CLUSTER = "inCluster"
    KUBECONFIG = "kubeconfig"

    @classmethod
    def from_string(cls, value: str | None) -> AuthMode:
        """Parse auth mode from string value.

        Args:
            value: String value from config or environment variable.

        Returns:
            AuthMode enum value (defaults to AUTO if invalid).

        """
        if not value:
            return cls.AUTO
        # Normalize to lowercase for comparison
        normalized = value.lower().strip()
        for mode in cls:
            # Compare lowercase normalized value against enum value
            if mode.value.lower() == normalized:
                return mode
        _logger.warning(
            "Unknown auth mode '%s', defaulting to 'auto'",
            value,
        )
        return cls.AUTO


# Valid auth mode values for config validation
AUTH_MODE_VALUES = tuple(mode.value for mode in AuthMode)


def has_service_account_credentials() -> bool:
    """Check if service account credentials are present.

    Returns True if:
    - Service account token file exists
    - Service account CA file exists

    Note: Does not check KUBECONFIG; use is_in_cluster() for full detection.
    """
    return (
        Path(_IN_CLUSTER_TOKEN_PATH).exists()
        and Path(_IN_CLUSTER_CA_PATH).exists()
    )


def is_in_cluster() -> bool:
    """Detect if running inside a Kubernetes pod using service account.

    Returns True if:
    - KUBECONFIG is not set (to avoid kubeconfig overriding in-cluster config)
    - Service account token file exists
    - Service account CA file exists

    For forced inCluster mode validation, use validate_in_cluster_mode() instead.
    """
    if os.environ.get("KUBECONFIG"):
        return False
    return has_service_account_credentials()


def validate_in_cluster_mode() -> None:
    """Validate that in-cluster mode can work.

    Raises:
        AuthError: If service account credentials are not available.

    """
    if not has_service_account_credentials():
        raise AuthError(
            "Kubernetes auth mode is 'inCluster', but ServiceAccount "
            "token or CA is unavailable at "
            f"{_IN_CLUSTER_TOKEN_PATH} or {_IN_CLUSTER_CA_PATH}"
        )


def validate_kubeconfig_mode(kubeconfig_enabled: bool) -> None:
    """Validate that kubeconfig mode can work.

    Args:
        kubeconfig_enabled: Whether kubeconfig secret is mounted in the pod.

    Raises:
        AuthError: If no kubeconfig is available.

    """
    if not kubeconfig_enabled and not os.environ.get("KUBECONFIG"):
        raise AuthError(
            "Kubernetes auth mode is 'kubeconfig', but no kubeconfig is configured. "
            "Set kubeconfig.enabled=true and provide a kubeconfig Secret, "
            "or set KUBECONFIG environment variable."
        )


def resolve_auth_mode(
    configured_mode: str | AuthMode | None = None,
    *,
    kubeconfig_enabled: bool = False,
) -> AuthMode:
    """Resolve the effective authentication mode.

    Resolves the auth mode based on configured preference, environment detection,
    and kubeconfig availability.

    Args:
        configured_mode: Explicit auth mode from config (string or enum).
        kubeconfig_enabled: Whether kubeconfig secret is mounted in the pod.

    Returns:
        Resolved AuthMode to use for kubectl commands.

    Raises:
        AuthError: If explicit mode (inCluster/kubeconfig) has missing prerequisites.

    Note:
        Explicit modes (inCluster, kubeconfig) validate their prerequisites
        and raise AuthError if unavailable. Only 'auto' mode may fallback.

    """
    # Parse configured mode
    if isinstance(configured_mode, AuthMode):
        mode = configured_mode
    else:
        mode = AuthMode.from_string(configured_mode)

    # Explicit inCluster mode: validate SA credentials exist
    if mode == AuthMode.IN_CLUSTER:
        validate_in_cluster_mode()
        _logger.debug("Auth mode: validated inCluster")
        return mode

    # Explicit kubeconfig mode: validate kubeconfig is available
    if mode == AuthMode.KUBECONFIG:
        validate_kubeconfig_mode(kubeconfig_enabled)
        _logger.debug("Auth mode: validated kubeconfig")
        return mode

    # Auto mode (default logic)
    # Priority: kubeconfig env > in-cluster detection > mounted kubeconfig

    # Check if KUBECONFIG env is set (external kubeconfig takes precedence)
    kubeconfig_env = os.environ.get("KUBECONFIG")
    if kubeconfig_env and kubeconfig_enabled:
        _logger.debug(
            "Auth mode (auto): using kubeconfig from KUBECONFIG env"
        )
        return AuthMode.KUBECONFIG

    # Check in-cluster detection
    if is_in_cluster():
        _logger.debug(
            "Auth mode (auto): detected in-cluster service account auth"
        )
        return AuthMode.IN_CLUSTER

    # Fallback to kubeconfig if available
    if kubeconfig_enabled:
        _logger.debug(
            "Auth mode (auto): falling back to mounted kubeconfig"
        )
        return AuthMode.KUBECONFIG

    # Last resort: try in-cluster anyway (may fail at runtime)
    _logger.warning(
        "Auth mode (auto): no kubeconfig and in-cluster not detected; "
        "attempting in-cluster auth as best effort"
    )
    return AuthMode.IN_CLUSTER


def get_context_for_auth_mode(mode: AuthMode) -> str | None:
    """Get the kubectl context name for the given auth mode.

    Args:
        mode: The resolved authentication mode.

    Returns:
        Context name for kubeconfig mode, or None for in-cluster mode.

    """
    if mode == AuthMode.IN_CLUSTER:
        return "in-cluster"
    # For kubeconfig mode, let kubectl use default context or KUBECONFIG
    return None


def build_kubectl_env(mode: AuthMode) -> dict[str, str | None]:
    """Build environment variables for kubectl based on auth mode.

    Args:
        mode: The resolved authentication mode.

    Returns:
        Dict of env vars to set (None values to unset).

    """
    env: dict[str, str | None] = {}

    if mode == AuthMode.IN_CLUSTER:
        # Ensure KUBECONFIG is not set to avoid overriding in-cluster config
        env["KUBECONFIG"] = None
        _logger.debug("Kubectl env: unsetting KUBECONFIG for in-cluster auth")
    # For kubeconfig mode, let KUBECONFIG from environment or default be used

    return env


def log_auth_mode(
    mode: AuthMode,
    *,
    logger: logging.Logger | None = None,
) -> None:
    """Log the selected auth mode without exposing sensitive values.

    Args:
        mode: The resolved authentication mode.
        logger: Optional logger instance (uses module logger if not provided).

    """
    target_logger = logger or _logger

    if mode == AuthMode.IN_CLUSTER:
        target_logger.info(
            "Kubernetes auth: using in-cluster service account"
        )
    elif mode == AuthMode.KUBECONFIG:
        target_logger.info(
            "Kubernetes auth: using kubeconfig file"
        )
    else:
        target_logger.info(
            "Kubernetes auth: using auto-detected mode"
        )


def resolve_process_auth_mode() -> AuthMode:
    """Resolve auth mode for this process using environment variables.

    This is the canonical function for resolving auth mode in kubectl subprocess
    execution paths. It reads standard environment variables:
    - KUBERNETES_AUTH_MODE: explicit mode (auto, inCluster, kubeconfig)
    - KUBERNETES_AUTH_KUBECONFIG_ENABLED: whether kubeconfig secret is mounted
    - KUBECONFIG: external kubeconfig path (takes precedence if kubeconfig_enabled)

    Returns:
        Resolved AuthMode (IN_CLUSTER or KUBECONFIG, never AUTO).

    Note:
        This function does not raise AuthError for missing prerequisites.
        It returns the resolved mode and lets subprocess execution fail later
        if credentials are actually missing.
    """
    # Check if kubeconfig is enabled (mounted via Helm chart)
    kubeconfig_enabled = os.environ.get("KUBERNETES_AUTH_KUBECONFIG_ENABLED", "").lower() in ("true", "1", "yes")
    # Also check for KUBECONFIG env var as a fallback indicator
    if os.environ.get("KUBECONFIG") and not kubeconfig_enabled:
        kubeconfig_enabled = True

    # Resolve auth mode (returns IN_CLUSTER or KUBECONFIG, never AUTO)
    configured_mode = os.environ.get("KUBERNETES_AUTH_MODE")
    return resolve_auth_mode(
        configured_mode,
        kubeconfig_enabled=kubeconfig_enabled,
    )
