"""TypedDict payload definitions for runs-list API responses.

This module contains pure data contracts (TypedDict definitions) for runs
management UI responses, including the runs list view and execution summary
information.

Ownership:
    - All TypedDict payload classes defined here represent API response contracts.
    - JSON key names, optional vs required fields, and field types are frozen.
    - Serialization logic lives in api_runs_payloads.py and related modules.

Extraction rationale:
    - Runs-list contracts are self-contained with minimal dependencies.
    - Extracting them first establishes the runs-list contract boundary.
    - Keeping runs contracts in a dedicated module makes it easier to audit
      runs-list API contracts without filtering through unrelated payloads.
"""

from __future__ import annotations

from typing import Literal, TypedDict

__all__ = [
    "BatchExecutionSummary",
    "RunsListEntry",
    "RunsListPayload",
    "RunsListTimings",
]


class BatchExecutionSummary(TypedDict):
    """Execution summary for a run's batch execution state.

    Provides sufficient information for Recent Runs Execute button eligibility
    without requiring full execution artifact scanning.

    Contract:
    - totalCandidates: total number of next-check plan candidates
    - executableCandidates: candidates eligible for batch execution (safe, approved, etc.)
    - executedCandidates: candidates with execution artifacts (success, failed, or validation-failure)
    - failedCandidates: executed candidates with failure status
    - pendingExecutableCandidates: executable candidates without execution artifacts
    - batchExecutionState: canonical state for UI eligibility derivation
      - "no-candidates": no candidates in plan
      - "not-started": has pending executable candidates, none executed yet
      - "partially-executed": some candidates executed, some pending
      - "fully-executed": all executable candidates have execution artifacts
    """

    totalCandidates: int
    executableCandidates: int
    executedCandidates: int
    failedCandidates: int
    pendingExecutableCandidates: int
    batchExecutionState: Literal["no-candidates", "not-started", "partially-executed", "fully-executed"]


class RunsListEntry(TypedDict):
    """Payload for a single entry in the runs list."""

    runId: str
    runLabel: str
    timestamp: str
    clusterCount: int
    triaged: bool
    executionCount: int
    reviewedCount: int
    reviewStatus: str
    reviewDownloadPath: str | None
    # Batch execution support for Recent runs
    # When batchEligibility is "unknown", batchExecutable/batchEligibleCount are not computed
    # (deferred for performance on initial load)
    batchEligibility: Literal["computed", "unknown"]
    batchExecutable: bool
    batchEligibleCount: int
    # Execution summary for button eligibility derivation
    # Present when batchEligibility is "computed", None otherwise
    executionSummary: BatchExecutionSummary | None


class RunsListPayload(TypedDict):
    """Payload for the runs list response."""

    runs: list[RunsListEntry]
    totalCount: int  # Total discovered runs (not just returned)
    returnedCount: int  # Number of runs in returned list
    hasMore: bool  # True if there are more runs beyond returned list
    # Indicates whether execution counts (executionCount, reviewedCount) are complete.
    # When False (fast path), counts may be 0/unknown because expensive artifact
    # derivation was skipped. UI should render "Execution status not loaded" instead
    # of "No executions" when this flag is False.
    executionCountsComplete: bool


class RunsListTimings(TypedDict, total=False):
    """Timing metrics from build_runs_list()."""

    # Stage 1a: include_status metrics (bounded status/review/execution projection)
    status_lookup_strategy: str  # "skipped_fast_path" | "window_glob"
    status_run_prefixes_queried: int
    status_files_found: int
    status_lookup_ms: float
    # Stage 1: reviews discovery
    reviews_glob_ms: float
    reviews_parsed: int
    execution_artifacts_glob_ms: float
    execution_artifacts_scanned: int
    execution_count_derivation_ms: float
    execution_count_derivation_matches: int
    # Stage 2b execution file metrics (window-driven lookup optimization)
    execution_lookup_strategy: str  # "window_glob" | "global_scan"
    execution_run_prefixes_queried: int
    execution_files_found_total: int
    execution_files_considered: int
    execution_files_parsed: int
    execution_files_skipped_outside_window: int
    execution_lookup_ms: float
    # Stage 1 sub-stages (breakdown of reviews_glob_ms)
    reviews_glob_only_ms: float
    reviews_files_found: int
    reviews_parse_ms: float
    # Fast path telemetry for ijson streaming
    review_fast_path_attempted: int
    review_fast_path_succeeded: int
    review_fast_path_fallbacks: int
    review_fast_path_failure_json: int
    review_fast_path_failure_missing_field: int
    review_fast_path_failure_other: int
    review_fast_path_other: int  # Non-failure other count for telemetry restoration
    # Stage 2 sub-stages (breakdown of execution_artifacts_glob_ms)
    execution_glob_only_ms: float
    execution_parse_ms: float
    review_artifact_prescan_ms: float
    review_download_path_checks_ms: float
    review_download_paths_found: int
    batch_eligibility_prescan_ms: float
    # Stage 3b sub-stages (breakdown of batch_eligibility_prescan_ms)
    batch_plan_glob_ms: float
    batch_plan_parse_ms: float
    batch_plan_files_found: int
    batch_exec_glob_ms: float
    batch_exec_parse_ms: float
    batch_exec_files_found: int
    batch_run_id_matching_ms: float
    batch_cache_construction_ms: float
    batch_eligible_runs: int
    # Row assembly sub-stages (detailed breakdown of row_assembly_ms)
    review_status_row_ms: float
    review_download_path_row_ms: float
    batch_eligibility_row_ms: float
    artifact_lookup_row_ms: float
    timestamp_normalization_row_ms: float
    label_normalization_row_ms: float
    per_row_fs_checks_ms: float  # Should be ~0 if precomputed properly
    row_assembly_ms: float
    rows_built: int
    rows_considered: int  # Total runs discovered before limit
    rows_returned: int  # Runs actually returned after limit
    sort_ms: float
    batch_eligibility_runs_computed: int  # How many runs had batch eligibility computed
    # Per-row filesystem call counters (prove no per-row FS work)
    path_exists_calls: int
    stat_calls: int
    diagnostic_pack_path_checks: int
    run_scoped_review_path_checks: int
    per_run_glob_calls: int
    per_run_directory_list_calls: int
    # Super fast path optimization markers
    path_strategy: str  # "super_fast_path" when super fast path is used
    total_duration_ms: float  # Total elapsed time
    # Index batch eligibility cache freshness diagnostics
    fallback_reason: str
    index_rejected_reason: str
    index_version: int
    entries_checked: int
    entries_with_fields: int
    has_runs_list: bool
    has_total_count: bool
    cache_freshness_source: str
    cache_freshness_path: str
    # Stale execution indices detection (index freshness fallback)
    index_stale_execution_indices: bool  # True when external-analysis dir is fresher than ui-index.json
    index_execution_indices_recomputed: bool  # True when execution indices were recomputed from filesystem
    index_stale_by_generated_at: bool  # True when execution artifact mtime > generated_at (primary detection)
