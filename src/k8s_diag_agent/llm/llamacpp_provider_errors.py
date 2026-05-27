"""Error types and failure classification for llama.cpp provider."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import requests

if TYPE_CHECKING:
    pass  # reserved for type-only imports


class LLMFailureClass(StrEnum):
    """Classification of LLM provider failures for diagnostics and observability."""

    LLM_CLIENT_READ_TIMEOUT = "llm_client_read_timeout"
    LLM_CLIENT_CONNECT_TIMEOUT = "llm_client_connect_timeout"
    LLM_SERVER_HTTP_ERROR = "llm_server_http_error"
    LLM_RESPONSE_PARSE_ERROR = "llm_response_parse_error"
    LLM_CLIENT_REQUEST_ERROR = "llm_client_request_error"
    LLM_ADAPTER_ERROR = "llm_adapter_error"
    LLM_RESPONSE_PARSE_ERROR_LENGTH_CAPPED = "llm_response_parse_error_length_capped"
    LLM_RESPONSE_INVALID_JSON = "llm_response_invalid_json"
    LLM_RESPONSE_UNRECOGNIZED_PAYLOAD = "llm_response_unrecognized_payload"
    LLM_EMPTY_RESPONSE = "llm_empty_response"


def _classify_request_exception(exc: BaseException, exc_name: str) -> tuple[LLMFailureClass, str]:
    """Helper to classify a requests.RequestException or similar."""
    import json

    if isinstance(exc, requests.Timeout):
        # requests.Timeout has two subclasses: ConnectTimeout and ReadTimeout
        # but they may not always be distinguishable, so check class name
        if "Connect" in exc_name or "connect" in str(exc).lower():
            return LLMFailureClass.LLM_CLIENT_CONNECT_TIMEOUT, exc_name
        return LLMFailureClass.LLM_CLIENT_READ_TIMEOUT, exc_name

    if isinstance(exc, requests.ConnectionError):
        err_msg = str(exc).lower()
        if "timeout" in err_msg or "timed out" in err_msg:
            return LLMFailureClass.LLM_CLIENT_CONNECT_TIMEOUT, exc_name
        return LLMFailureClass.LLM_CLIENT_REQUEST_ERROR, exc_name

    if isinstance(exc, requests.RequestException):
        return LLMFailureClass.LLM_CLIENT_REQUEST_ERROR, exc_name

    if isinstance(exc, (ValueError, json.JSONDecodeError)):
        return LLMFailureClass.LLM_RESPONSE_PARSE_ERROR, exc_name

    # Default to adapter error for unexpected exceptions
    return LLMFailureClass.LLM_ADAPTER_ERROR, exc_name


def classify_llm_failure(
    exc: BaseException,
    response: requests.Response | None = None,
    _seen: frozenset[int] | None = None,
) -> tuple[LLMFailureClass, str]:
    """Classify an LLM provider exception into a stable failure class.


    This helper distinguishes common failure modes for better diagnostics:
    - Read timeout (server slow to respond)
    - Connect timeout (cannot reach server)
    - HTTP errors (4xx/5xx responses)
    - Response parse errors (malformed output)
    - Client request errors (other requests lib errors)
    - Adapter errors (unexpected exceptions)
    For wrapped exceptions (e.g., RuntimeError wrapping a requests.RequestException),
    this function checks the exception chain via __cause__ and __context__ to
    preserve the original classification.

    Args:
        exc: The exception that caused the failure.
        response: The HTTP response object if available.
        _seen: Internal - set of seen exception ids to prevent infinite recursion.

    Returns:
        Tuple of (failure_class, exception_type_name)
    """
    exc_name = exc.__class__.__name__
    # Cycle protection: track seen exceptions by id
    if _seen is None:
        _seen = frozenset()
    exc_id = id(exc)
    if exc_id in _seen:
        # Cycle detected - return adapter error to prevent infinite loop
        return LLMFailureClass.LLM_ADAPTER_ERROR, exc_name
    new_seen = _seen | {exc_id}

    # Check for HTTP error responses first
    if response is not None:
        status_code = getattr(response, "status_code", None)
        if status_code is not None:
            if 400 <= status_code < 600:
                return LLMFailureClass.LLM_SERVER_HTTP_ERROR, exc_name
    # Classify HTTPError even without response (e.g., pre-response errors)
    if isinstance(exc, requests.HTTPError):
        return LLMFailureClass.LLM_SERVER_HTTP_ERROR, exc_name
    # For RuntimeError, check if it\'s wrapping a requests exception
    # by traversing the exception chain (__cause__ and __context__)
    if isinstance(exc, RuntimeError):
        # Check the __cause__ first (explicit chaining via 'raise X from Y')
        cause = getattr(exc, '__cause__', None)
        if cause is not None and not isinstance(cause, BaseException):
            cause = None
        if cause is not None:
            # Recursively classify the cause with cycle protection
            cause_class, cause_name = classify_llm_failure(cause, response, new_seen)
            return cause_class, cause_name
        # Check __context__ for implicit exception chaining
        context = getattr(exc, '__context__', None)
        if context is not None and isinstance(context, requests.RequestException):
            # Return the context exception\'s type to preserve the inner exception
            return _classify_request_exception(context, context.__class__.__name__)
        # Fallback: check if the RuntimeError message contains timeout keywords
        exc_msg = str(exc).lower()
        if 'timeout' in exc_msg or 'timed out' in exc_msg:
            if 'connect' in exc_msg:
                return LLMFailureClass.LLM_CLIENT_CONNECT_TIMEOUT, exc_name
            return LLMFailureClass.LLM_CLIENT_READ_TIMEOUT, exc_name
        # Default to adapter error for unexpected RuntimeErrors
        return LLMFailureClass.LLM_ADAPTER_ERROR, exc_name
    return _classify_request_exception(exc, exc_name)


class LLMResponseParseError(ValueError):
    """Exception raised when LLM response cannot be parsed as valid JSON.

    Carries structured output diagnostics for observability and failure analysis.
    """

    def __init__(
        self,
        message: str,
        finish_reason: str | None = None,
        response_content_chars: int | None = None,
        response_content_prefix: str | None = None,
        completion_stopped_by_length: bool = False,
        max_tokens: int | None = None,
    ) -> None:
        super().__init__(message)
        self.finish_reason = finish_reason
        self.response_content_chars = response_content_chars
        self.response_content_prefix = response_content_prefix
        self.completion_stopped_by_length = completion_stopped_by_length
        self.max_tokens = max_tokens

    def to_diagnostics(self) -> dict[str, Any]:
        """Convert to diagnostics dict for failure metadata."""
        return {
            "finish_reason": self.finish_reason,
            "response_content_chars": self.response_content_chars,
            "response_content_prefix": self.response_content_prefix,
            "completion_stopped_by_length": self.completion_stopped_by_length,
            "max_tokens": self.max_tokens,
        }


@dataclass(frozen=True)
class LLMFailureMetadata:
    """Structured metadata for LLM provider failures."""

    failure_class: str
    exception_type: str
    timeout_seconds: int | None = None
    elapsed_ms: int | None = None
    endpoint: str | None = None
    summary: str | None = None
    # Structured output diagnostics
    finish_reason: str | None = None
    response_content_chars: int | None = None
    response_content_prefix: str | None = None
    json_parse_error: str | None = None
    completion_stopped_by_length: bool | None = None
    max_tokens: int | None = None
    provider: str | None = None
    operation: str | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "failure_class": self.failure_class,
            "exception_type": self.exception_type,
        }
        if self.timeout_seconds is not None:
            result["timeout_seconds"] = self.timeout_seconds
        if self.elapsed_ms is not None:
            result["elapsed_ms"] = self.elapsed_ms
        if self.endpoint is not None:
            result["endpoint"] = self.endpoint
        if self.summary is not None:
            result["summary"] = self.summary
        if self.finish_reason is not None:
            result["finish_reason"] = self.finish_reason
        if self.response_content_chars is not None:
            result["response_content_chars"] = self.response_content_chars
        if self.response_content_prefix is not None:
            result["response_content_prefix"] = self.response_content_prefix
        if self.json_parse_error is not None:
            result["json_parse_error"] = self.json_parse_error
        if self.completion_stopped_by_length is not None:
            result["completion_stopped_by_length"] = self.completion_stopped_by_length
        if self.max_tokens is not None:
            result["max_tokens"] = self.max_tokens
        if self.provider is not None:
            result["provider"] = self.provider
        if self.operation is not None:
            result["operation"] = self.operation
        return result


__all__ = [
    "LLMFailureClass",
    "LLMFailureMetadata",
    "LLMResponseParseError",
    "classify_llm_failure",
]
