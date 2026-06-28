"""Structured error types for one-pass diagnosis service.

These error types allow the route layer to return appropriate HTTP status codes
for different failure conditions, replacing opaque 500 responses.

Error hierarchy:
- DiagnosisServiceError (base)
  - IncidentNotFoundError
  - LLMProviderNotConfiguredError
  - LLMProviderError
  - LLMProviderInvalidResponseError
  - DiagnosisArtifactError
  - DiagnosisServiceInternalError
"""

from __future__ import annotations


class DiagnosisServiceError(Exception):
    """Base exception for one-pass diagnosis service errors.

    Subclasses define the HTTP status code that should be returned to the client.
    """

    error_code: str = "diagnosis_service_error"
    http_status: int = 500
    retryable: bool = False

    def to_dict(self) -> dict[str, object]:
        """Convert error to structured response dict.

        Returns:
            Dict suitable for JSON serialization in HTTP response body.
        """
        return {
            "error": self.error_code,
            "message": str(self),
            "retryable": self.retryable,
        }


class IncidentNotFoundError(DiagnosisServiceError):
    """Raised when the incident does not exist in the store."""

    error_code = "incident_not_found"
    http_status = 404
    retryable = False


class LLMProviderNotConfiguredError(DiagnosisServiceError):
    """Raised when the LLM provider is not configured/initialized."""

    error_code = "llm_provider_not_configured"
    http_status = 503  # Service Unavailable
    retryable = False

    def to_dict(self) -> dict[str, object]:
        result = super().to_dict()
        result["provider_enabled"] = True  # Config exists but not initialized
        return result


class LLMProviderError(DiagnosisServiceError):
    """Raised when the LLM provider call fails (timeout, network, etc.)."""

    error_code = "llm_provider_failed"
    http_status = 502  # Bad Gateway
    retryable = True

    def to_dict(self) -> dict[str, object]:
        result = super().to_dict()
        result["retryable"] = True
        return result


class LLMProviderInvalidResponseError(DiagnosisServiceError):
    """Raised when the LLM provider returns an invalid/malformed response."""

    error_code = "llm_provider_invalid_response"
    http_status = 502  # Bad Gateway
    retryable = False


class DiagnosisArtifactError(DiagnosisServiceError):
    """Raised when artifact persistence fails."""

    error_code = "diagnosis_artifact_write_failed"
    http_status = 500
    retryable = False


class DiagnosisServiceInternalError(DiagnosisServiceError):
    """Raised for unexpected internal errors (catch-all)."""

    error_code = "internal_diagnosis_error"
    http_status = 500
    retryable = False


__all__ = [
    "DiagnosisServiceError",
    "IncidentNotFoundError",
    "LLMProviderNotConfiguredError",
    "LLMProviderError",
    "LLMProviderInvalidResponseError",
    "DiagnosisArtifactError",
    "DiagnosisServiceInternalError",
]
