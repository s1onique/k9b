"""llama.cpp provider that speaks the OpenAI-compatible API."""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NoReturn, cast

import requests

from .assessor_schema import AssessorAssessment
from .base import LLMProvider

DEFAULT_TIMEOUT_SECONDS = 90

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
        return cls(
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
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
    ) -> dict[str, Any]:
        system = system_instructions if system_instructions is not None else _SYSTEM_INSTRUCTIONS
        return {
            "model": config.model,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }

    def _request_headers(self, config: LlamaCppProviderConfig) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        return headers

    def _extract_assessment(self, data: Any) -> dict[str, Any]:
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
            excerpt = content[:500]
            excerpt_snippet = " ".join(excerpt.split()) or excerpt
            if len(content) > 500:
                excerpt_snippet = f"{excerpt_snippet}…"
            raise ValueError(
                f"llama.cpp response text content is not valid JSON (first 500 chars: {excerpt_snippet}); "
                f"response snippet: {payload_snippet}"
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

    def assess(
        self,
        prompt: str,
        payload: LLMAssessmentInput,
        *,
        validate_schema: bool = True,
        system_instructions: str | None = None,
    ) -> dict[str, Any]:
        config, session, endpoint = self._ensure_ready()
        request_payload = self._build_payload(prompt, config, system_instructions=system_instructions)
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
        assessment = self._extract_assessment(raw)
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


__all__ = ["LlamaCppProvider", "LlamaCppProviderConfig"]
