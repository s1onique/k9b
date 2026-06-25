"""Fake small-provider adapter for ACT-local smoke testing.

This module provides a fake external-analysis adapter that:
- Registers via @register_external_analysis_adapter("fake_small_provider")
- Tracks whether run() was invoked
- Returns bounded, safe output via ExternalAnalysisArtifact
- Never reads live Kubernetes or runs subprocesses
- Emits upload-safe proof artifacts

Used for ACT-local verification of the non-incident "small provider" path.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .adapter import ExternalAnalysisAdapter, ExternalAnalysisRequest, register_external_analysis_adapter
from .artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus
from .llamacpp_adapter import ExternalAnalysisPreflightResult

if TYPE_CHECKING:
    pass


@dataclass
class FakeSmallProviderState:
    """State tracker for fake small provider."""
    configured: bool = False
    base_url_present: bool = False
    model_present: bool = False
    api_key_present: bool = False
    invocations: list[dict[str, Any]] = field(default_factory=list)
    kubernetes_fallback_attempted: bool = False


# Global state for tracking (process-safe for single invocation)
_state = FakeSmallProviderState()


def reset_fake_provider_state() -> None:
    """Reset global state before each test."""
    global _state
    _state = FakeSmallProviderState()


def get_fake_provider_state() -> FakeSmallProviderState:
    """Get current provider state."""
    return _state


class FakeSmallProviderAdapter(ExternalAnalysisAdapter):
    """Fake external-analysis adapter for ACT-local testing.
    
    Mimics the ExternalAnalysisAdapter interface and:
    - Never makes HTTP calls
    - Never runs kubectl or other subprocesses
    - Tracks all invocations
    - Returns bounded, safe JSON via ExternalAnalysisArtifact
    """
    name = "fake_small_provider"

    def __init__(self, config: Any = None, settings: Any = None) -> None:
        self._config = config
        self._settings = settings
        
        # Read from same env-var config path as production llamacpp adapter
        try:
            from ..llm.llamacpp_provider_config import LlamaCppProviderConfig
            llm_config = LlamaCppProviderConfig.from_env()
            _state.configured = bool(llm_config.base_url and llm_config.model)
            _state.base_url_present = bool(llm_config.base_url)
            _state.model_present = bool(llm_config.model)
            _state.api_key_present = bool(llm_config.api_key)
        except RuntimeError:
            # Config not available (missing required env vars)
            _state.configured = False
            _state.base_url_present = False
            _state.model_present = False
            _state.api_key_present = False

    def preflight_check(self, provider_requested: str | None = None) -> ExternalAnalysisPreflightResult:
        """Return success preflight."""
        return ExternalAnalysisPreflightResult(
            ok=True,
            provider_requested=provider_requested or self.name,
            provider_normalized=self.name,
        )

    def run(self, request: ExternalAnalysisRequest) -> ExternalAnalysisArtifact:
        """Generate fake completion and track invocation."""
        global _state
        start = time.perf_counter()
        
        payload = {
            "summary": "ACT-local smoke test: fake provider invoked successfully",
            "status": "success",
            "provider": self.name,
            "invocation_count": len(_state.invocations) + 1,
            "findings": [{"id": "finding-1", "description": "Fake finding for smoke testing", "confidence": "high"}],
            "next_checks": ["kubectl get pods -n default", "kubectl describe node"],
            "triage_order": ["cluster-a", "cluster-b"],
            "top_concerns": ["Test concern"],
            "evidence_gaps": [],
            "focus_notes": ["This is a fake response for ACT-local testing"],
        }
        
        duration_ms = int((time.perf_counter() - start) * 1000)
        _state.invocations.append({
            "run_id": request.run_id,
            "cluster_label": request.cluster_label,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        
        return ExternalAnalysisArtifact(
            tool_name=self.name,
            run_id=request.run_id,
            cluster_label=request.cluster_label,
            source_artifact=request.source_artifact,
            summary=str(payload["summary"]),
            findings=(),
            suggested_next_checks=(),
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output=json.dumps(payload),
            provider=self.name,
            duration_ms=duration_ms,
            payload=payload,
        )


def _build_fake_adapter(config: Any, settings: Any = None) -> FakeSmallProviderAdapter:
    """Build function registered via @register_external_analysis_adapter."""
    return FakeSmallProviderAdapter(config=config, settings=settings)


# Register the fake adapter
register_external_analysis_adapter("fake_small_provider")(_build_fake_adapter)


__all__ = [
    "FakeSmallProviderAdapter",
    "FakeSmallProviderState",
    "get_fake_provider_state",
    "reset_fake_provider_state",
]
