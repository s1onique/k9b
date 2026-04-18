"""Public surface for external analysis adapters and helpers."""

from __future__ import annotations

# Import adapters to ensure they register themselves.
from . import (
    alertmanager_adapter,  # noqa: F401
    k8sgpt_adapter,  # noqa: F401
    llamacpp_adapter,  # noqa: F401
)
from .adapter import (
    ExternalAnalysisAdapter,
    ExternalAnalysisExecutionError,
    ExternalAnalysisRequest,
    build_external_analysis_adapters,
    register_external_analysis_adapter,
)
from .alertmanager_artifact import (
    alertmanager_artifacts_exist,
    alertmanager_sources_exist,
    read_alertmanager_compact,
    read_alertmanager_snapshot,
    read_alertmanager_sources,
    write_alertmanager_artifacts,
    write_alertmanager_compact,
    write_alertmanager_snapshot,
    write_alertmanager_sources,
)
from .alertmanager_config import (
    AlertmanagerAuth,
    AlertmanagerConfig,
    parse_alertmanager_auth,
    parse_alertmanager_config,
)
from .alertmanager_snapshot import (
    AlertmanagerCompact,
    AlertmanagerSnapshot,
    AlertmanagerStatus,
    create_error_snapshot,
    normalize_alertmanager_payload,
    snapshot_to_compact,
)
from .alertmanager_source_actions import (
    AlertmanagerSourceOverrides,
    SourceAction,
    SourceOverride,
    merge_source_overrides,
    read_source_overrides,
    source_overrides_exist,
    write_source_overrides,
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
    # Alertmanager integration
    "AlertmanagerAuth",
    "AlertmanagerConfig",
    "AlertmanagerStatus",
    "AlertmanagerSnapshot",
    "AlertmanagerCompact",
    "parse_alertmanager_config",
    "parse_alertmanager_auth",
    "normalize_alertmanager_payload",
    "snapshot_to_compact",
    "create_error_snapshot",
    "write_alertmanager_snapshot",
    "write_alertmanager_compact",
    "write_alertmanager_artifacts",
    "read_alertmanager_snapshot",
    "read_alertmanager_compact",
    "alertmanager_artifacts_exist",
    # Alertmanager source management
    "AlertmanagerSourceOverrides",
    "SourceAction",
    "SourceOverride",
    "merge_source_overrides",
    "read_source_overrides",
    "source_overrides_exist",
    "write_source_overrides",
    "alertmanager_sources_exist",
]
