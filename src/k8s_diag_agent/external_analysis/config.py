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
class ExternalAnalysisAdapterConfig:
    name: str
    enabled: bool = True
    command: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ExternalAnalysisSettings:
    policy: ExternalAnalysisPolicy = field(default_factory=ExternalAnalysisPolicy)
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
    return ExternalAnalysisSettings(policy=policy, adapters=tuple(configs))
