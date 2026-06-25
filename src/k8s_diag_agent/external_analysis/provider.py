"""Provider connectivity status for external analysis adapters.

This module provides a one-shot sanitized provider connectivity probe that:
- Checks if provider is configured
- Attempts a lightweight connectivity check (HEAD/GET to health endpoint)
- Returns only status enum, HTTP class, and connectivity phase
- Never prints raw URL, hostname, IP, token, or response body

Used by /api/health/details to diagnose provider connection failures.
"""

from __future__ import annotations

import logging
import socket
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Timeout for connectivity probe (seconds)
_CONNECTIVITY_TIMEOUT_SECONDS = 5


def _classify_connectivity_error(exc: Exception) -> tuple[str, str]:
    """Classify a connectivity error into enum reason codes.
    
    Args:
        exc: The exception from connectivity probe
        
    Returns:
        Tuple of (error_type, error_class) where both are sanitized enum strings.
        error_type: One of timeout, connection, auth, unavailable, unknown
        error_class: Full reason code like provider_timeout, provider_connection_failed
    """
    exc_str = str(exc).lower()
    exc_type = type(exc).__name__.lower()
    
    # Timeout detection
    if "timeout" in exc_str or exc_type == "timeouterror":
        return "timeout", "provider_timeout"
    
    # DNS resolution failures
    if "name or service not known" in exc_str or "nodename nor servname" in exc_str:
        return "dns", "provider_connection_failed"
    
    # Connection refused/reset
    if "connection refused" in exc_str or "connection reset" in exc_str:
        return "connection", "provider_connection_failed"
    
    # Network unreachable
    if "network is unreachable" in exc_str or "no route to host" in exc_str:
        return "network", "provider_connection_failed"
    
    # TLS/SSL errors
    if "ssl" in exc_str or "tls" in exc_str or exc_type in ("sslfoundation", "sslerror"):
        return "tls", "provider_connection_failed"
    
    # Authentication/authorization
    if "401" in exc_str or "403" in exc_str or "auth" in exc_str:
        return "auth", "provider_auth_failed"
    
    # Service unavailable (404, 503)
    if "404" in exc_str or "not found" in exc_str:
        return "unavailable", "provider_unavailable"
    if "503" in exc_str or "unavailable" in exc_str:
        return "unavailable", "provider_unavailable"
    
    # Default unknown
    return "unknown", "provider_unknown_error"


def _probe_tcp_connectivity(host: str, port: int, timeout: int = _CONNECTIVITY_TIMEOUT_SECONDS) -> tuple[bool, str]:
    """Probe TCP connectivity to host:port.
    
    Args:
        host: Hostname or IP address
        port: Port number
        timeout: Connection timeout in seconds
        
    Returns:
        Tuple of (success, phase) where phase is one of:
        - dns_resolved: DNS resolved but TCP not yet attempted
        - tcp_connecting: TCP connection attempt started
        - tcp_connected: TCP connection successful
        - tcp_refused: Connection refused
        - tcp_timeout: Connection timed out
        - tcp_error: Other TCP error
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return True, "tcp_connected"
    except TimeoutError:
        return False, "tcp_timeout"
    except ConnectionRefusedError:
        return False, "tcp_refused"
    except OSError:
        # OSError messages may contain endpoint details - never leak raw text
        return False, "tcp_error"


def _probe_https_connectivity(url: str, timeout: int = _CONNECTIVITY_TIMEOUT_SECONDS) -> tuple[bool, str, str]:
    """Probe HTTPS connectivity with sanitized output.
    
    Args:
        url: Full URL to probe (https only)
        timeout: Request timeout in seconds
        
    Returns:
        Tuple of (success, phase, error_class):
        - success: True if connection succeeded
        - phase: One of dns, connect, tls, http, success
        - error_class: Sanitized error classification
    """
    try:
        import requests
    except ImportError:
        # Fallback to socket-based probe
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or 443
        success, tcp_phase = _probe_tcp_connectivity(host, port, timeout)
        if success:
            return True, "tcp_only", "provider_available"
        return False, tcp_phase, _classify_connectivity_error(Exception(tcp_phase))[1]
    
    try:
        # Use HEAD request for minimal data transfer
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        if response.status_code < 400:
            return True, "success", "provider_available"
        elif response.status_code == 401 or response.status_code == 403:
            return False, "http_auth_required", "provider_auth_failed"
        elif response.status_code == 404:
            return False, "http_not_found", "provider_unavailable"
        elif response.status_code >= 500:
            return False, "http_server_error", "provider_unavailable"
        else:
            return True, "success", "provider_available"
    except requests.Timeout:
        return False, "timeout", "provider_timeout"
    except requests.ConnectionError as exc:
        exc_str = str(exc).lower()
        # Extract phase from error message
        if "name or service not known" in exc_str:
            return False, "dns_failed", "provider_connection_failed"
        if "connection refused" in exc_str:
            return False, "connection_refused", "provider_connection_failed"
        if "timeout" in exc_str:
            return False, "timeout", "provider_timeout"
        return False, "connection_failed", "provider_connection_failed"
    except requests.RequestException as exc:
        error_type, error_class = _classify_connectivity_error(exc)
        return False, error_type, error_class
    except Exception as exc:
        error_type, error_class = _classify_connectivity_error(exc)
        return False, error_type, error_class


def get_provider_status() -> dict[str, Any]:
    """Get the external analysis provider health status.
    
    This function performs a one-shot sanitized connectivity probe and returns
    only status enums, HTTP classes, and connectivity phases - never raw URLs,
    hostnames, IPs, tokens, or response bodies.
    
    Returns:
        dict with keys:
        - available: bool - whether provider is available
        - error: str | None - sanitized error classification (enum value)
        - phase: str | None - connectivity phase (dns, tcp, tls, http, success)
        - error_class: str | None - full reason code (provider_timeout, etc.)
    """
    try:
        # Import from the diagnosis provider registry
        from ..collect.api_incident_one_pass_diagnosis_provider import (
            get_diagnosis_provider,
            is_production_provider_initialized,
        )
    except ImportError:
        return {
            "available": False,
            "error": "provider_status_unavailable",
            "phase": "import_failed",
            "error_class": "provider_status_unavailable",
        }
    
    # Check if provider was initialized
    if not is_production_provider_initialized():
        return {
            "available": False,
            "error": "provider_unconfigured",
            "phase": "not_initialized",
            "error_class": "provider_unavailable",
        }
    
    provider = get_diagnosis_provider()
    if provider is None:
        return {
            "available": False,
            "error": "provider_not_configured",
            "phase": "null_provider",
            "error_class": "provider_unavailable",
        }
    
    # Check if the provider has a config with base_url
    try:
        from ..collect.diagnosis_provider_config import DiagnosisProviderConfig
        config = DiagnosisProviderConfig.from_env(required=False)
        
        if config is None or config.base_url is None:
            return {
                "available": False,
                "error": "provider_no_base_url",
                "phase": "config_missing",
                "error_class": "provider_unavailable",
            }
        
        # Build health endpoint URL (probe the base URL for connectivity)
        base_url = config.base_url.rstrip("/")
        health_url = f"{base_url}/health"
        
        # Perform sanitized connectivity probe
        success, phase, error_class = _probe_https_connectivity(health_url)
        
        if success:
            return {
                "available": True,
                "error": None,
                "phase": phase,
                "error_class": "provider_available",
            }
        else:
            return {
                "available": False,
                "error": error_class,
                "phase": phase,
                "error_class": error_class,
            }
            
    except ImportError:
        # Config not available - just check if provider is set
        return {
            "available": True if provider else False,
            "error": None if provider else "provider_not_set",
            "phase": "config_check_skipped",
            "error_class": "provider_available" if provider else "provider_unavailable",
        }
    except Exception as exc:
        error_type, error_class = _classify_connectivity_error(exc)
        return {
            "available": False,
            "error": error_class,
            "phase": error_type,
            "error_class": error_class,
        }


__all__ = [
    "get_provider_status",
]
