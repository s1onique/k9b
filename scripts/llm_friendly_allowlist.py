# scripts/llm_friendly_allowlist.py
"""Allowlist for LLM-friendly file size checker.

This module contains the baseline allowlist of files that exceed size thresholds
but are intentionally kept as-is pending staged extraction or architectural work.

Categories:
    [EXTRACTION] - Backend extraction in progress
    [CONTRACT]   - TypedDict/payload contracts
    [TEST]       - Test fixtures, need split by behavior
    [SCRIPT]     - Standalone utility scripts
    [DOC]        - Documentation files
    [GENERATED]  - Generated or data files
    [CONFIG]     - Configuration/ledger files
    [FRONTEND]   - Frontend React components
    [FRONTEND TEST] - Frontend test files
    [STYLES]     - CSS style files

Review allowlist entries periodically for staleness.
"""

from __future__ import annotations

# Allowlist: (path, "[CATEGORY] reason")
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
    # server_read_support.py extracted - cluster/drilldown to server_read_clusters.py (495);
    #   next-check to server_read_next_checks.py (379); execution history to server_read_execution_history.py (207);
    #   llm-stats to server_read_llm_stats.py (388); now 390 lines, below 500 threshold
    # vmalert_discovery.py extracted to models/sources/strategies modules (416 lines, below threshold)
    # llamacpp_provider.py extracted to config/errors/payloads/response modules (143 lines)
    ("src/k8s_diag_agent/health/loop_scheduler.py", "[EXTRACTION] Loop scheduler - run loop extracted; compatibility surface remains"),


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

    # [FRONTEND TEST] Frontend test files
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

    # [CONFIG] Checker configuration - baseline allowlist ledger
    ("scripts/check_llm_friendly_files.py", "[CONFIG] LLM-friendly checker implementation"),
    ("scripts/llm_friendly_allowlist.py", "[CONFIG] Baseline burn-down allowlist ledger"),
]
