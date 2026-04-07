"""K8sGPT adapter implementation."""

from __future__ import annotations

import time
from collections.abc import Sequence

from .adapter import (
    ExternalAnalysisAdapter,
    ExternalAnalysisExecutionError,
    ExternalAnalysisRequest,
    _run_subprocess,
    register_external_analysis_adapter,
)
from .artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus
from .config import ExternalAnalysisAdapterConfig


class K8sGptAdapter(ExternalAnalysisAdapter):
    name = "k8sgpt"

    def __init__(self, command: Sequence[str] | None = None) -> None:
        default_command = ("k8sgpt", "analysis")
        super().__init__(command=tuple(command) if command else default_command)

    def run(self, request: ExternalAnalysisRequest) -> ExternalAnalysisArtifact:
        if not self._command:
            artifact = ExternalAnalysisArtifact(
                tool_name=self.name,
                run_id=request.run_id,
                cluster_label=request.cluster_label,
                source_artifact=request.source_artifact,
                summary="Adapter is not configured",
                status=ExternalAnalysisStatus.SKIPPED,
                provider=self.name,
            )
            return artifact

        invocation = list(self._command)
        if request.source_artifact:
            invocation.append(request.source_artifact)
        else:
            invocation.extend(["--cluster", request.cluster_label])

        start = time.perf_counter()
        try:
            raw_output = _run_subprocess(invocation)
            duration_ms = int((time.perf_counter() - start) * 1000)
            summary = raw_output.splitlines()[0] if raw_output else "analysis completed"
            artifact = ExternalAnalysisArtifact(
                tool_name=self.name,
                run_id=request.run_id,
                cluster_label=request.cluster_label,
                source_artifact=request.source_artifact,
                summary=summary,
                findings=(),
                suggested_next_checks=(),
                status=ExternalAnalysisStatus.SUCCESS,
                raw_output=raw_output,
                provider=self.name,
                duration_ms=duration_ms,
            )
            return artifact
        except ExternalAnalysisExecutionError as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            artifact = ExternalAnalysisArtifact(
                tool_name=self.name,
                run_id=request.run_id,
                cluster_label=request.cluster_label,
                source_artifact=request.source_artifact,
                summary=str(exc),
                findings=(),
                suggested_next_checks=(),
                status=ExternalAnalysisStatus.FAILED,
                raw_output=str(exc),
                provider=self.name,
                duration_ms=duration_ms,
            )
            return artifact


@register_external_analysis_adapter("k8sgpt")
def _build_k8sgpt_adapter(config: ExternalAnalysisAdapterConfig) -> ExternalAnalysisAdapter:
    return K8sGptAdapter(command=config.command)
