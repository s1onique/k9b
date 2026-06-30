"""Configuration and CLI-mode run helpers for OpenAI-compatible adapter.

This module extracts config initialization and CLI-mode run logic from
openai_compatible_adapter.py.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

from ..llm.openai_compatible_provider import OpenAICompatibleProvider, OpenAICompatibleProviderConfig
from .adapter import ExternalAnalysisExecutionError, _run_subprocess
from .artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus

if TYPE_CHECKING:
    from .adapter import ExternalAnalysisRequest


# Default command for CLI-based llamacpp binary execution
DEFAULT_COMMAND = ("llamacpp", "analysis")


def init_http_provider(
    command: Sequence[str] | None, http_only: bool
) -> tuple[bool, OpenAICompatibleProvider | None, Exception | None]:
    """Initialize HTTP provider and track config state.

    Returns (use_http, http_provider, config_error) tuple.
    When command is None and http_only is True, always attempts HTTP config.
    """
    http_config: OpenAICompatibleProviderConfig | None = None
    http_intent = False
    config_error: Exception | None = None

    if http_only or command is None:
        try:
            http_config = OpenAICompatibleProviderConfig.from_env()
            http_intent = True
        except RuntimeError as exc:
            config_error = exc
            http_intent = True
        except (ValueError, TypeError) as exc:
            config_error = exc
            http_intent = True

        if http_intent:
            provider = OpenAICompatibleProvider(config=http_config) if http_config else None
            return True, provider, config_error

    return False, None, None


def run_cli(
    tool_name: str,
    command: Sequence[str] | None,
    request: ExternalAnalysisRequest,
) -> ExternalAnalysisArtifact:
    """Run llamacpp in CLI subprocess mode.

    Used when HTTP provider is not available and explicit command is given.
    Returns an ExternalAnalysisArtifact with SUCCESS or FAILED status.
    """
    if not command:
        return ExternalAnalysisArtifact(
            tool_name=tool_name,
            run_id=request.run_id,
            cluster_label=request.cluster_label,
            source_artifact=request.source_artifact,
            summary="Adapter is not configured",
            status=ExternalAnalysisStatus.SKIPPED,
            provider=tool_name,
            skip_reason="No command configured and HTTP provider not available",
        )

    invocation = list(command)
    if request.source_artifact:
        invocation.append(request.source_artifact)
    else:
        invocation.extend(["--cluster", request.cluster_label])

    start = time.perf_counter()
    try:
        raw_output = _run_subprocess(invocation)
        duration_ms = int((time.perf_counter() - start) * 1000)
        summary = raw_output.splitlines()[0] if raw_output else "analysis completed"
        return ExternalAnalysisArtifact(
            tool_name=tool_name,
            run_id=request.run_id,
            cluster_label=request.cluster_label,
            source_artifact=request.source_artifact,
            summary=summary,
            findings=(),
            suggested_next_checks=(),
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output=raw_output,
            provider=tool_name,
            duration_ms=duration_ms,
        )
    except ExternalAnalysisExecutionError as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return ExternalAnalysisArtifact(
            tool_name=tool_name,
            run_id=request.run_id,
            cluster_label=request.cluster_label,
            source_artifact=request.source_artifact,
            summary=str(exc),
            findings=(),
            suggested_next_checks=(),
            status=ExternalAnalysisStatus.FAILED,
            raw_output=str(exc),
            provider=tool_name,
            duration_ms=duration_ms,
        )
