"""Production diagnosis provider using OpenAI-compatible API.

This module provides an OpenAI-compatible diagnosis provider that wraps
the existing LlamaCppProvider for the incident one-pass diagnosis service.

Design constraints:
- Implements DiagnosisProvider protocol (complete method)
- Uses bounded output
- Provider credentials come from environment variables
- Fail-closed on provider errors
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import requests
from requests.exceptions import HTTPError

if TYPE_CHECKING:
    from .diagnosis_provider_config import DiagnosisProviderConfig

logger = logging.getLogger(__name__)

# Default system instructions for diagnosis
_DIAGNOSIS_SYSTEM_INSTRUCTIONS = """You are a Kubernetes incident diagnostics assistant.

CRITICAL: Return ONLY a valid JSON object. Do NOT use markdown fences, XML, or any text outside the JSON.
The JSON must contain at minimum these fields:
- summary: A brief summary of the incident (string)
- likely_causes: List of likely causes (array of strings)
- supporting_evidence: Evidence from case file supporting each cause (array of strings)
- recommended_investigations: Read-only investigation suggestions (array of strings)
- uncertainties: Areas of uncertainty or missing information (array of strings)
- confidence: Confidence level (string: "low", "medium", "high", or "unknown")

You MUST NOT:
- Execute any commands or actions
- Promote, apply, or remediate anything
- Delete resources or mutate cluster state
- Recommend executable actions
- Suggest kubectl apply, helm install, or similar mutations

You MAY only:
- Analyze the provided case file
- Suggest read-only investigation directions
- Distinguish facts from hypotheses
- Identify missing evidence
"""


class InvocationTrackingDiagnosisProvider:
    """Wraps any DiagnosisProvider and tracks whether complete() was called.

    Used for live-lab smoke testing to prove provider.complete() was actually invoked,
    not just that a non-NoOp provider was configured.
    """

    def __init__(self, inner: Any) -> None:
        """Initialize the tracking wrapper.

        Args:
            inner: The wrapped DiagnosisProvider instance
        """
        self._inner = inner
        self._invocation_attempted: bool = False

    def complete(self, prompt: str) -> str:
        """Generate completion and track invocation.

        Args:
            prompt: The diagnosis prompt to complete.

        Returns:
            Raw model output as string.
        """
        self._invocation_attempted = True
        result = self._inner.complete(prompt)
        return str(result)

    @property
    def invocation_attempted(self) -> bool:
        """Return True if complete() was called."""
        return self._invocation_attempted


class OpenAICompatibleDiagnosisProvider:
    """OpenAI-compatible diagnosis provider.

    Wraps HTTP API calls to an OpenAI-compatible endpoint for incident diagnosis.
    Implements the DiagnosisProvider protocol (complete method).
    """

    def __init__(
        self,
        config: DiagnosisProviderConfig,
        session_factory: Any = None,
    ) -> None:
        """Initialize the diagnosis provider.

        Args:
            config: Diagnosis provider configuration
            session_factory: Optional factory for requests.Session (for testing)
        """
        self._config = config
        self._session_factory = session_factory or requests.Session
        self._session: requests.Session | None = None

        # Build endpoint URL
        # base_url is the API v1 base, e.g. https://api.openai.com/v1
        # We append only the path segment to form the full endpoint
        base = config.base_url.rstrip("/")
        self._endpoint = f"{base}/chat/completions"

    def _get_session(self) -> requests.Session:
        """Get or create session."""
        if self._session is None:
            self._session = self._session_factory()
        return self._session

    def complete(self, prompt: str) -> str:
        """Generate diagnosis completion for the given prompt.

        Args:
            prompt: The diagnosis prompt to complete.

        Returns:
            Raw model output as string (JSON format).

        Raises:
            RuntimeError: On provider errors (auth failure, timeout, malformed response).
        """
        session = self._get_session()

        # Build request payload
        messages = [
            {"role": "system", "content": _DIAGNOSIS_SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ]

        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
            "temperature": 0.0,  # Deterministic output
            "max_tokens": min(self._config.max_output_chars // 4, 4096),  # Approximate token limit
        }

        # Build headers
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        api_key = self._config.get_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Make request
        try:
            response = session.post(
                self._endpoint,
                json=payload,
                headers=headers,
                timeout=self._config.timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise RuntimeError(
                f"Diagnosis provider timeout after {self._config.timeout_seconds}s: {exc}"
            ) from exc
        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"Diagnosis provider connection failed: {exc}"
            ) from exc
        except HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status == 401 or status == 403:
                raise RuntimeError(
                    f"Diagnosis provider authentication failed (HTTP {status}): "
                    "Check K9B_DIAGNOSIS_API_KEY"
                ) from exc
            raise RuntimeError(
                f"Diagnosis provider HTTP error {status}: {exc}"
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Diagnosis provider request failed: {exc}"
            ) from exc

        # Parse response
        try:
            data = response.json()
        except Exception as exc:
            raise RuntimeError(
                f"Diagnosis provider returned malformed JSON: {exc}"
            ) from exc

        # Extract content from OpenAI-compatible response
        try:
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError("Diagnosis provider returned no choices in response")
            message = choices[0].get("message", {})
            content: str = message.get("content", "")
            if not content:
                raise RuntimeError("Diagnosis provider returned empty content")
            return content
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Diagnosis provider returned unexpected response format: {exc}"
            ) from exc


def build_diagnosis_provider_from_config(
    config: DiagnosisProviderConfig | None,
) -> Any | None:
    """Build a production diagnosis provider from config.

    Args:
        config: Diagnosis provider configuration, or None.

    Returns:
        OpenAICompatibleDiagnosisProvider instance, or None if config is None.

    Raises:
        ValueError: If config specifies unsupported provider type.
    """
    if config is None:
        return None

    if config.provider_name == "openai_compatible":
        return OpenAICompatibleDiagnosisProvider(config)
    elif config.provider_name == "gigachat":
        # GigaChat uses OpenAI-compatible API
        return OpenAICompatibleDiagnosisProvider(config)
    elif config.provider_name == "qwen":
        # Qwen uses OpenAI-compatible API
        return OpenAICompatibleDiagnosisProvider(config)
    else:
        raise ValueError(
            f"Unsupported diagnosis provider type: {config.provider_name}"
        )


__all__ = [
    "OpenAICompatibleDiagnosisProvider",
    "InvocationTrackingDiagnosisProvider",
    "build_diagnosis_provider_from_config",
]
