"""Provider connectivity status for external analysis adapters.

This module provides a one-shot sanitized provider connectivity probe that:
- Checks if provider is configured
- Attempts a lightweight connectivity check (GET to /models endpoint)
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


def _normalize_openai_compatible_url(base_url: str) -> str:
    """Normalize base_url to OpenAI-compatible /models endpoint.
    
    For OpenAI-compatible providers, this function produces an idempotent normalization:
    - /v1 -> /v1/models
    - /v1/models -> /v1/models (already normalized)
    - /v1/chat/completions -> /v1/models
    - /v1/responses -> /v1/models
    - /v1/completions -> /v1/models
    - /v1/embeddings -> /v1/models
    - no /v1 suffix -> /v1/models
    
    This handles the common OpenAI API patterns:
    - https://api.openai.com/v1 -> https://api.openai.com/v1/models
    - https://api.openai.com/v1/chat/completions -> https://api.openai.com/v1/models
    - http://localhost:11434 -> http://localhost:11434/v1/models (Ollama)
    - http://localhost:8080/v1 -> http://localhost:8080/v1/models
    
    Args:
        base_url: The provider's base URL (may or may not include /v1)
        
    Returns:
        The normalized /models endpoint URL
    """
    normalized = base_url.rstrip("/")
    
    # Already normalized - return as-is
    if normalized.endswith("/v1/models"):
        return normalized
    
    # Common endpoint suffixes to strip
    endpoint_suffixes = (
        "/v1/chat/completions",
        "/v1/responses",
        "/v1/completions",
        "/v1/embeddings",
    )
    
    for suffix in endpoint_suffixes:
        if normalized.endswith(suffix):
            base = normalized[: -len(suffix)]
            return f"{base}/v1/models"
    
    # If ends with /v1, append /models
    if normalized.endswith("/v1"):
        return f"{normalized}/models"
    
    # Otherwise append /v1/models
    return f"{normalized}/v1/models"


def _classify_connectivity_error(exc: Exception) -> tuple[str, str]:
    """Classify a connectivity error into enum reason codes.
    
    Args:
        exc: The exception from connectivity probe
        
    Returns:
        Tuple of (phase, error_class) where both are sanitized enum strings.
        phase: One of timeout, dns_failed, connection_refused, connection_failed, tls_failed, http_auth_required, unavailable, unknown
        error_class: Full reason code like provider_timeout, provider_connection_failed
        
    Note: phase values are normalized to match ALLOWED_PROVIDER_PHASES in allowlists.py
    """
    exc_str = str(exc).lower()
    exc_type = type(exc).__name__.lower()
    
    # Timeout detection
    if "timeout" in exc_str or exc_type == "timeouterror":
        return "timeout", "provider_timeout"
    
    # DNS resolution failures
    if "name or service not known" in exc_str or "nodename nor servname" in exc_str:
        return "dns_failed", "provider_connection_failed"
    
    # Connection refused/reset
    if "connection refused" in exc_str or "connection reset" in exc_str:
        return "connection_refused", "provider_connection_failed"
    
    # Network unreachable
    if "network is unreachable" in exc_str or "no route to host" in exc_str:
        return "connection_failed", "provider_connection_failed"
    
    # TLS/SSL errors
    if "ssl" in exc_str or "tls" in exc_str or exc_type in ("sslfoundation", "sslerror"):
        return "tls_failed", "provider_connection_failed"
    
    # Authentication/authorization
    if "401" in exc_str or "403" in exc_str or "auth" in exc_str:
        return "http_auth_required", "provider_auth_failed"
    
    # Service unavailable (404, 503)
    if "404" in exc_str or "not found" in exc_str:
        return "models_endpoint_not_found", "provider_unavailable"
    if "503" in exc_str or "unavailable" in exc_str:
        return "http_server_error", "provider_unavailable"
    
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


def _probe_models_endpoint(url: str, api_key: str | None, timeout: int = _CONNECTIVITY_TIMEOUT_SECONDS) -> tuple[bool, str, str]:
    """Probe OpenAI-compatible /models endpoint with sanitized output.
    
    Args:
        url: Full URL to /models endpoint
        api_key: Optional API key for Authorization header (must be resolved secret value)
        timeout: Request timeout in seconds
        
    Returns:
        Tuple of (success, phase, error_class):
        - success: True if models list returned successfully
        - phase: One of models_list_ok, models_endpoint_not_found, http_auth_required, http_rate_limited, http_server_error, timeout, dns_failed, connection_refused, connection_failed, tls_failed, unknown
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
    
    # Build headers - never log api_key
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    try:
        # Use GET request for /models endpoint (HEAD may not work for all providers)
        response = requests.get(url, timeout=timeout, allow_redirects=True, headers=headers)
        
        # 200: Models list OK - verify JSON structure
        if response.status_code == 200:
            try:
                data = response.json()
                # Accept both object with "data" array and plain array
                if isinstance(data, dict) and "data" in data:
                    return True, "models_list_ok", "provider_available"
                elif isinstance(data, list):
                    return True, "models_list_ok", "provider_available"
                else:
                    # Valid JSON but unexpected structure - still consider available
                    return True, "models_list_ok", "provider_available"
            except ValueError:
                # Valid HTTP but not JSON - still available if we got 200
                return True, "models_list_ok", "provider_available"
        
        # 401/403: Authentication required
        elif response.status_code == 401 or response.status_code == 403:
            return False, "http_auth_required", "provider_auth_failed"
        
        # 404: Models endpoint not found
        elif response.status_code == 404:
            return False, "models_endpoint_not_found", "provider_unavailable"
        
        # 429: Rate limited
        elif response.status_code == 429:
            return False, "http_rate_limited", "provider_unavailable"
        
        # 5xx: Server error
        elif response.status_code >= 500:
            return False, "http_server_error", "provider_unavailable"
        
        # Other 2xx/3xx: Treat as success
        else:
            return True, "models_list_ok", "provider_available"
            
    except requests.Timeout:
        return False, "timeout", "provider_timeout"
    except requests.ConnectionError as exc:
        exc_str = str(exc).lower()
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
    
    This function performs a one-shot sanitized connectivity probe against
    the OpenAI-compatible /models endpoint and returns only status enums,
    HTTP classes, and connectivity phases - never raw URLs, hostnames, IPs,
    tokens, or response bodies.
    
    Returns:
        dict with keys:
        - available: bool - whether provider is available
        - error: str | None - sanitized error classification (enum value)
        - phase: str | None - connectivity phase (models_list_ok, models_endpoint_not_found, etc.)
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
        
        # Normalize base_url to OpenAI-compatible /models endpoint
        models_url = _normalize_openai_compatible_url(config.base_url)
        
        # Get API key using the config's get_api_key() method
        # This returns the resolved secret value from K9B_DIAGNOSIS_API_KEY env var
        # (not the env var name itself)
        api_key = config.get_api_key()
        
        # Perform sanitized connectivity probe to /models endpoint
        success, phase, error_class = _probe_models_endpoint(models_url, api_key)
        
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
    "_normalize_openai_compatible_url",
    "_probe_models_endpoint",
]
