"""llama.cpp provider that speaks the OpenAI-compatible API."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

import requests

from .assessor_schema import AssessorAssessment
from .base import LLMProvider

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


@dataclass(frozen=True)
class LlamaCppProviderConfig:
    base_url: str
    api_key: str
    model: str

    @property
    def endpoint(self) -> str:
        base = self.base_url.rstrip('/')
        return f"{base}/v1/chat/completions"

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "LlamaCppProviderConfig":
        source = env or os.environ
        missing = []
        values: Dict[str, str] = {}
        for key in ("LLAMA_CPP_BASE_URL", "LLAMA_CPP_API_KEY", "LLAMA_CPP_MODEL"):
            raw = source.get(key)
            if not raw or not raw.strip():
                missing.append(key)
                continue
            values[key] = raw.strip()
        if missing:
            raise RuntimeError(f"Missing environment variables for llamacpp provider: {', '.join(missing)}")
        return cls(
            base_url=values["LLAMA_CPP_BASE_URL"],
            api_key=values["LLAMA_CPP_API_KEY"],
            model=values["LLAMA_CPP_MODEL"],
        )


class LlamaCppProvider(LLMProvider):
    """Provider implementation that calls an OpenAI-compatible llama.cpp endpoint."""

    def __init__(
        self,
        config: Optional[LlamaCppProviderConfig] = None,
        session_factory: Optional[SessionFactory] = None,
    ) -> None:
        self._config = config
        self._session_factory = session_factory or requests.Session
        self._session: Optional[requests.Session] = None
        self._endpoint: Optional[str] = None

    def _ensure_ready(self) -> tuple[LlamaCppProviderConfig, requests.Session, str]:
        if self._config is None:
            self._config = LlamaCppProviderConfig.from_env()
        if self._session is None:
            self._session = self._session_factory()
        if self._endpoint is None:
            self._endpoint = self._config.endpoint
        return self._config, self._session, self._endpoint

    def _build_payload(self, prompt: str, config: LlamaCppProviderConfig) -> Dict[str, Any]:
        return {
            "model": config.model,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": prompt},
            ],
        }

    def _request_headers(self, config: LlamaCppProviderConfig) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        }

    def _extract_assessment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("llama.cpp response missing choices")
        top = choices[0]
        message = top.get("message") or {}
        content = message.get("content")
        if isinstance(content, dict):
            # some servers wrap the text content inside an object
            content = content.get("content")
        if not isinstance(content, str):
            raise ValueError("llama.cpp response message lacks textual content")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("llama.cpp response did not contain valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("llama.cpp response JSON must be an object")
        return parsed

    def assess(self, prompt: str, payload: "LLMAssessmentInput") -> Dict[str, Any]:
        config, session, endpoint = self._ensure_ready()
        request_payload = self._build_payload(prompt, config)
        try:
            response = session.post(
                endpoint, json=request_payload, headers=self._request_headers(config), timeout=30
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError("llama.cpp request failed") from exc
        raw = response.json()
        assessment = self._extract_assessment(raw)
        validated = AssessorAssessment.from_dict(assessment)
        return validated.to_dict()


__all__ = ["LlamaCppProvider", "LlamaCppProviderConfig"]
