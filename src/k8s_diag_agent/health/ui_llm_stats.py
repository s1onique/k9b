"""LLM/provider stats and policy serialization for UI consumers.

This module provides high-level builders for LLM stats, policy, and execution
reporting. Core aggregation and activity serialization are delegated to
ui_projection.llm_activity.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from ..external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from ..external_analysis.config import (
    AutoDrilldownPolicy,
    ExternalAnalysisSettings,
)
from .ui_projection.llm_activity import (
    _EPOCH_SENTINEL,
    _SCOPE_CURRENT_RUN,
    _SCOPE_RETAINED_HISTORY,
    _build_historical_llm_stats,
    _build_llm_stats,
    _coerce_optional_str,
    _collect_historical_external_analysis_entries,
    _compute_llm_stats,
    _parse_optional_int,
    _parse_timestamp,
    _percentile_value,
    _serialize_llm_activity,
)

if TYPE_CHECKING:
    from .loop import DrilldownArtifact


# Re-export for backward compatibility
__all__ = [
    # Constants from llm_activity
    "_SCOPE_CURRENT_RUN",
    "_SCOPE_RETAINED_HISTORY",
    "_EPOCH_SENTINEL",
    # Stats functions from llm_activity
    "_build_llm_stats",
    "_build_historical_llm_stats",
    "_collect_historical_external_analysis_entries",
    "_compute_llm_stats",
    "_serialize_llm_activity",
    # Parsing helpers from llm_activity
    "_parse_optional_int",
    "_parse_timestamp",
    "_coerce_optional_str",
    "_percentile_value",
    # Policy/execution (stay in this module)
    "_build_llm_policy",
    "_build_provider_execution",
]


# =============================================================================
# LLM Policy Reporting
# =============================================================================


def _build_llm_policy(
    settings: ExternalAnalysisSettings | None,
    artifacts: Sequence[ExternalAnalysisArtifact],
    drilldown_count: int,
) -> dict[str, object]:
    config = settings or ExternalAnalysisSettings()
    policy = config.auto_drilldown
    auto_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.purpose == ExternalAnalysisPurpose.AUTO_DRILLDOWN
    ]
    used_statuses = {ExternalAnalysisStatus.SUCCESS, ExternalAnalysisStatus.FAILED}
    used_calls = sum(1 for artifact in auto_artifacts if artifact.status in used_statuses)
    successful_calls = sum(1 for artifact in auto_artifacts if artifact.status == ExternalAnalysisStatus.SUCCESS)
    failed_calls = sum(1 for artifact in auto_artifacts if artifact.status == ExternalAnalysisStatus.FAILED)
    skipped_calls = sum(1 for artifact in auto_artifacts if artifact.status == ExternalAnalysisStatus.SKIPPED)
    budget_exhausted: bool | None = None
    if policy.enabled and policy.max_per_run > 0:
        if len(auto_artifacts) >= policy.max_per_run and drilldown_count > len(auto_artifacts):
            budget_exhausted = True
        elif drilldown_count <= len(auto_artifacts):
            budget_exhausted = False
    return {
        "auto_drilldown": {
            "enabled": policy.enabled,
            "provider": policy.provider or "default",
            "maxPerRun": policy.max_per_run,
            "usedThisRun": used_calls,
            "successfulThisRun": successful_calls,
            "failedThisRun": failed_calls,
            "skippedThisRun": skipped_calls,
            "budgetExhausted": budget_exhausted,
        }
    }


# =============================================================================
# Provider Execution Reporting
# =============================================================================


def _build_provider_execution(
    settings: ExternalAnalysisSettings | None,
    artifacts: Sequence[ExternalAnalysisArtifact],
    drilldowns: Sequence[DrilldownArtifact],
    review_config: Mapping[str, object] | None,
) -> dict[str, object]:
    config = settings or ExternalAnalysisSettings()
    auto_policy = config.auto_drilldown
    return {
        "auto_drilldown": _build_auto_drilldown_execution(
            auto_policy, artifacts, len(drilldowns)
        ),
        "review_enrichment": _build_review_enrichment_execution(
            artifacts, review_config
        ),
    }


def _execution_counts_for_purpose(
    artifacts: Sequence[ExternalAnalysisArtifact],
    purpose: ExternalAnalysisPurpose,
) -> tuple[int, int, int]:
    success = 0
    failed = 0
    skipped = 0
    for artifact in artifacts:
        if artifact.purpose != purpose:
            continue
        status = artifact.status
        if status == ExternalAnalysisStatus.SUCCESS:
            success += 1
        elif status == ExternalAnalysisStatus.FAILED:
            failed += 1
        elif status == ExternalAnalysisStatus.SKIPPED:
            skipped += 1
    return success, failed, skipped


def _build_auto_drilldown_execution(
    policy: AutoDrilldownPolicy,
    artifacts: Sequence[ExternalAnalysisArtifact],
    eligible_count: int,
) -> dict[str, object]:
    succeeded, failed, skipped = _execution_counts_for_purpose(
        artifacts, ExternalAnalysisPurpose.AUTO_DRILLDOWN
    )
    attempted = succeeded + failed + skipped
    eligible: int | None = eligible_count if policy.enabled else None
    unattempted: int | None = None
    if eligible is not None and eligible > attempted:
        unattempted = eligible - attempted
    budget_limited: int | None = None
    if (
        eligible is not None
        and policy.max_per_run > 0
        and attempted >= policy.max_per_run
        and eligible > attempted
    ):
        budget_limited = eligible - attempted
    notes_parts: list[str] = []
    if budget_limited:
        notes_parts.append(
            f"Reached max per run ({policy.max_per_run}) before processing {budget_limited} eligible drilldown(s)."
        )
    elif unattempted:
        notes_parts.append(
            f"{unattempted} eligible drilldown(s) were not processed by the provider log."
        )
    notes = " ".join(notes_parts) if notes_parts else None
    return {
        "enabled": policy.enabled,
        "provider": policy.provider or "default",
        "maxPerRun": policy.max_per_run,
        "eligible": eligible,
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "unattempted": unattempted,
        "budgetLimited": budget_limited,
        "notes": notes,
    }


def _extract_review_run_config(run_config: Mapping[str, object] | None) -> tuple[bool | None, str | None]:
    run_enabled: bool | None = None
    run_provider: str | None = None
    if isinstance(run_config, Mapping):
        if "enabled" in run_config:
            run_enabled = bool(run_config.get("enabled"))
        if "provider" in run_config:
            provider_raw = str(run_config.get("provider") or "").strip()
            run_provider = provider_raw or None
    return run_enabled, run_provider


def _build_review_enrichment_execution(
    artifacts: Sequence[ExternalAnalysisArtifact],
    run_config: Mapping[str, object] | None,
) -> dict[str, object]:
    succeeded, failed, skipped = _execution_counts_for_purpose(
        artifacts, ExternalAnalysisPurpose.REVIEW_ENRICHMENT
    )
    attempted = succeeded + failed + skipped
    run_enabled, run_provider = _extract_review_run_config(run_config)
    if run_enabled is None:
        eligible: int | None = None
    elif not run_enabled:
        eligible = 0
    elif run_provider:
        eligible = 1
    else:
        eligible = 0
    unattempted: int | None = None
    if eligible is not None and eligible > attempted:
        unattempted = eligible - attempted
    notes = None
    if unattempted and run_provider:
        notes = (
            f"Run configuration enabled review enrichment for '{run_provider}', but no artifact was recorded."
        )
    elif unattempted:
        notes = "Run configuration enabled review enrichment, but no artifact was recorded."
    return {
        "enabled": run_enabled,
        "eligible": eligible,
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "unattempted": unattempted,
        "budgetLimited": None,
        "notes": notes,
    }
