"""View models for LLM policy and provider execution (UI layer).

This module contains LLM policy and provider execution view models extracted from model.py.
It exists to enable incremental modularization without changing behavior.

Moved symbols:
- LLMPolicyView
- AutoDrilldownPolicyView
- ProviderExecutionBranchView
- ProviderExecutionView
- _build_llm_policy_view
- _build_auto_drilldown_policy_view
- _build_provider_execution_view
- _build_execution_branch_view
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .model_primitives import (
    _coerce_int,
    _coerce_optional_bool,
    _coerce_optional_int,
    _coerce_optional_str,
    _coerce_str,
)


@dataclass(frozen=True)
class AutoDrilldownPolicyView:
    """View model for auto-drilldown policy configuration and runtime state."""
    enabled: bool
    provider: str
    max_per_run: int
    used_this_run: int
    successful_this_run: int
    failed_this_run: int
    skipped_this_run: int
    budget_exhausted: bool | None


@dataclass(frozen=True)
class LLMPolicyView:
    """View model for LLM policy configuration and runtime state."""
    auto_drilldown: AutoDrilldownPolicyView | None


@dataclass(frozen=True)
class ProviderExecutionBranchView:
    """View model for a single provider execution branch (policy + runtime stats)."""
    enabled: bool | None
    eligible: int | None
    provider: str | None
    max_per_run: int | None
    attempted: int
    succeeded: int
    failed: int
    skipped: int
    unattempted: int | None
    budget_limited: int | None
    notes: str | None


@dataclass(frozen=True)
class ProviderExecutionView:
    """View model for provider execution across all enabled branches."""
    auto_drilldown: ProviderExecutionBranchView | None
    review_enrichment: ProviderExecutionBranchView | None


def _build_llm_policy_view(raw: object | None) -> LLMPolicyView | None:
    """Build LLMPolicyView from raw JSON data."""
    if not isinstance(raw, Mapping):
        return None
    return LLMPolicyView(auto_drilldown=_build_auto_drilldown_policy_view(raw.get("auto_drilldown")))


def _build_auto_drilldown_policy_view(raw: object | None) -> AutoDrilldownPolicyView | None:
    """Build AutoDrilldownPolicyView from raw JSON data."""
    if not isinstance(raw, Mapping):
        return None
    return AutoDrilldownPolicyView(
        enabled=bool(raw.get("enabled")),
        provider=_coerce_str(raw.get("provider")),
        max_per_run=_coerce_int(raw.get("maxPerRun")),
        used_this_run=_coerce_int(raw.get("usedThisRun")),
        successful_this_run=_coerce_int(raw.get("successfulThisRun")),
        failed_this_run=_coerce_int(raw.get("failedThisRun")),
        skipped_this_run=_coerce_int(raw.get("skippedThisRun")),
        budget_exhausted=_coerce_optional_bool(raw.get("budgetExhausted")),
    )


def _build_provider_execution_view(raw: object | None) -> ProviderExecutionView | None:
    """Build ProviderExecutionView from raw JSON data."""
    if not isinstance(raw, Mapping):
        return None
    return ProviderExecutionView(
        auto_drilldown=_build_execution_branch_view(raw.get("auto_drilldown")),
        review_enrichment=_build_execution_branch_view(raw.get("review_enrichment")),
    )


def _build_execution_branch_view(raw: object | None) -> ProviderExecutionBranchView | None:
    """Build ProviderExecutionBranchView from raw JSON data."""
    if not isinstance(raw, Mapping):
        return None
    return ProviderExecutionBranchView(
        enabled=_coerce_optional_bool(raw.get("enabled")),
        eligible=_coerce_optional_int(raw.get("eligible")),
        provider=_coerce_optional_str(raw.get("provider")),
        max_per_run=_coerce_optional_int(raw.get("maxPerRun")),
        attempted=_coerce_int(raw.get("attempted")),
        succeeded=_coerce_int(raw.get("succeeded")),
        failed=_coerce_int(raw.get("failed")),
        skipped=_coerce_int(raw.get("skipped")),
        unattempted=_coerce_optional_int(raw.get("unattempted")),
        budget_limited=_coerce_optional_int(raw.get("budgetLimited")),
        notes=_coerce_optional_str(raw.get("notes")),
    )
