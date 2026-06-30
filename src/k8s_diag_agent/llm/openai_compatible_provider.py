"""OpenAI-compatible provider that speaks the OpenAI API."""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import requests

from .assessor_schema import AssessorAssessment
from .base import LLMProvider
from .openai_compatible_provider_config import (
    _REVIEW_ENRICHMENT_SYSTEM_INSTRUCTIONS,
    DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN,
    DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT,
    DEFAULT_TIMEOUT_SECONDS,
    OpenAICompatibleProviderConfig,
)
from .openai_compatible_provider_errors import (
    LLMFailureClass,
    LLMFailureMetadata,
    LLMResponseParseError,
    classify_llm_failure,
)
from .openai_compatible_provider_payloads import build_payload, build_request_headers
from .openai_compatible_provider_response import (
    _extract_response_diagnostics,
    build_error_message,
    extract_assessment,
)

if TYPE_CHECKING:
    from .base import LLMAssessmentInput

SessionFactory = Callable[[], requests.Session]


class OpenAICompatibleProvider(LLMProvider):
    """Provider implementation that calls an OpenAI-compatible endpoint."""

    # Re-export internal helpers for backward compatibility
    _extract_assessment = staticmethod(extract_assessment)
    _extract_response_diagnostics = staticmethod(_extract_response_diagnostics)

    def __init__(
        self,
        config: OpenAICompatibleProviderConfig | None = None,
        session_factory: SessionFactory | None = None,
    ) -> None:
        self._config = config
        self._session_factory = session_factory or requests.Session
        self._session: requests.Session | None = None
        self._endpoint: str | None = None

    def _ensure_ready(self) -> tuple[OpenAICompatibleProviderConfig, requests.Session, str]:
        if self._config is None:
            self._config = OpenAICompatibleProviderConfig.from_env()
        if self._session is None:
            self._session = self._session_factory()
        if self._endpoint is None:
            self._endpoint = self._config.endpoint
        return self._config, self._session, self._endpoint

    def max_tokens_for_operation(self, operation: str) -> int | None:
        """Get max_tokens for a given operation type.

        Args:
            operation: One of "auto-drilldown" or "review-enrichment"

        Returns:
            The configured max_tokens for the operation, or None if not applicable
        """
        config, _, _ = self._ensure_ready()
        if operation == "auto-drilldown":
            return config.max_tokens_auto_drilldown
        elif operation == "review-enrichment":
            return config.max_tokens_review_enrichment
        return None

    def assess(
        self,
        prompt: str,
        payload: LLMAssessmentInput,
        *,
        validate_schema: bool = True,
        system_instructions: str | None = None,
        max_tokens: int | None = None,
        response_format_json: bool | None = None,
    ) -> dict[str, Any]:
        config, session, endpoint = self._ensure_ready()
        # Use config default when response_format_json is None
        effective_response_format_json = (
            response_format_json if response_format_json is not None else config.response_format_json
        )
        request_payload = build_payload(
            prompt,
            config,
            system_instructions=system_instructions,
            max_tokens=max_tokens,
            response_format_json=effective_response_format_json,
        )
        response: requests.Response | None = None
        timeout_seconds = config.timeout_seconds
        try:
            response = session.post(
                endpoint,
                json=request_payload,
                headers=build_request_headers(config),
                timeout=timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(
                build_error_message(config.base_url, endpoint, exc, response, timeout_seconds)
            ) from exc
        assert response is not None
        raw = response.json()
        assessment = extract_assessment(raw, max_tokens=max_tokens)
        if validate_schema:
            try:
                validated = AssessorAssessment.from_dict(assessment)
            except ValueError as exc:
                from .openai_compatible_provider_response import _payload_snippet
                snippet = _payload_snippet(assessment)
                raise ValueError(
                    f"Assessor schema validation failed: {exc}; assessment snippet: {snippet}"
                ) from exc
            return validated.to_dict()
        return assessment


# Re-export public API from split modules for backward compatibility
__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN",
    "DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT",
    "OpenAICompatibleProvider",
    "OpenAICompatibleProviderConfig",
    "LLMFailureClass",
    "LLMFailureMetadata",
    "LLMResponseParseError",
    "_REVIEW_ENRICHMENT_SYSTEM_INSTRUCTIONS",
    "classify_llm_failure",
]
