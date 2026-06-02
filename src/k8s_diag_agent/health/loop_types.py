"""Shared type definitions for health loop modules.

This module provides shared type definitions that can be imported by
extracted helper modules without creating circular import cycles.

Types are defined here to enable clean module boundaries while maintaining
type safety. The dataclasses here can be imported by helper modules without
needing to import loop.py.

No runner logic - this is a pure types module with no HealthLoopRunner dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .image_pull_secret import ImagePullSecretInsight
from .loop_history import HealthAssessmentResult

if TYPE_CHECKING:
    from ..collect.cluster_snapshot import ClusterSnapshot
    from .baseline import BaselinePolicy


@dataclass(frozen=True)
class HealthTarget:
    """Target cluster configuration for health assessment.

    This dataclass is shared across loop.py, loop_runner_assessments.py,
    loop_runner_drilldowns.py, and loop_health_assessment.py.
    """

    context: str
    label: str
    monitor_health: bool
    watched_helm_releases: tuple[str, ...]
    watched_crd_families: tuple[str, ...]
    cluster_class: str | None = None
    cluster_role: str | None = None
    baseline_cohort: str | None = None
    baseline_policy_path: str | None = None


@dataclass
class HealthSnapshotRecord:
    """Health snapshot record combining target, snapshot, and assessment data.

    This dataclass is shared across loop.py, loop_runner_drilldowns.py,
    and loop_drilldown_helpers.py.
    """

    target: HealthTarget
    snapshot: ClusterSnapshot  # ClusterSnapshot from collect module
    path: Path
    baseline_policy: BaselinePolicy  # BaselinePolicy from baseline module
    baseline_policy_path: str | None = None
    assessment: HealthAssessmentResult | None = None
    pattern_reasons: tuple[str, ...] = field(default_factory=tuple)
    pattern_metadata: dict[str, tuple[str, ...]] = field(default_factory=dict)
    image_pull_secret_insight: ImagePullSecretInsight | None = None

    def refs(self) -> tuple[str, str]:
        from .utils import normalize_ref

        return (normalize_ref(self.target.context), normalize_ref(self.target.label))
