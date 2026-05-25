#!/usr/bin/env python3
"""Check files for LLM-friendly size limits.

This script enforces file size limits to keep code reviewable for humans and
LLM agents. Large monolithic files are design debt.

Usage:
    python scripts/check_llm_friendly_files.py              # full repo check
    python scripts/check_llm_friendly_files.py --changed-only  # git-changed files only
    python scripts/check_llm_friendly_files.py --warn-lines 300 --max-lines 500

Thresholds:
    - Warn: > 300 lines (configurable)
    - Fail: > 500 lines (configurable)

Exclude patterns (always ignored):
    - .git/, node_modules/, .venv/, coverage_html/, runs/
    - build/, dist/, __pycache__/, .pytest_cache/
    - Generated data: *.json (large), *.log

Allowlist categories:
    - [EXTRACTION] - temporary, pending staged extraction
    - [CONTRACT] - typeddict/payload contracts, need review
    - [TEST] - test fixtures, need split by behavior
    - [SCRIPT] - standalone utility scripts
    - [DOC] - documentation files (not code)
    - [GENERATED] - generated or data files
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Default thresholds
DEFAULT_WARN_LINES = 300
DEFAULT_MAX_LINES = 500

# Directories to always exclude (generated/data only)
EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "coverage_html",
    "runs",
    "build",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
}

# File patterns to always exclude (generated/data)
EXCLUDED_PATTERNS = {
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "Pipfile.lock",
    "requirements.txt",
    ".DS_Store",
}

# Allowed file extensions (empty means all)
ALLOWED_EXTENSIONS: set[str] = set()

# ============================================================================
# Allowlist with category markers
# ============================================================================
# Format: (path, "[CATEGORY] reason")
# Categories: EXTRACTION, CONTRACT, TEST, SCRIPT, DOC, GENERATED
# Review allowlist entries periodically for staleness.
ALLOWLIST: list[tuple[str, str]] = [
    # [DOC] Documentation - single-purpose reference docs
    ("docs/agent-run-review-template.md", "[DOC] Single-purpose template"),
    ("docs/data-model.md", "[DOC] Data model reference"),
    ("docs/security/threat-model.md", "[DOC] Security reference"),
    ("docs/security-exception-audit.md", "[DOC] Audit document - historical record"),
    ("docs/artifact-immutability-audit.md", "[DOC] Audit document - historical record"),

    # [CONTRACT] TypedDict contracts - large but coherent
    ("src/k8s_diag_agent/ui/api_payloads.py", "[CONTRACT] TypedDict contracts - pending split"),

    # [EXTRACTION] Backend - extraction in progress
    ("src/k8s_diag_agent/health/loop.py", "[EXTRACTION] Health loop - extract by concern"),
    ("src/k8s_diag_agent/ui/api_incident_report.py", "[EXTRACTION] Incident report - extract builders"),
    ("src/k8s_diag_agent/health/ui.py", "[EXTRACTION] Health UI - extract by panel"),
    ("src/k8s_diag_agent/ui/api.py", "[EXTRACTION] API orchestrator - re-export pattern"),
    ("src/k8s_diag_agent/ui/server.py", "[EXTRACTION] Server routes - pending extraction"),
    ("src/k8s_diag_agent/ui/server_read_support.py", "[EXTRACTION] Read support - pending extraction"),
    ("src/k8s_diag_agent/ui/server_reads.py", "[EXTRACTION] Server reads - pending extraction"),
    ("src/k8s_diag_agent/ui/server_next_checks.py", "[EXTRACTION] Next checks - reduced to 757 lines"),
    ("src/k8s_diag_agent/external_analysis/alertmanager_discovery.py", "[EXTRACTION] Alertmanager discovery - extraction in progress"),
    ("src/k8s_diag_agent/external_analysis/next_check_planner.py", "[EXTRACTION] Next check planner - complex extraction"),
    ("src/k8s_diag_agent/external_analysis/vmalert_discovery.py", "[EXTRACTION] vmalert discovery - extraction in progress"),
    ("src/k8s_diag_agent/external_analysis/manual_next_check.py", "[EXTRACTION] Manual next check - complex dependencies"),
    ("src/k8s_diag_agent/external_analysis/llamacpp_adapter.py", "[EXTRACTION] LLM adapter - complex extraction"),
    ("src/k8s_diag_agent/llm/llamacpp_provider.py", "[EXTRACTION] LLM provider - complex dependencies"),
    ("src/k8s_diag_agent/health/loop_scheduler.py", "[EXTRACTION] Loop scheduler - complex extraction"),
    ("src/k8s_diag_agent/cli_handlers.py", "[EXTRACTION] CLI handlers - command complexity"),
    ("src/k8s_diag_agent/health/adaptation.py", "[EXTRACTION] Adaptation module - complex logic"),
    ("src/k8s_diag_agent/health/drilldown.py", "[EXTRACTION] Drilldown module - complex logic"),
    ("src/k8s_diag_agent/health/review_feedback.py", "[EXTRACTION] Review feedback - complex logic"),
    ("src/k8s_diag_agent/health/summary.py", "[EXTRACTION] Summary module - complex aggregation"),
    ("src/k8s_diag_agent/health/ui_planner_queue.py", "[EXTRACTION] Planner queue - complex UI logic"),

    # [TEST] Test fixtures - need split by behavior
    ("tests/fixtures/incident_report_fixtures.py", "[TEST] Fixture data - extract by test family"),
    ("tests/unit/test_ui_server_api_alertmanager_sources.py", "[TEST] Alertmanager sources - large fixtures"),
    ("tests/unit/test_health_loop_alertmanager_snapshot_collection.py", "[TEST] Snapshot tests - split by scenario"),
    ("tests/unit/test_api_incident_report.py", "[TEST] Incident report tests - large fixtures"),
    ("tests/unit/test_health_ui.py", "[TEST] Health UI tests - complex fixtures"),
    ("tests/unit/test_ui_server_api.py", "[TEST] UI server API tests - complex fixtures"),
    ("tests/unit/test_alertmanager_discovery.py", "[TEST] Alertmanager discovery tests"),
    ("tests/test_health_loop.py", "[TEST] Health loop tests - complex fixtures"),
    ("tests/test_alertmanager.py", "[TEST] Alertmanager tests - complex scenarios"),
    ("tests/test_scripts.py", "[TEST] Script tests - complex test scenarios"),
    ("tests/test_security_path_validation.py", "[TEST] Security tests - complex scenarios"),
    ("tests/test_index_batch_eligibility.py", "[TEST] Batch eligibility tests"),
    ("tests/test_prompt_anonymization.py", "[TEST] Prompt tests - complex scenarios"),
    ("tests/test_next_check_planner.py", "[TEST] Planner tests - complex scenarios"),
    ("tests/test_alertmanager_feedback.py", "[TEST] Alertmanager feedback tests"),
    ("tests/test_external_analysis.py", "[TEST] External analysis tests"),
    ("tests/test_server_read_support_deanonymization.py", "[TEST] Deanonymization tests"),
    ("tests/test_server_read_support_security.py", "[TEST] Security tests - complex scenarios"),
    ("tests/unit/test_external_analysis_artifact.py", "[TEST] External analysis artifact tests"),
    ("tests/unit/test_usefulness_feedback.py", "[TEST] Usefulness feedback tests - complex scenarios"),
    ("tests/unit/test_next_check_planner_alertmanager.py", "[TEST] Planner tests"),
    ("tests/unit/test_external_analysis_adapter.py", "[TEST] Adapter tests"),
    ("tests/unit/test_external_analysis_manual_next_check.py", "[TEST] Manual next check tests"),
    ("tests/unit/test_external_analysis_result_digest.py", "[TEST] Result digest tests"),
    ("tests/unit/test_vmalert_discovery.py", "[TEST] vmalert discovery tests"),
    ("tests/unit/test_alertmanager_source_registry.py", "[TEST] Alertmanager registry tests"),
    ("tests/unit/test_alertmanager_relevance_review.py", "[TEST] Relevance tests - complex scenarios"),
    ("tests/unit/test_alertmanager_cross_namespace_discovery.py", "[TEST] Cross-namespace discovery tests"),
    ("tests/unit/test_api_incident_report_ownership.py", "[TEST] Ownership tests - complex scenarios"),
    ("tests/unit/test_api_run_performance.py", "[TEST] Performance tests"),
    ("tests/unit/test_artifact_exception_handling.py", "[TEST] Exception handling tests"),
    ("tests/unit/test_batch_next_checks.py", "[TEST] Batch tests - complex scenarios"),
    ("tests/unit/test_diagnostic_pack.py", "[TEST] Diagnostic pack tests"),
    ("tests/unit/test_external_analysis_deterministic_next_check_promotion.py", "[TEST] Promotion tests"),
    ("tests/unit/test_feedback_validators.py", "[TEST] Validator tests - complex scenarios"),
    ("tests/unit/test_health_loop_alertmanager_discovery.py", "[TEST] Discovery tests - complex"),
    ("tests/unit/test_health_notifications.py", "[TEST] Notification tests - complex scenarios"),
    ("tests/unit/test_health_scheduler.py", "[TEST] Scheduler tests - complex scenarios"),
    ("tests/unit/test_llm_assessor.py", "[TEST] LLM assessor tests - complex scenarios"),
    ("tests/unit/test_mutation_request_validation.py", "[TEST] Mutation tests"),
    ("tests/unit/test_report_usefulness_learning.py", "[TEST] Learning tests"),
    ("tests/unit/test_review_enrichment_alertmanager_references.py", "[TEST] Reference tests - complex scenarios"),
    ("tests/unit/test_run_artifact_index.py", "[TEST] Index tests - complex scenarios"),
    ("tests/unit/test_runs_list_window_optimization.py", "[TEST] Window optimization tests"),
    ("tests/unit/test_scheduler_config_logging.py", "[TEST] Logging tests - complex scenarios"),
    ("tests/unit/test_server_alertmanager_exception_handling.py", "[TEST] Exception tests - complex"),
    ("tests/unit/test_ui_model.py", "[TEST] UI model tests - complex scenarios"),
    ("tests/unit/test_ui_model_builders.py", "[TEST] Builder tests - complex scenarios"),
    ("tests/unit/test_ui_model_next_check_queue_import_compat.py", "[TEST] Import compatibility tests"),
    ("tests/unit/test_ui_server_api_vmalert_sources.py", "[TEST] vmalert sources tests - complex scenarios"),
    ("tests/unit/test_ui_server_past_run_status.py", "[TEST] Past status tests - complex scenarios"),
    ("tests/unit/test_vmalert_discovery_smoke.py", "[TEST] vmalert smoke tests - complex scenarios"),
    ("tests/unit/test_vmalert_rule_state_artifact.py", "[TEST] vmalert rule state tests"),
    ("tests/security/test_deanonymization.py", "[TEST] Security tests - complex scenarios"),
    ("tests/test_index_batch_eligibility_cache_freshness.py", "[TEST] Cache tests - complex scenarios"),

    # [SCRIPT] Standalone utility scripts
    ("scripts/build_diagnostic_pack.py", "[SCRIPT] Build tool - single-purpose"),
    ("scripts/import_next_check_usefulness_feedback.py", "[SCRIPT] Import tool - single-purpose"),
    ("scripts/report_usefulness_learning.py", "[SCRIPT] Report tool - single-purpose"),
    ("scripts/debug_recent_runs_execution_state.sh", "[SCRIPT] Debug script - single-purpose"),

    # [FRONTEND] Frontend components and tests
    ("frontend/src/App.tsx", "[FRONTEND] Main React app - requires UI architect review"),
    ("frontend/src/components/ExecutionHistoryPanel.tsx", "[FRONTEND] Execution history - complex panel"),
    ("frontend/src/components/AlertmanagerPanel.tsx", "[FRONTEND] Alertmanager panel - complex UI"),
    ("frontend/src/components/ClusterNextCheckPlanSection.tsx", "[FRONTEND] Cluster section - complex UI"),
    ("frontend/src/components/QueuePanel.tsx", "[FRONTEND] Queue panel - complex UI"),
    ("frontend/src/components/RunsPanel.tsx", "[FRONTEND] Runs panel - complex UI"),
    ("frontend/src/hooks/useRunSelection.ts", "[FRONTEND] Selection hook - state complexity"),
    ("frontend/src/types.ts", "[FRONTEND] Shared types - large but coherent"),
    ("frontend/src/utils/selectors.ts", "[FRONTEND] Selector utilities - complex state"),
    ("frontend/src/run-control/runControlReducer.ts", "[FRONTEND] Reducer - state machine complexity"),
    ("frontend/src/run-control/useRunControl.ts", "[FRONTEND] State hook - complex dependencies"),

    # [FRONTEND TESTS] Frontend test files
    ("frontend/src/__tests__/app.test.tsx", "[FRONTEND TEST] Frontend app test - requires shared context"),
    ("frontend/src/__tests__/fixtures.ts", "[FRONTEND TEST] Test fixtures - shared test data"),
    ("frontend/src/__tests__/incident-report-operator-worklist.test.tsx", "[FRONTEND TEST] Snapshot UI test"),
    ("frontend/src/__tests__/api.test.ts", "[FRONTEND TEST] API tests - complex scenarios"),
    ("frontend/src/__tests__/advisory-lower-sections.test.tsx", "[FRONTEND TEST] Snapshot UI test"),
    ("frontend/src/__tests__/advisory-panel.test.tsx", "[FRONTEND TEST] Snapshot UI test"),
    ("frontend/src/__tests__/alertmanager-cluster-switching-regression.test.tsx", "[FRONTEND TEST] Regression test"),
    ("frontend/src/__tests__/execution-history-filter.test.tsx", "[FRONTEND TEST] UI test - complex scenarios"),
    ("frontend/src/__tests__/execution-history-usefulness.test.tsx", "[FRONTEND TEST] UI test - complex scenarios"),
    ("frontend/src/__tests__/run-summary-components.test.tsx", "[FRONTEND TEST] Snapshot UI test"),
    ("frontend/src/__tests__/status-cue-regression.test.tsx", "[FRONTEND TEST] Regression test"),
    ("frontend/src/__tests__/vmalert-alert-state-panel.test.tsx", "[FRONTEND TEST] Snapshot UI test"),
    ("frontend/src/utils/__tests__/selectors.test.ts", "[FRONTEND TEST] Selector tests - complex scenarios"),
    ("frontend/src/run-control/__tests__/runControlReducer.test.ts", "[FRONTEND TEST] Reducer tests - complex state"),
    ("frontend/src/run-control/__tests__/useRunControl.test.tsx", "[FRONTEND TEST] Hook tests - complex scenarios"),
    ("frontend/src/run-control/__tests__/boot-fetch-scheduling.test.tsx", "[FRONTEND TEST] Boot fetch tests"),

    # [STYLES] CSS files - large but coherent
    ("frontend/src/index.css", "[STYLES] Main CSS - style collection"),
    ("frontend/src/styles/components/next-check-plan.css", "[STYLES] Plan styles - complex selectors"),
    ("frontend/src/styles/components/next-check-queue.css", "[STYLES] Queue styles - complex selectors"),
    ("frontend/src/styles/components/run-overview-dashboard.css", "[STYLES] Dashboard styles - complex selectors"),

    # [SCRIPTS] Additional scripts
    ("scripts/export_next_check_usefulness_review.py", "[SCRIPT] Export tool - single-purpose"),
    ("scripts/select_review_candidate_runs.py", "[SCRIPT] Selection tool - single-purpose"),

    # [FRONTEND] Additional frontend files
    ("frontend/src/api.ts", "[FRONTEND] API client - large but coherent"),
    ("frontend/src/hooks/useQueueState.ts", "[FRONTEND] Queue state hook - complex logic"),
    ("frontend/src/__tests__/alertmanager-snapshot-panel.test.tsx", "[FRONTEND TEST] Snapshot panel tests"),
    ("frontend/src/__tests__/alertmanager-sources-panel.test.tsx", "[FRONTEND TEST] Sources panel tests"),
    ("frontend/src/__tests__/pagination.test.tsx", "[FRONTEND TEST] Pagination tests"),
    ("frontend/src/__tests__/run-overview-dashboard.test.tsx", "[FRONTEND TEST] Dashboard tests"),
    ("frontend/src/__tests__/selected-run-refresh-regression.test.tsx", "[FRONTEND TEST] Refresh regression tests"),

    # [BACKEND] Additional backend files
    ("src/k8s_diag_agent/collect/live_snapshot.py", "[EXTRACTION] Live snapshot - complex extraction"),
    ("src/k8s_diag_agent/external_analysis/alertmanager_durable_learning.py", "[EXTRACTION] Durable learning - complex extraction"),
    ("src/k8s_diag_agent/external_analysis/alertmanager_source_registry.py", "[EXTRACTION] Alertmanager registry - complex extraction"),
    ("src/k8s_diag_agent/external_analysis/vmalert_rule_state.py", "[EXTRACTION] vmalert rule state - complex extraction"),
    ("src/k8s_diag_agent/health/ui_next_check_execution.py", "[EXTRACTION] UI execution - complex extraction"),
    ("src/k8s_diag_agent/security/anonymizer.py", "[EXTRACTION] Anonymizer - complex extraction"),
    ("src/k8s_diag_agent/ui/api_debug.py", "[EXTRACTION] API debug - complex extraction"),
    ("src/k8s_diag_agent/ui/model.py", "[EXTRACTION] UI model - complex extraction"),
    ("src/k8s_diag_agent/ui/notifications.py", "[EXTRACTION] Notifications - complex extraction"),

    # [TEST FIXTURES] Additional test fixture files
    ("tests/fixtures/incident_report_cross_cluster_fixtures.py", "[TEST] Cross-cluster fixtures - large data"),
    ("tests/fixtures/ui_index_sample.py", "[TEST] UI index fixtures - large data"),
    ("tests/test_alertmanager_durable_learning.py", "[TEST] Durable learning tests"),
    ("tests/test_debug_recent_runs_execution_state.py", "[TEST] Debug execution state tests"),
    ("tests/test_metadata_anonymizer.py", "[TEST] Metadata anonymizer tests"),
    ("tests/test_phase1b_anonymization.py", "[TEST] Anonymization tests"),
    ("tests/unit/test_alertmanager_identity_e2e.py", "[TEST] Alertmanager identity e2e tests"),
    ("tests/unit/test_batch_execution_state_consolidation.py", "[TEST] Batch execution tests"),
    ("tests/unit/test_execution_summary_derivation.py", "[TEST] Execution summary tests"),
    ("tests/unit/test_health_validators.py", "[TEST] Health validators tests"),
    ("tests/unit/test_llamacpp_generation_settings.py", "[TEST] LlamaCPP settings tests"),
    ("tests/unit/test_loop_vmalert_discovery.py", "[TEST] Loop vmalert discovery tests"),
    ("tests/unit/test_notification_artifact_readers.py", "[TEST] Notification readers tests"),
    ("tests/unit/test_proposal_lifecycle_events.py", "[TEST] Proposal lifecycle tests"),
    ("tests/unit/test_server_feedback_exception_handling.py", "[TEST] Feedback exception tests"),
    ("tests/unit/test_ui_api.py", "[TEST] UI API tests - large fixtures"),
    ("tests/unit/test_ui_api_debug.py", "[TEST] UI API debug tests"),
    ("tests/unit/test_ui_api_execution_summary.py", "[TEST] Execution summary tests"),
    ("tests/unit/test_ui_model_assessment.py", "[TEST] Model assessment tests"),
    ("tests/unit/test_ui_model_llm_policy_import_compat.py", "[TEST] LLM policy import tests"),
    ("tests/unit/test_vmalert_rule_state.py", "[TEST] vmalert rule state tests"),

    # [DOCS] Large documentation files
    ("charts/k9b/README.md", "[DOC] Helm chart reference - all content is related"),
    ("docs/beta-stakeholder-demo-script.md", "[DOC] Demo script - single-purpose"),
    ("docs/doctrine/evals/seed_evals.yaml", "[DOC] Seed evals - data file"),
    ("docs/post-beta-operator-feedback-and-live-integrations.md", "[DOC] Feedback document"),
    ("docs/schemas/incident-report-schema.md", "[DOC] Schema reference - all content related"),
    ("docs/security/llm-anonymization-design.md", "[DOC] Design document"),
    ("docs/security/llm-prompt-security-audit.md", "[DOC] Security audit - historical"),
    ("docs/security/operator-auth-design.md", "[DOC] Auth design - all content related"),
    ("docs/security/rbac-deployment-guide.md", "[DOC] RBAC guide - all content related"),
    ("docs/security/security-audit-closeout.md", "[DOC] Audit closeout - historical"),
    ("docs/security/subprocess-security-audit.md", "[DOC] Subprocess audit - historical"),

    # [SCRIPTS] Verification scripts - comprehensive but coherent
    ("scripts/step_runner.sh", "[SCRIPT] Step runner - shared verification logic"),
    ("scripts/verify_all.sh", "[SCRIPT] Verification gate - comprehensive gate"),
]

# ============================================================================
# Helpers
# ============================================================================


def get_git_root() -> Path:
    """Return the git repository root."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def get_git_tracked_files() -> list[Path]:
    """Return list of git-tracked files."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
        cwd=get_git_root(),
    )
    files = [Path(get_git_root() / f) for f in result.stdout.split("\0") if f]
    return files


def get_changed_files() -> list[Path]:
    """Return list of files changed in working tree (staged + unstaged + untracked)."""
    root = get_git_root()

    # Staged files
    result = subprocess.run(
        ["git", "diff", "--name-only", "--cached"],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    staged = set(f for f in result.stdout.strip().split("\n") if f)

    # Unstaged modifications
    result = subprocess.run(
        ["git", "diff", "--name-only"],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    unstaged = set(f for f in result.stdout.strip().split("\n") if f)

    # Untracked files
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    untracked = set(f for f in result.stdout.strip().split("\n") if f)

    combined = staged | unstaged | untracked
    return [Path(root / f) for f in combined if f]


def is_excluded(path: Path, root: Path) -> bool:
    """Check if path should be excluded based on directory/pattern rules."""
    rel = path.relative_to(root)

    # Check path components
    for part in rel.parts:
        if part in EXCLUDED_DIRS:
            return True

    # Check filename patterns
    if rel.name in EXCLUDED_PATTERNS:
        return True

    # Check extensions
    if ALLOWED_EXTENSIONS and path.suffix not in ALLOWED_EXTENSIONS:
        return True

    return False


def is_allowlisted(path: Path, root: Path, allowlist: list[tuple[str, str]]) -> tuple[bool, str | None]:
    """Check if path is in allowlist. Returns (is_allowed, reason)."""
    for allowed_path, reason in allowlist:
        # Normalize to absolute path for comparison
        if Path(allowed_path).resolve() == path.resolve():
            return True, reason

    # Check relative to root
    try:
        rel_path = str(path.relative_to(root))
        for allowed_path, reason in allowlist:
            if Path(allowed_path) == path or Path(allowed_path) == Path(rel_path):
                return True, reason
    except ValueError:
        pass

    return False, None


def count_physical_lines(path: Path) -> int:
    """Count physical lines in a file. Returns 0 for binary files."""
    try:
        with open(path, "rb") as f:
            # Read first 8KB to check for binary content
            chunk = f.read(8192)
            if b"\x00" in chunk:
                return 0  # Binary file

        with open(path, encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def validate_allowlist(root: Path, allowlist: list[tuple[str, str]]) -> list[str]:
    """Validate allowlist entries. Returns list of error messages."""
    errors = []
    for path_str, reason in allowlist:
        # Check reason is sufficient
        if not reason or len(reason.strip()) < 10:
            errors.append(f"Allowlist entry '{path_str}' has insufficient reason")

        # Check file exists
        file_path = Path(path_str)
        if not file_path.is_absolute():
            file_path = root / path_str

        if not file_path.exists():
            errors.append(f"Allowlist entry '{path_str}' - file does not exist (stale)")
            continue

        # Check if file is excluded by global exclusion rules
        if is_excluded(file_path, root):
            errors.append(f"Allowlist entry '{path_str}' - file is globally excluded (redundant)")

    return errors


def check_file(
    path: Path,
    root: Path,
    warn_lines: int,
    max_lines: int,
    allowlist: list[tuple[str, str]],
) -> tuple[bool, str]:
    """Check a single file. Returns (passed, message)."""
    # Check allowlist first
    is_allowed, reason = is_allowlisted(path, root, allowlist)
    if is_allowed:
        return True, f"{path} is allowlisted: {reason}"

    # Check for binary
    line_count = count_physical_lines(path)
    if line_count == 0 and path.suffix not in {".py", ".ts", ".tsx", ".sh", ".md", ".yml", ".yaml"}:
        return True, f"{path} appears to be binary, skipped"

    # If line_count is 0 but extension suggests text, count non-empty as fallback
    if line_count == 0:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                line_count = sum(1 for _ in f)
        except OSError:
            return True, f"{path} could not be read, skipped"

    if line_count > max_lines:
        return False, (
            f"{path}: {line_count} lines (exceeds {max_lines})\n"
            f"  Action: Split this file by responsibility. Consider:\n"
            f"    - Extract related functions/classes into focused modules\n"
            f"    - Move type definitions to contract module\n"
            f"    - Separate UI rendering from business logic"
        )

    if line_count > warn_lines:
        return False, (
            f"{path}: {line_count} lines (warn > {warn_lines})\n"
            f"  Action: Consider splitting if related code can be extracted"
        )

    return True, f"{path}: {line_count} lines (OK)"


# ============================================================================
# Main
# ============================================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check files for LLM-friendly size limits.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Check only git-changed files (staged + unstaged + untracked)",
    )
    parser.add_argument(
        "--warn-lines",
        type=int,
        default=DEFAULT_WARN_LINES,
        help=f"Warning threshold for file size (default: {DEFAULT_WARN_LINES})",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
        help=f"Maximum allowed lines (default: {DEFAULT_MAX_LINES})",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress OK messages",
    )

    args = parser.parse_args()

    root = get_git_root()

    # Validate allowlist
    errors = validate_allowlist(root, ALLOWLIST)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    # Get files to check
    if args.changed_only:
        files = get_changed_files()
    else:
        files = get_git_tracked_files()

    # Filter to checkable files
    checkable = [f for f in files if not is_excluded(f, root) and f.is_file()]

    failures = []
    warnings = []

    for path in sorted(checkable):
        passed, msg = check_file(path, root, args.warn_lines, args.max_lines, ALLOWLIST)
        if not passed:
            if "exceeds" in msg:
                failures.append(msg)
                if not args.quiet:
                    print(msg)
            else:
                warnings.append(msg)
                if not args.quiet:
                    print(msg)
        elif not args.quiet:
            print(msg)

    # Summary
    print()
    print(f"Checked {len(checkable)} files")
    print(f"  Failures: {len(failures)}")
    print(f"  Warnings: {len(warnings)}")

    if failures:
        print("\nFAILURE: Files exceed maximum threshold")
        return 1

    if warnings:
        print("\nWARNING: Files exceed warning threshold (non-blocking)")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())