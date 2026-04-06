"""Public surface for external analysis adapters and helpers."""

from __future__ import annotations

# Import adapters to ensure they register themselves.
from . import k8sgpt_adapter  # noqa: F401
from .adapter import (
    ExternalAnalysisAdapter,
    ExternalAnalysisExecutionError,
    ExternalAnalysisRequest,
    build_external_analysis_adapters,
    register_external_analysis_adapter,
)
from .artifact import ExternalAnalysisArtifact, ExternalAnalysisStatus, write_external_analysis_artifact
from .config import ExternalAnalysisAdapterConfig, ExternalAnalysisPolicy, ExternalAnalysisSettings, parse_external_analysis_settings

__all__ = [
    "ExternalAnalysisAdapter",
    "ExternalAnalysisArtifact",
    "ExternalAnalysisExecutionError",
    "ExternalAnalysisRequest",
    "ExternalAnalysisStatus",
    "ExternalAnalysisSettings",
    "ExternalAnalysisPolicy",
    "ExternalAnalysisAdapterConfig",
    "build_external_analysis_adapters",
    "parse_external_analysis_settings",
    "register_external_analysis_adapter",
    "write_external_analysis_artifact",
]
