"""llama.cpp provider that speaks the OpenAI-compatible API."""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, NoReturn, cast

import requests

from .assessor_schema import AssessorAssessment
from .base import LLMProvider

DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN = 768
DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT = 1200

if TYPE_CHECKING:
    from .base import LLMAssessmentInput

SessionFactory = Callable[[], requests.Session]

_SYSTEM_INSTRUCTIONS = (
    "You are a Kubernetes diagnostics assistant."
    " Provide a single JSON object that matches the AssessorAssessment schema exactly."  # noqa: E501
    " Do not include markdown, XML, or explanatory text outside the JSON payload."  # noqa: E501
    " Include all required keys (observed_signals, findings, hypotheses, next_evidence_to_collect,"
    " recommended_action, safety_level) and set strings accordingly."
)

# System instructions for review-enrichment use case (bounded advisory payload)
_REVIEW_ENRICHMENT_SYSTEM_INSTRUCTIONS = (
    "You are a Kubernetes diagnostics review advisor."
    " Provide a concise JSON advisory payload that includes summary, triageOrder, topConcerns,"
    " evidenceGaps, nextChecks, focusNotes, and optionally alertmanagerEvidenceReferences."  # noqa: E501
    " Use arrays of non-empty strings for list entries and highlight missing data explicitly."  # noqa: E501
    " Do not include markdown, XML, or explanatory text outside the JSON payload."  # noqa: E501
    " When Alertmanager data is available in the input, you may optionally reference it in alertmanagerEvidenceReferences."
    " Each reference MUST cite evidence that was present in the provided Alertmanager compact artifact."
    " You MUST NOT cite alert names, severities, namespaces, or clusters that do NOT appear in the supplied artifacts."
    " alertmanagerEvidenceReferences format: [{\"cluster\": \"<string>\", \"matchedDimensions\": [\"<dim>\",...], \"reason\": \"<string>\", \"usedFor\": \"<top_concern|next_check|summary|triage_order|focus_note>\"}]"  # noqa: E501
    " CRITICAL - usedFor values: Use EXACTLY one of these literals: top_concern, next_check, summary, triage_order, focus_note."
    " Do NOT use plural forms like 'top_concerns', 'next_checks', or 'focus_notes'."
    " Do NOT derive usedFor from field names like topConcerns, nextChecks, or focusNotes."
    " CRITICAL for nextChecks: each entry MUST be an explicit kubectl command in one of these formats:"  # noqa: E501
    " - 'kubectl describe <resource> -n <namespace>'"
    " - 'kubectl logs <pod> -n <namespace>'"
    " - 'kubectl get <resource> -n <namespace>'"
    " - 'kubectl get crd --context <cluster>'"
    " - 'kubectl top <resource> -n <namespace>' (if metrics-server available)"
    " REQUIREMENTS:"
    " - Every nextChecks entry must START with one of: kubectl describe, kubectl logs, kubectl get, kubectl top"  # noqa: E501
    " - Each command must target exactly ONE cluster (use --context flag)"
    " - NEVER use phrases like: validate, review, check status, confirm, investigate, verify, plan upgrade"  # noqa: E501
    " - NEVER suggest 'all clusters', 'across clusters', or multi-cluster commands"
    " - NEVER suggest mutations: do not include apply, patch, scale, edit, upgrade, delete, restart, rollout"  # noqa: E501
    " Examples of CORRECT nextChecks:"
    " - 'kubectl describe pod -n default myapp-abc123 --context cluster1'"
    " - 'kubectl logs deployment/myapp -n production --context admin@prod'"
    " - 'kubectl get crd --context cluster2'"
    " Examples of WRONG nextChecks (will be rejected by planner):"
    " - 'Validate image pull secrets in cluster1' (has 'validate')"
    " - 'Check all clusters for CRDs' (has 'all clusters')"
    " - 'Verify cluster2 version and upgrade to v1.33' (has 'upgrade')"
)


@dataclass(frozen=True)
class LlamaCppProviderConfig:
    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_tokens_auto_drilldown: int = DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN
    max_tokens_review_enrichment: int = DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT

    @property
    def endpoint(self) -> str:
        base = self.base_url.rstrip('/')
        return f"{base}/v1/chat/completions"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> LlamaCppProviderConfig:
        source = env or os.environ
        missing: list[str] = []
        base_raw = source.get("LLAMA_CPP_BASE_URL")
        base_url = base_raw.strip() if base_raw is not None else ""
        if not base_url:
            missing.append("LLAMA_CPP_BASE_URL")
        model_raw = source.get("LLAMA_CPP_MODEL")
        model = model_raw.strip() if model_raw is not None else ""
        if not model:
            missing.append("LLAMA_CPP_MODEL")
        if missing:
            raise RuntimeError(f"Missing environment variables for llamacpp provider: {', '.join(missing)}")
        api_key_raw = source.get("LLAMA_CPP_API_KEY")
        api_key: str | None = None
        if api_key_raw is not None:
            stripped = api_key_raw.strip()
            if stripped:
                api_key = stripped
        timeout_seconds = cls._parse_timeout(source.get("LLAMA_CPP_TIMEOUT_SECONDS"))
        max_tokens_auto_drilldown = cls._parse_max_tokens(source.get("LLAMA_CPP_MAX_TOKENS_AUTO_DRILLDOWN"), DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN)
        max_tokens_review_enrichment = cls._parse_max_tokens(source.get("LLAMA_CPP_MAX_TOKENS_REVIEW_ENRICHMENT"), DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT)
        return cls(
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_tokens_auto_drilldown=max_tokens_auto_drilldown,
            max_tokens_review_enrichment=max_tokens_review_enrichment,
        )

    @staticmethod
    def _parse_timeout(value: str | None) -> int:
        if value is None:
            return DEFAULT_TIMEOUT_SECONDS
        trimmed = value.strip()
        if not trimmed:
            return DEFAULT_TIMEOUT_SECONDS
        try:
            parsed = int(trimmed)
        except ValueError as exc:
            raise ValueError(
                f"LLAMA_CPP_TIMEOUT_SECONDS must be an integer but got '{value}'"
            ) from exc
        if parsed <= 0:
            raise ValueError("LLAMA_CPP_TIMEOUT_SECONDS must be a positive integer")
        return parsed

    @staticmethod
    def _parse_max_tokens(value: str | None, default: int) -> int:
        """Parse max_tokens from env var, returning default if not set or invalid."""
        if value is None:
            return default
        trimmed = value.strip()
        if not trimmed:
            return default
        try:
            parsed = int(trimmed)
        except ValueError:
            return default
        if parsed <= 0:
            return default
        return parsed


class LlamaCppProvider(LLMProvider):
    """Provider implementation that calls an OpenAI-compatible llama.cpp endpoint."""

    def __init__(
        self,
        config: LlamaCppProviderConfig | None = None,
        session_factory: SessionFactory | None = None,
    ) -> None:
        self._config = config
        self._session_factory = session_factory or requests.Session
        self._session: requests.Session | None = None
        self._endpoint: str | None = None

    def _ensure_ready(self) -> tuple[LlamaCppProviderConfig, requests.Session, str]:
        if self._config is None:
            self._config = LlamaCppProviderConfig.from_env()
        if self._session is None:
            self._session = self._session_factory()
        if self._endpoint is None:
            self._endpoint = self._config.endpoint
        return self._config, self._session, self._endpoint

    def _build_payload(
        self,
        prompt: str,
        config: LlamaCppProviderConfig,
        *,
        system_instructions: str | None = None,
        max_tokens: int | None = None,
        response_format_json: bool = False,
    ) -> dict[str, Any]:
        system = system_instructions if system_instructions is not None else _SYSTEM_INSTRUCTIONS
        payload: dict[str, Any] = {
            "model": config.model,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _request_headers(self, config: LlamaCppProviderConfig) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        return headers

    def _extract_assessment(self, data: Any, *, max_tokens: int | None = None) -> dict[str, Any]:
        payload_snippet = self._payload_snippet(data)
        if not isinstance(data, dict):
            raise ValueError(
                f"llama.cpp response expected an object but got {self._type_name(data)}; "
                f"response snippet: {payload_snippet}"
            )
        choices0_type: str | None = None
        message_type: str | None = None

        def debug_context() -> str:
            parts = [f"response snippet: {payload_snippet}"]
            if choices0_type:
                parts.append(f"choices[0] type: {choices0_type}")
            if message_type:
                parts.append(f"choices[0]['message'] type: {message_type}")
            return "; ".join(parts)

        if not isinstance(data, dict):
            raise ValueError(
                f"llama.cpp response expected an object but got {self._type_name(data)}; {debug_context()}"
            )

        def raise_shape_error(path: str, expected: str, value: Any) -> NoReturn:
            raise ValueError(
                f"llama.cpp response {path} expected {expected} but got {self._type_name(value)}; "
                f"{debug_context()}"
            )

        def extract_text_from_content(node: Any, path: str) -> str | None:
            if node is None:
                return None
            if isinstance(node, str):
                return node
            if isinstance(node, dict):
                nested_path = f"{path}['content']"
                return extract_text_from_content(node.get("content"), nested_path)
            raise_shape_error(path, "a string or nested 'content' object", node)

        choices = data.get("choices")
        if not isinstance(choices, list):
            raise_shape_error("'choices'", "a list", choices)
        if not choices:
            raise ValueError(
                f"llama.cpp response 'choices' expected a non-empty list; {debug_context()}"
            )
        top_choice = choices[0]
        choices0_type = self._type_name(top_choice)
        if not isinstance(top_choice, dict):
            raise_shape_error("'choices[0]'", "a dictionary", top_choice)

        message = top_choice.get("message")
        if message is not None:
            message_type = self._type_name(message)
        if message is not None and not isinstance(message, dict | str):
            raise_shape_error("'choices[0]['message']'", "a dictionary or string", message)

        content: str | None
        if isinstance(message, str):
            content = message
        elif isinstance(message, dict):
            content = extract_text_from_content(
                message.get("content"), "'choices[0]['message']['content']'"
            )
        else:
            content = None

        if content is None:
            text_field = top_choice.get("text")
            if text_field is None:
                raise ValueError(
                    f"llama.cpp response choice lacks textual content; response snippet: {payload_snippet}"
                )
            if not isinstance(text_field, str):
                raise_shape_error("'choices[0]['text']'", "a string", text_field)
            content = text_field

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            # Extract structured output diagnostics before raising
            resp_diags = self._extract_response_diagnostics(data)
            excerpt = content[:500]
            excerpt_snippet = " ".join(excerpt.split()) or excerpt
            if len(content) > 500:
                excerpt_snippet = f"{excerpt_snippet}…"
            # Check if completion was stopped by length cap
            finish_reason = resp_diags.get("finish_reason")
            stopped_by_length = finish_reason == "length" if finish_reason else False
            raise LLMResponseParseError(
                f"llama.cpp response text content is not valid JSON (first 500 chars: {excerpt_snippet}); "
                f"response snippet: {payload_snippet}",
                finish_reason=resp_diags.get("finish_reason"),
                response_content_chars=resp_diags.get("response_content_chars"),
                response_content_prefix=resp_diags.get("response_content_prefix"),
                completion_stopped_by_length=stopped_by_length,
                max_tokens=max_tokens,
            ) from exc
        if not isinstance(parsed, dict):
            raise_shape_error("message JSON", "an object", parsed)
        return cast(dict[str, Any], parsed)

    @staticmethod
    def _base_url_mutually_exclusive_v1(base_url: str) -> bool:
        return base_url.rstrip('/').endswith('/v1')

    @staticmethod
    def _format_http_status(response: Any) -> str | None:
        status_code = getattr(response, "status_code", None)
        if status_code is None:
            return None
        reason = getattr(response, "reason", "") or ""
        reason_text = f" {reason}" if reason else ""
        return f"HTTP {status_code}{reason_text}"

    @staticmethod
    def _response_body_snippet(response: Any, limit: int = 320) -> str | None:
        raw = getattr(response, "text", None)
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        snippet = " ".join(text.split())
        if len(snippet) > limit:
            snippet = snippet[:limit].rstrip()
            snippet = f"{snippet}…"
        return snippet

    @staticmethod
    def _type_name(value: Any) -> str:
        if value is None:
            return "NoneType"
        return type(value).__name__

    @staticmethod
    def _payload_snippet(value: Any, limit: int = 320) -> str:
        try:
            serialized = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            serialized = repr(value)
        snippet = " ".join(serialized.split())
        if len(snippet) > limit:
            snippet = snippet[:limit].rstrip()
            snippet = f"{snippet}…"
        return snippet

    @staticmethod
    def _extract_response_diagnostics(data: Any, max_prefix_len: int = 200) -> dict[str, Any]:
        """Extract structured output diagnostics from LLM response.

        Args:
            data: The parsed JSON response from the LLM
            max_prefix_len: Maximum length for response content prefix

        Returns:
            Dict with finish_reason, content chars, content prefix if available
        """
        diagnostics: dict[str, Any] = {}
        try:
            choices = data.get("choices")
            if isinstance(choices, list) and choices:
                top_choice = choices[0]
                if isinstance(top_choice, dict):
                    # Extract finish_reason
                    finish_reason = top_choice.get("finish_reason")
                    if finish_reason is not None:
                        diagnostics["finish_reason"] = str(finish_reason)
                    # Extract content
                    message = top_choice.get("message")
                    content: str | None = None
                    if isinstance(message, dict):
                        content = message.get("content")
                    elif isinstance(message, str):
                        content = message
                    if content is not None:
                        diagnostics["response_content_chars"] = len(content)
                        if content:
                            prefix = content[:max_prefix_len]
                            diagnostics["response_content_prefix"] = prefix
        except Exception:  # noqa: BLE001
            # Best-effort extraction, don't fail on unexpected response shape
            pass
        return diagnostics

    @classmethod
    def _build_error_message(
        cls,
        config: LlamaCppProviderConfig,
        endpoint: str,
        exc: requests.RequestException,
        response: requests.Response | None,
        timeout_seconds: int,
    ) -> str:
        context: list[str] = [f"Endpoint {endpoint} (LLAMA_CPP_BASE_URL={config.base_url})"]
        if cls._base_url_mutually_exclusive_v1(config.base_url):
            context.append("Base URL already includes '/v1'; provider still appends '/v1/chat/completions'. Remove the trailing '/v1' if you only meant to specify the server root.")
        if response is not None:
            status_text = cls._format_http_status(response)
            if status_text:
                context.append(status_text)
            snippet = cls._response_body_snippet(response)
            if snippet:
                context.append(f"Response snippet: {snippet}")
        else:
            context.append(f"{exc.__class__.__name__}: {exc}")
        context.append(f"timeout={timeout_seconds}s")
        return "llama.cpp request failed: " + "; ".join(context)

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
        response_format_json: bool = False,
    ) -> dict[str, Any]:
        config, session, endpoint = self._ensure_ready()
        request_payload = self._build_payload(prompt, config, system_instructions=system_instructions, max_tokens=max_tokens, response_format_json=response_format_json)
        response: requests.Response | None = None
        timeout_seconds = config.timeout_seconds
        try:
            response = session.post(
                endpoint,
                json=request_payload,
                headers=self._request_headers(config),
                timeout=timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(
                self._build_error_message(config, endpoint, exc, response, timeout_seconds)
            ) from exc
        assert response is not None
        raw = response.json()
        assessment = self._extract_assessment(raw, max_tokens=max_tokens)
        if validate_schema:
            try:
                validated = AssessorAssessment.from_dict(assessment)
            except ValueError as exc:
                snippet = self._payload_snippet(assessment)
                raise ValueError(
                    f"Assessor schema validation failed: {exc}; assessment snippet: {snippet}"
                ) from exc
            return validated.to_dict()
        return assessment


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



def _classify_request_exception(exc: BaseException, exc_name: str) -> tuple[LLMFailureClass, str]:
    """Helper to classify a requests.RequestException or similar."""
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
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN",
    "DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT",
    "LlamaCppProvider",
    "LlamaCppProviderConfig",
    "LLMFailureClass",
    "LLMFailureMetadata",
    "classify_llm_failure",
    "LLMResponseParseError",
]
