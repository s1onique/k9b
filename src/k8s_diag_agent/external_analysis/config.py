"""Configuration helpers for external analysis adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExternalAnalysisPolicy:
    manual: bool = True
    degraded_health: bool = False
    suspicious_comparison: bool = False


@dataclass(frozen=True)
class AutoDrilldownPolicy:
    enabled: bool = False
    provider: str | None = None
    max_per_run: int = 1


@dataclass(frozen=True)
class ReviewEnrichmentPolicy:
    enabled: bool = False
    provider: str | None = None


@dataclass(frozen=True)
class ExternalAnalysisAdapterConfig:
    name: str
    enabled: bool = True
    command: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ExternalAnalysisSettings:
    policy: ExternalAnalysisPolicy = field(default_factory=ExternalAnalysisPolicy)
    auto_drilldown: AutoDrilldownPolicy = field(default_factory=AutoDrilldownPolicy)
    review_enrichment: ReviewEnrichmentPolicy = field(default_factory=ReviewEnrichmentPolicy)
    adapters: tuple[ExternalAnalysisAdapterConfig, ...] = field(default_factory=tuple)


def parse_external_analysis_settings(raw: Mapping[str, Any] | None) -> ExternalAnalysisSettings:
    if not isinstance(raw, Mapping):
        return ExternalAnalysisSettings()
    policy_raw = raw.get("policy") or {}
    policy = ExternalAnalysisPolicy(
        manual=bool(policy_raw.get("manual", True)),
        degraded_health=bool(policy_raw.get("degraded_health", False)),
        suspicious_comparison=bool(policy_raw.get("suspicious_comparison", False)),
    )
    auto_raw = raw.get("auto_drilldown") or {}
    max_raw = auto_raw.get("max_per_run")
    max_per_run = 1
    if isinstance(max_raw, (int, float)):
        max_per_run = max(1, int(max_raw))
    elif isinstance(max_raw, str):
        try:
            parsed = int(max_raw)
        except ValueError:
            parsed = 1
        max_per_run = max(1, parsed)
    auto_drilldown = AutoDrilldownPolicy(
        enabled=bool(auto_raw.get("enabled", False)),
        provider=str(auto_raw.get("provider")) if auto_raw.get("provider") else None,
        max_per_run=max_per_run,
    )
    review_raw = raw.get("review_enrichment") or {}
    review_enrichment = ReviewEnrichmentPolicy(
        enabled=bool(review_raw.get("enabled", False)),
        provider=str(review_raw.get("provider")) if review_raw.get("provider") else None,
    )
    adapters_raw = raw.get("adapters") or []
    configs: list[ExternalAnalysisAdapterConfig] = []
    if isinstance(adapters_raw, Sequence):
        for entry in adapters_raw:
            if not isinstance(entry, Mapping):
                continue
            name_raw = entry.get("name")
            if not name_raw:
                continue
            name = str(name_raw).strip()
            if not name:
                continue
            enabled = bool(entry.get("enabled", True))
            command_raw = entry.get("command")
            command: tuple[str, ...] | None = None
            if isinstance(command_raw, Sequence):
                candidate = tuple(str(item) for item in command_raw if str(item).strip())
                if candidate:
                    command = candidate
            configs.append(
                ExternalAnalysisAdapterConfig(name=name, enabled=enabled, command=command)
            )
    return ExternalAnalysisSettings(
        policy=policy,
        auto_drilldown=auto_drilldown,
        review_enrichment=review_enrichment,
        adapters=tuple(configs),
    )
