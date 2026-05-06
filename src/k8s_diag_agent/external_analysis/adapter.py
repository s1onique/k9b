"""Adapter interface and registry for external analysis tools."""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from .artifact import ExternalAnalysisArtifact
from .config import ExternalAnalysisAdapterConfig, ExternalAnalysisSettings


class ExternalAnalysisExecutionError(RuntimeError):
    """Base exception for external analysis adapter failures."""
    pass


# Subprocess timeout for external tool execution (120s)
EXTERNAL_ANALYSIS_TIMEOUT_SECONDS = 120


class TimeoutError(Exception):
    """Raised when a request times out."""
    pass


class AuthError(Exception):
    """Raised when authentication fails (401/403)."""
    pass


class InvalidResponseError(Exception):
    """Raised when the response is malformed or invalid."""
    pass


class UpstreamError(Exception):
    """Raised when upstream service returns an error (5xx) or is unreachable."""
    pass


@dataclass(frozen=True)
class ExternalAnalysisRequest:
    run_id: str
    cluster_label: str
    source_artifact: str | None
    metadata: Mapping[str, object] | None = None


class ExternalAnalysisAdapter(ABC):
    name: str

    def __init__(self, command: Sequence[str] | None = None) -> None:
        self._command = tuple(command) if command else None

    @abstractmethod
    def run(self, request: ExternalAnalysisRequest) -> ExternalAnalysisArtifact:
        ...


AdapterBuilder = Callable[[ExternalAnalysisAdapterConfig, ExternalAnalysisSettings], ExternalAnalysisAdapter | None]
_ADAPTER_BUILDERS: dict[str, AdapterBuilder] = {}


def register_external_analysis_adapter(name: str) -> Callable[[AdapterBuilder], AdapterBuilder]:
    def decorator(builder: AdapterBuilder) -> AdapterBuilder:
        _ADAPTER_BUILDERS[name.lower()] = builder
        return builder

    return decorator


def build_external_analysis_adapters(
    configs: Sequence[ExternalAnalysisAdapterConfig],
    settings: ExternalAnalysisSettings | None = None,
) -> dict[str, ExternalAnalysisAdapter]:
    if settings is None:
        settings = ExternalAnalysisSettings()
    adapters: dict[str, ExternalAnalysisAdapter] = {}
    for entry in configs:
        if not entry.enabled:
            continue
        builder = _ADAPTER_BUILDERS.get(entry.name.lower())
        if not builder:
            continue
        adapter = builder(entry, settings)
        if adapter:
            adapters[adapter.name] = adapter
    return adapters


def _run_subprocess(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=True,
            timeout=EXTERNAL_ANALYSIS_TIMEOUT_SECONDS,
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired as exc:
        # Include only safe truncated command summary (first element only)
        # Do not leak full command args which may contain sensitive data
        cmd_summary = command[0] if command else "unknown"
        raise ExternalAnalysisExecutionError(
            f"Command {cmd_summary} timed out after "
            f"{EXTERNAL_ANALYSIS_TIMEOUT_SECONDS}s. External tool may be unresponsive.",
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else exc.stdout.strip()
        # Include only safe command summary
        cmd_summary = command[0] if command else "unknown"
        raise ExternalAnalysisExecutionError(
            f"Command {cmd_summary} exited {exc.returncode}: {stderr or exc}",
        )
    except FileNotFoundError as exc:
        raise ExternalAnalysisExecutionError(f"Command not found: {exc}")
