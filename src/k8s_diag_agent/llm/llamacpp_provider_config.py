"""Configuration for llama.cpp provider."""
from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass

from .openai_compatible_urls import build_chat_completions_url

_logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 120
# Token budgets for thinking/reasoning models (Qwen-style):
# - Auto-drilldown: 3072 tokens accommodates extended reasoning chains
# - Review-enrichment: 4096 tokens for richer multi-field JSON output
DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN = 3072
DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT = 4096

# Canonical and legacy environment variable names for OpenAI-compatible provider
_CANONICAL_ENV_BASE_URL = "K9B_EXTERNAL_ANALYSIS_BASE_URL"
_CANONICAL_ENV_MODEL = "K9B_EXTERNAL_ANALYSIS_MODEL"
_CANONICAL_ENV_API_KEY = "K9B_EXTERNAL_ANALYSIS_API_KEY"
_CANONICAL_ENV_TIMEOUT = "K9B_EXTERNAL_ANALYSIS_TIMEOUT_SECONDS"
_CANONICAL_ENV_MAX_TOKENS_AUTO_DRILLDOWN = "K9B_EXTERNAL_ANALYSIS_MAX_TOKENS_AUTO_DRILLDOWN"
_CANONICAL_ENV_MAX_TOKENS_REVIEW_ENRICHMENT = "K9B_EXTERNAL_ANALYSIS_MAX_TOKENS_REVIEW_ENRICHMENT"
_CANONICAL_ENV_RESPONSE_FORMAT_JSON = "K9B_EXTERNAL_ANALYSIS_RESPONSE_FORMAT_JSON"
_CANONICAL_ENV_TEMPERATURE = "K9B_EXTERNAL_ANALYSIS_TEMPERATURE"
_CANONICAL_ENV_TOP_P = "K9B_EXTERNAL_ANALYSIS_TOP_P"
_CANONICAL_ENV_TOP_K = "K9B_EXTERNAL_ANALYSIS_TOP_K"
_CANONICAL_ENV_REPEAT_PENALTY = "K9B_EXTERNAL_ANALYSIS_REPEAT_PENALTY"
_CANONICAL_ENV_SEED = "K9B_EXTERNAL_ANALYSIS_SEED"
_CANONICAL_ENV_STOP = "K9B_EXTERNAL_ANALYSIS_STOP"
_CANONICAL_ENV_ENABLE_THINKING = "K9B_EXTERNAL_ANALYSIS_ENABLE_THINKING"

_LEGACY_ENV_BASE_URL = "LLAMA_CPP_BASE_URL"
_LEGACY_ENV_MODEL = "LLAMA_CPP_MODEL"
_LEGACY_ENV_API_KEY = "LLAMA_CPP_API_KEY"
_LEGACY_ENV_TIMEOUT = "LLAMA_CPP_TIMEOUT_SECONDS"
_LEGACY_ENV_MAX_TOKENS_AUTO_DRILLDOWN = "LLAMA_CPP_MAX_TOKENS_AUTO_DRILLDOWN"
_LEGACY_ENV_MAX_TOKENS_REVIEW_ENRICHMENT = "LLAMA_CPP_MAX_TOKENS_REVIEW_ENRICHMENT"
_LEGACY_ENV_RESPONSE_FORMAT_JSON = "LLAMA_CPP_RESPONSE_FORMAT_JSON"
_LEGACY_ENV_TEMPERATURE = "LLAMA_CPP_TEMPERATURE"
_LEGACY_ENV_TOP_P = "LLAMA_CPP_TOP_P"
_LEGACY_ENV_TOP_K = "LLAMA_CPP_TOP_K"
_LEGACY_ENV_REPEAT_PENALTY = "LLAMA_CPP_REPEAT_PENALTY"
_LEGACY_ENV_SEED = "LLAMA_CPP_SEED"
_LEGACY_ENV_STOP = "LLAMA_CPP_STOP"
_LEGACY_ENV_ENABLE_THINKING = "LLAMA_CPP_ENABLE_THINKING"

# Track deprecation warnings to emit only once per process
_DEPRECATION_WARNING_LOGGED: set[str] = set()


def _get_env_with_fallback(
    canonical_name: str,
    legacy_name: str,
    source: Mapping[str, str],
) -> tuple[str | None, str | None, bool]:
    """Get environment variable value with canonical/legacy fallback."""
    canonical_value = source.get(canonical_name)
    if canonical_value is not None and str(canonical_value).strip():
        return canonical_value.strip(), canonical_name, False
    legacy_value = source.get(legacy_name)
    if legacy_value is not None and str(legacy_value).strip():
        return legacy_value.strip(), legacy_name, True
    return None, None, False


_SYSTEM_INSTRUCTIONS = (
    "You are a Kubernetes diagnostics assistant."
    " Provide a single JSON object that matches the AssessorAssessment schema exactly."
    " Do not include markdown, XML, or explanatory text outside the JSON payload."
    " Include all required keys (observed_signals, findings, hypotheses, next_evidence_to_collect,"
    " recommended_action, safety_level) and set strings accordingly."
)

_REVIEW_ENRICHMENT_SYSTEM_INSTRUCTIONS = (
    "You are a Kubernetes diagnostics review advisor."
    " CRITICAL: Return ONLY a valid JSON object. Do NOT use markdown fences, XML, or any text outside the JSON."
    " The JSON must contain at minimum a 'summary' field with a non-empty string value."
    " Include these fields: summary (required), triageOrder, topConcerns, evidenceGaps, nextChecks, focusNotes."
    " Each array field must contain non-empty strings. Highlight missing data explicitly in arrays."
    " nextChecks entries MUST be kubectl commands starting with: kubectl describe, kubectl logs, kubectl get, or kubectl top."
    " NEVER include phrases like: validate, confirm, investigate, verify, plan upgrade in nextChecks."
    " NEVER suggest mutations: do not include apply, patch, scale, edit, upgrade, delete, restart, rollout."
    " If Alertmanager data is present, you MAY include alertmanagerEvidenceReferences."
    " alertmanagerEvidenceReferences format: [{\"cluster\": \"<string>\", \"matchedDimensions\": [\"<dim>\"], \"reason\": \"<string>\", \"usedFor\": \"<string>\"}]"
    " usedFor values: EXACTLY one of: top_concern, next_check, summary, triage_order, focus_note."
    " Do NOT use plural forms. Invalid plural usedFor examples include: top_concerns, next_checks, triage_order_items, focus_notes, evidence_gaps."
    " Do NOT derive usedFor from field names."
)


@dataclass(frozen=True)
class LlamaCppProviderConfig:
    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_tokens_auto_drilldown: int = DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN
    max_tokens_review_enrichment: int = DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT
    response_format_json: bool = False
    enable_thinking: bool = False
    temperature: float | None = 0.0
    top_p: float | None = None
    top_k: int | None = None
    repeat_penalty: float | None = None
    seed: int | None = None
    stop: tuple[str, ...] | None = None

    @staticmethod
    def _parse_enable_thinking(value: str | None) -> bool:
        if value is None:
            return False
        trimmed = value.strip().lower()
        if trimmed in ("true", "1", "yes"):
            return True
        if trimmed in ("false", "0", "no", ""):
            return False
        return False

    @property
    def endpoint(self) -> str:
        return build_chat_completions_url(self.base_url)

    @property
    def generation_settings(self) -> dict[str, object]:
        settings: dict[str, object] = {}
        if self.temperature is not None:
            settings["temperature"] = self.temperature
        if self.top_p is not None:
            settings["top_p"] = self.top_p
        if self.top_k is not None:
            settings["top_k"] = self.top_k
        if self.repeat_penalty is not None:
            settings["repeat_penalty"] = self.repeat_penalty
        if self.seed is not None:
            settings["seed"] = self.seed
        if self.stop is not None:
            settings["stop_count"] = len(self.stop)
        settings["enable_thinking"] = self.enable_thinking
        return settings

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> LlamaCppProviderConfig:
        source: Mapping[str, str] = env if env is not None else os.environ
        missing: list[str] = []
        used_legacy: set[str] = set()

        base_url, _, used_legacy_base = _get_env_with_fallback(
            _CANONICAL_ENV_BASE_URL, _LEGACY_ENV_BASE_URL, source
        )
        if not base_url:
            missing.append(_CANONICAL_ENV_BASE_URL)
        elif used_legacy_base:
            used_legacy.add("base_url")

        model, _, used_legacy_model = _get_env_with_fallback(
            _CANONICAL_ENV_MODEL, _LEGACY_ENV_MODEL, source
        )
        if not model:
            missing.append(_CANONICAL_ENV_MODEL)
        elif used_legacy_model:
            used_legacy.add("model")

        if missing:
            raise RuntimeError(
                f"Missing environment variables for OpenAI-compatible provider: {', '.join(missing)}. "
                f"Use K9B_EXTERNAL_ANALYSIS_BASE_URL and K9B_EXTERNAL_ANALYSIS_MODEL (legacy LLAMA_CPP_* vars accepted)."
            )

        assert base_url is not None
        assert model is not None

        if used_legacy and "env_deprecation" not in _DEPRECATION_WARNING_LOGGED:
            _logger.warning(
                "Deprecated LLM provider environment variables used",
                extra={
                    "event": "deprecated-provider-env",
                    "legacy_vars": sorted(used_legacy),
                    "replacement": "K9B_EXTERNAL_ANALYSIS_*",
                },
            )
            _DEPRECATION_WARNING_LOGGED.add("env_deprecation")

        api_key, _, _ = _get_env_with_fallback(
            _CANONICAL_ENV_API_KEY, _LEGACY_ENV_API_KEY, source
        )

        timeout_seconds_raw, _, _ = _get_env_with_fallback(
            _CANONICAL_ENV_TIMEOUT, _LEGACY_ENV_TIMEOUT, source
        )
        timeout_seconds = cls._parse_timeout(timeout_seconds_raw)

        max_tokens_auto_drilldown_raw, _, _ = _get_env_with_fallback(
            _CANONICAL_ENV_MAX_TOKENS_AUTO_DRILLDOWN, _LEGACY_ENV_MAX_TOKENS_AUTO_DRILLDOWN, source
        )
        max_tokens_auto_drilldown = cls._parse_max_tokens(max_tokens_auto_drilldown_raw, DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN)

        max_tokens_review_enrichment_raw, _, _ = _get_env_with_fallback(
            _CANONICAL_ENV_MAX_TOKENS_REVIEW_ENRICHMENT, _LEGACY_ENV_MAX_TOKENS_REVIEW_ENRICHMENT, source
        )
        max_tokens_review_enrichment = cls._parse_max_tokens(max_tokens_review_enrichment_raw, DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT)

        response_format_json_raw, _, _ = _get_env_with_fallback(
            _CANONICAL_ENV_RESPONSE_FORMAT_JSON, _LEGACY_ENV_RESPONSE_FORMAT_JSON, source
        )
        response_format_json = cls._parse_response_format_json(response_format_json_raw)

        temperature_raw, _, _ = _get_env_with_fallback(
            _CANONICAL_ENV_TEMPERATURE, _LEGACY_ENV_TEMPERATURE, source
        )
        temperature = cls._parse_temperature(temperature_raw)

        top_p_raw, _, _ = _get_env_with_fallback(
            _CANONICAL_ENV_TOP_P, _LEGACY_ENV_TOP_P, source
        )
        top_p = cls._parse_top_p(top_p_raw)

        top_k_raw, _, _ = _get_env_with_fallback(
            _CANONICAL_ENV_TOP_K, _LEGACY_ENV_TOP_K, source
        )
        top_k = cls._parse_top_k(top_k_raw)

        repeat_penalty_raw, _, _ = _get_env_with_fallback(
            _CANONICAL_ENV_REPEAT_PENALTY, _LEGACY_ENV_REPEAT_PENALTY, source
        )
        repeat_penalty = cls._parse_repeat_penalty(repeat_penalty_raw)

        seed_raw, _, _ = _get_env_with_fallback(
            _CANONICAL_ENV_SEED, _LEGACY_ENV_SEED, source
        )
        seed = cls._parse_seed(seed_raw)

        stop_raw, _, _ = _get_env_with_fallback(
            _CANONICAL_ENV_STOP, _LEGACY_ENV_STOP, source
        )
        stop = cls._parse_stop(stop_raw)

        enable_thinking_raw, _, _ = _get_env_with_fallback(
            _CANONICAL_ENV_ENABLE_THINKING, _LEGACY_ENV_ENABLE_THINKING, source
        )
        enable_thinking = cls._parse_enable_thinking(enable_thinking_raw)

        return cls(
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_tokens_auto_drilldown=max_tokens_auto_drilldown,
            max_tokens_review_enrichment=max_tokens_review_enrichment,
            response_format_json=response_format_json,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            repeat_penalty=repeat_penalty,
            seed=seed,
            stop=stop,
            enable_thinking=enable_thinking,
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

    @staticmethod
    def _parse_response_format_json(value: str | None) -> bool:
        if value is None:
            return False
        trimmed = value.strip().lower()
        if trimmed in ("true", "1", "yes"):
            return True
        if trimmed in ("false", "0", "no", ""):
            return False
        return False

    @staticmethod
    def _parse_temperature(value: str | None) -> float | None:
        if value is None:
            return 0.0
        trimmed = value.strip()
        if not trimmed:
            return 0.0
        try:
            return float(trimmed)
        except ValueError:
            return 0.0

    @staticmethod
    def _parse_top_p(value: str | None) -> float | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        try:
            parsed = float(trimmed)
            if 0.0 < parsed <= 1.0:
                return parsed
            return None
        except ValueError:
            return None

    @staticmethod
    def _parse_top_k(value: str | None) -> int | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        try:
            parsed = int(trimmed)
            if parsed > 0:
                return parsed
            return None
        except ValueError:
            return None

    @staticmethod
    def _parse_repeat_penalty(value: str | None) -> float | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        try:
            return float(trimmed)
        except ValueError:
            return None

    @staticmethod
    def _parse_seed(value: str | None) -> int | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        try:
            return int(trimmed)
        except ValueError:
            return None

    @staticmethod
    def _parse_stop(value: str | None) -> tuple[str, ...] | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        sequences = [s.strip() for s in trimmed.split(",") if s.strip()]
        return tuple(sequences) if sequences else None


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_MAX_TOKENS_AUTO_DRILLDOWN",
    "DEFAULT_MAX_TOKENS_REVIEW_ENRICHMENT",
    "LlamaCppProviderConfig",
    "_SYSTEM_INSTRUCTIONS",
    "_REVIEW_ENRICHMENT_SYSTEM_INSTRUCTIONS",
    "build_chat_completions_url",
]
