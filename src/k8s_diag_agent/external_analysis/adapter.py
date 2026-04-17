"""Adapter interface and registry for external analysis tools."""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from .artifact import ExternalAnalysisArtifact
from .config import ExternalAnalysisAdapterConfig, ExternalAnalysisSettings


class ExternalAnalysisExecutionError(RuntimeError):
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
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else exc.stdout.strip()
        raise ExternalAnalysisExecutionError(
            f"Command {command[0]} exited {exc.returncode}: {stderr or exc}",
        )
    except FileNotFoundError as exc:
        raise ExternalAnalysisExecutionError(f"Command not found: {exc}")
