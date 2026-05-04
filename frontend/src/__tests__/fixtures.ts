import { vi } from "vitest";
import dayjs from "dayjs";
import { within } from "@testing-library/react";
import type {
  ClusterDetailPayload,
  DiagnosticPackReview,
  FleetPayload,
  NextCheckPlanCandidate,
  NotificationsPayload,
  ProposalsPayload,
  ProviderExecution,
  ReviewEnrichment,
  ReviewEnrichmentStatus,
  RunPayload,
  RunsListPayload,
} from "../types";

// Helper to generate timestamps relative to test execution time.
// All fixtures use dynamic timestamps so freshness tests always have predictable
// behavior regardless of when tests run.
const minsAgo = (minutes: number) => dayjs().subtract(minutes, "minute").toISOString();
const secsAgo = (seconds: number) => dayjs().subtract(seconds, "second").toISOString();

export const sampleRunsList: RunsListPayload = {
  runs: [
    {
      runId: "run-123",
      runLabel: "2026-04-07-1200",
      timestamp: minsAgo(5),
      clusterCount: 3,
      triaged: true,
      executionCount: 5,
      reviewedCount: 5,
      reviewStatus: "fully-reviewed",
    },
    {
      runId: "run-122",
      runLabel: "2026-04-07-1100",
      timestamp: minsAgo(70),  // 70 min ago → aging/warning
      clusterCount: 3,
      triaged: false,
      executionCount: 3,
      reviewedCount: 0,
      reviewStatus: "unreviewed",
      reviewDownloadPath: "health/diagnostic-packs/run-122/next_check_usefulness_review.json",
    },
    {
      runId: "run-121",
      runLabel: "2026-04-07-1000",
      timestamp: "2026-04-07T10:00:00Z",
      clusterCount: 2,
      triaged: true,
      executionCount: 2,
      reviewedCount: 1,
      reviewStatus: "partially-reviewed",
    },
    {
      runId: "run-120",
      runLabel: "2026-04-07-0900",
      timestamp: "2026-04-07T09:00:00Z",
      clusterCount: 1,
      triaged: false,
      executionCount: 0,
      reviewedCount: 0,
      reviewStatus: "no-executions",
    },
  ],
  totalCount: 4,
  executionCountsComplete: true,
};

export const sampleNextCheckCandidates: NextCheckPlanCandidate[] = [
  {
    description: "Collect kubelet logs for control-plane pods",
    targetCluster: "cluster-a",
    sourceReason: "warning_event_threshold",
    expectedSignal: "logs",
    suggestedCommandFamily: "kubectl-logs",
    safeToAutomate: true,
    requiresOperatorApproval: false,
    riskLevel: "low",
    estimatedCost: "low",
    confidence: "high",
    priorityLabel: "primary",
    gatingReason: null,
    duplicateOfExistingEvidence: false,
    duplicateEvidenceDescription: null,
    candidateId: "candidate-logs",
    candidateIndex: 0,
    approvalStatus: "not-required",
    approvalState: "not-required",
    executionState: "executed-success",
    outcomeStatus: "executed-success",
    latestArtifactPath: "/artifacts/run-123-next-check-execution-0.json",
    latestTimestamp: "2026-04-06T12:05:00Z",
    normalizationReason: "selection_label",
    safetyReason: "known_command",
    approvalReason: null,
    duplicateReason: null,
    blockingReason: null,
    targetContext: "cluster-a · control-plane pods",
    priorityRationale: null,
    commandPreview: "kubectl logs deployment/control-plane --context cluster-a",
  },
  {
    description: "Describe diag CRD for control plane",
    targetCluster: null,
    sourceReason: "diag-availability",
    expectedSignal: "events",
    suggestedCommandFamily: "kubectl-describe",
    safeToAutomate: false,
    requiresOperatorApproval: true,
    riskLevel: "medium",
    estimatedCost: "medium",
    confidence: "medium",
    priorityLabel: "secondary",
    gatingReason: "Command not recognized or too vague",
    duplicateOfExistingEvidence: false,
    duplicateEvidenceDescription: null,
    candidateId: "candidate-describe",
    candidateIndex: 1,
    approvalStatus: "approval-required",
    approvalState: "approval-required",
    executionState: "unexecuted",
    outcomeStatus: "approval-required",
    latestArtifactPath: null,
    latestTimestamp: null,
    normalizationReason: "selection_default",
    safetyReason: "unknown_command",
    approvalReason: "unknown_command",
    duplicateReason: null,
    blockingReason: "unknown_command",
    targetContext: "cluster-b · diag CRD",
    commandPreview: "kubectl describe diag customresourcedefinition --context cluster-b",
    priorityRationale: "Approval required before execution",
  },
  {
    description: "Capture kubelet metrics for control-plane nodes",
    targetCluster: "cluster-a",
    sourceReason: "metric-surge",
    expectedSignal: "metrics",
    suggestedCommandFamily: "kubectl-get",
    safeToAutomate: false,
    requiresOperatorApproval: true,
    riskLevel: "medium",
    estimatedCost: "medium",
    confidence: "low",
    priorityLabel: "fallback",
    gatingReason: "Matches deterministic next check: Collect kubelet metrics",
    duplicateOfExistingEvidence: true,
    duplicateEvidenceDescription: "Collect kubelet metrics",
    candidateId: "candidate-metrics",
    candidateIndex: 2,
    approvalStatus: "not-required",
    approvalState: "not-required",
    executionState: "unexecuted",
    outcomeStatus: "not-used",
    latestArtifactPath: null,
    latestTimestamp: null,
    normalizationReason: "selection_default",
    safetyReason: "duplicate_evidence",
    approvalReason: "duplicate_evidence",
    duplicateReason: "exact_match",
    blockingReason: "duplicate",
    targetContext: "cluster-a · nodes",
    commandPreview: "kubectl get nodes --context cluster-a",
  },
];

export const sampleDiagnosticPackReview: DiagnosticPackReview = {
  timestamp: "2026-04-06T12:02:00Z",
  summary: "Review detected ranking mismatches and suggested additional confirmation steps.",
  majorDisagreements: [
    "cluster-b priority order conflicts with deterministic assessment",
    "planner ranked storage downstream of networking despite earlier alerts",
  ],
  missingChecks: [
    "Validate storage latency from cluster-b",
    "Capture node drain readiness for cluster-a",
  ],
  rankingIssues: [
    "Top recommendations favor low-utility checks",
    "Evidence-sourced prioritization differs from deterministic triggers",
  ],
  genericChecks: [
    "Review kubelet logs before escalating",
    "Double-check baseline release parity",
  ],
  recommendedNextActions: [
    "Confirm drift detection before reordering planner queue",
    "Survey provider-proposed actions with operator",
  ],
  driftMisprioritized: true,
  confidence: "medium",
  providerStatus: "provider-ok",
  providerSummary: "Provider k8sgpt validated the review and provided metadata.",
  providerErrorSummary: null,
  providerSkipReason: null,
  providerReview: { source: "k8sgpt", score: 0.92 },
  artifactPath: "/artifacts/diagnostic-pack-review.json",
};

export const makeDiagnosticPackReview = (
  overrides: Partial<DiagnosticPackReview> = {}
): DiagnosticPackReview => ({
  ...sampleDiagnosticPackReview,
  ...overrides,
  majorDisagreements:
    overrides.majorDisagreements ?? [...sampleDiagnosticPackReview.majorDisagreements],
  missingChecks: overrides.missingChecks ?? [...sampleDiagnosticPackReview.missingChecks],
  rankingIssues: overrides.rankingIssues ?? [...sampleDiagnosticPackReview.rankingIssues],
  genericChecks: overrides.genericChecks ?? [...sampleDiagnosticPackReview.genericChecks],
  recommendedNextActions:
    overrides.recommendedNextActions ?? [...sampleDiagnosticPackReview.recommendedNextActions],
});

export const sampleReviewEnrichmentStatus: ReviewEnrichmentStatus = {
  status: "success",
  reason: "Review enrichment succeeded and produced insights.",
  provider: "k8sgpt",
  policyEnabled: true,
  providerConfigured: true,
  adapterAvailable: true,
  runEnabled: true,
  runProvider: "k8sgpt",
};

export const makeReviewEnrichmentStatus = (
  overrides: Partial<ReviewEnrichmentStatus> = {}
): ReviewEnrichmentStatus => ({
  ...sampleReviewEnrichmentStatus,
  ...overrides,
});

export const sampleProviderExecution: ProviderExecution = {
  autoDrilldown: {
    enabled: true,
    provider: "default",
    maxPerRun: 3,
    eligible: 2,
    attempted: 1,
    succeeded: 0,
    failed: 1,
    skipped: 0,
    unattempted: 1,
    budgetLimited: 1,
    notes: "Reached max per run (3) before the 2nd eligible branch.",
  },
  reviewEnrichment: {
    enabled: true,
    provider: "k8sgpt",
    maxPerRun: 1,
    eligible: 1,
    attempted: 1,
    succeeded: 1,
    failed: 0,
    skipped: 0,
    unattempted: 0,
    budgetLimited: null,
    notes: "Review enrichment artifact recorded.",
  },
};

export const makeProviderExecution = (
  overrides: Partial<ProviderExecution> = {}
): ProviderExecution => ({
  autoDrilldown: {
    ...sampleProviderExecution.autoDrilldown,
    ...overrides.autoDrilldown,
  },
  reviewEnrichment:
    overrides.reviewEnrichment === undefined
      ? sampleProviderExecution.reviewEnrichment
      : overrides.reviewEnrichment,
});

export const sampleRun: RunPayload = {
  runId: "run-123",
  label: "Daily sweep",
  timestamp: minsAgo(5),
  collectorVersion: "collector:v1.2.0",
  clusterCount: 2,
  drilldownCount: 5,
  proposalCount: 4,
  externalAnalysisCount: 1,
  notificationCount: 2,
  artifacts: [
    { label: "run manifest", path: "/artifacts/run-manifest.json" },
  ],
  runStats: {
    lastRunDurationSeconds: 32,
    totalRuns: 12,
    p50RunDurationSeconds: 24,
    p95RunDurationSeconds: 48,
    p99RunDurationSeconds: 64,
  },
  llmStats: {
    totalCalls: 3,
    successfulCalls: 2,
    failedCalls: 1,
    lastCallTimestamp: "2026-04-06T11:59:00Z",
    p50LatencyMs: 110,
    p95LatencyMs: 220,
    p99LatencyMs: 300,
    providerBreakdown: [
      { provider: "k8sgpt", calls: 2, failedCalls: 0 },
      { provider: "default", calls: 1, failedCalls: 1 },
    ],
    scope: "current_run",
  },
  historicalLlmStats: {
    totalCalls: 18,
    successfulCalls: 15,
    failedCalls: 3,
    lastCallTimestamp: "2026-04-06T11:58:00Z",
    p50LatencyMs: 140,
    p95LatencyMs: 280,
    p99LatencyMs: 350,
    providerBreakdown: [
      { provider: "k8sgpt", calls: 10, failedCalls: 2 },
      { provider: "llm-autodrilldown", calls: 8, failedCalls: 1 },
    ],
    scope: "retained_history",
  },
  llmActivity: {
    entries: [
      {
        timestamp: "2026-04-06T12:00:00Z",
        runId: "run-123",
        runLabel: "Daily sweep",
        clusterLabel: "review",
        toolName: "k8sgpt",
        provider: "k8sgpt",
        purpose: "review-enrichment",
        status: "success",
        latencyMs: 180,
        artifactPath: "/artifacts/review-enrichment.json",
        summary: "Review enrichment insight",
        errorSummary: null,
        skipReason: null,
      },
      {
        timestamp: "2026-04-06T11:58:00Z",
        runId: "run-123",
        runLabel: "Daily sweep",
        clusterLabel: "cluster-a",
        toolName: "k8sgpt",
        provider: "k8sgpt",
        purpose: "manual",
        status: "success",
        latencyMs: 120,
        artifactPath: "/artifacts/llm-1.json",
        summary: "analysis ready",
        errorSummary: null,
        skipReason: null,
      },
      {
        timestamp: "2026-04-06T11:57:00Z",
        runId: "run-123",
        runLabel: "Daily sweep",
        clusterLabel: "cluster-b",
        toolName: "llm-autodrilldown",
        provider: "default",
        purpose: "auto-drilldown",
        status: "failed",
        latencyMs: 200,
        artifactPath: "/artifacts/llm-2.json",
        summary: "timeout",
        errorSummary: "provider timeout",
        skipReason: null,
      },
    ],
    summary: {
      retainedEntries: 19,
    },
  },
  llmPolicy: {
    autoDrilldown: {
      enabled: true,
      provider: "default",
      maxPerRun: 3,
      usedThisRun: 1,
      successfulThisRun: 0,
      failedThisRun: 1,
      skippedThisRun: 0,
      budgetExhausted: false,
    },
  },
  providerExecution: sampleProviderExecution,
  reviewEnrichment: {
    status: "success",
    provider: "k8sgpt",
    timestamp: "2026-04-06T12:00:00Z",
    summary: "Review enrichment reshaped the triage order.",
    triageOrder: ["cluster-b", "cluster-a"],
    topConcerns: ["ingress latency", "storage delays"],
    evidenceGaps: ["logs from edge"],
    nextChecks: ["Validate ingress timeouts", "Collect storage metrics"],
    focusNotes: ["Prioritize cluster-b"],
    artifactPath: "/artifacts/review-enrichment.json",
    errorSummary: null,
    skipReason: null,
  },
  reviewEnrichmentStatus: sampleReviewEnrichmentStatus,
  nextCheckPlan: {
    summary: "Planner generated multiple advisory checks.",
    artifactPath: "/artifacts/next-check-plan.json",
    reviewPath: "/artifacts/run-123-review.json",
    enrichmentArtifactPath: "/artifacts/review-enrichment.json",
    candidateCount: sampleNextCheckCandidates.length,
    candidates: sampleNextCheckCandidates,
    orphanedApprovals: [],
    outcomeCounts: [
      { status: "executed-success", count: 1 },
      { status: "approval-required", count: 1 },
      { status: "not-used", count: 1 },
    ],
    orphanedApprovalCount: 0,
  },
  deterministicNextChecks: {
    clusterCount: 1,
    totalNextCheckCount: 6,
    clusters: [
      {
        label: "cluster-a",
        context: "prod",
        topProblem: "High CPU",
        deterministicNextCheckCount: 6,
        deterministicNextCheckSummaries: [
          {
            description: "Capture tcpdump",
            owner: "platform",
            method: "kubectl exec",
            evidenceNeeded: ["tcpdump output"],
            priorityScore: 95,
            workstream: "incident",
            urgency: "high",
            isPrimaryTriage: true,
            whyNow: "Immediate triage for High CPU",
          },
          {
            description: "Collect kubelet logs for web deployment",
            owner: "platform",
            method: "kubectl logs",
            evidenceNeeded: ["kubectl logs deployment/web"],
            priorityScore: 88,
            workstream: "incident",
            urgency: "high",
            isPrimaryTriage: true,
            whyNow: "Immediate triage for High CPU",
          },
          {
            description: "Inspect readiness probes for web-frontend",
            owner: "platform",
            method: "kubectl describe pod",
            evidenceNeeded: ["kubectl describe pod web-frontend"],
            priorityScore: 75,
            workstream: "incident",
            urgency: "high",
            isPrimaryTriage: false,
            whyNow: "Immediate triage for High CPU",
          },
          {
            description: "Review node conditions for control-plane hosts",
            owner: "platform",
            method: "kubectl get nodes",
            evidenceNeeded: ["kubectl describe nodes"],
            priorityScore: 68,
            workstream: "incident",
            urgency: "medium",
            isPrimaryTriage: false,
            whyNow: "Immediate triage for High CPU",
          },
          {
            description: "Collect kubelet metrics from nodes",
            owner: "platform",
            method: "kubectl get --raw /metrics",
            evidenceNeeded: ["kubelet metrics"],
            priorityScore: 50,
            workstream: "evidence",
            urgency: "medium",
            isPrimaryTriage: false,
            whyNow: "Gather additional evidence",
          },
          {
            description: "Compare baseline release parity",
            owner: "platform engineer",
            method: "kubectl get helmrelease",
            evidenceNeeded: ["helm release list"],
            priorityScore: 25,
            workstream: "drift",
            urgency: "low",
            isPrimaryTriage: false,
            whyNow: "Baseline drift follow-up",
          },
        ],
        drilldownAvailable: true,
        assessmentArtifactPath: "/artifacts/cluster-a-assessment.json",
        drilldownArtifactPath: "/artifacts/drilldown-cluster-a.json",
      },
    ],
  },
  nextCheckQueue: [
    {
      candidateId: "candidate-vague",
      candidateIndex: 1,
      description: "Describe diag CRD for control plane",
      targetCluster: null,
      priorityLabel: "secondary",
      suggestedCommandFamily: "kubectl-describe",
      safeToAutomate: false,
      requiresOperatorApproval: true,
      approvalState: "approval-required",
      executionState: "unexecuted",
      outcomeStatus: "approval-required",
      latestArtifactPath: null,
      sourceReason: "diag-availability",
      expectedSignal: "events",
      normalizationReason: "selection_default",
      safetyReason: "unknown_command",
      approvalReason: "unknown_command",
      duplicateReason: null,
      blockingReason: "unknown_command",
      targetContext: "cluster-b · diag CRD",
      commandPreview: "kubectl describe diag customresourcedefinition --context cluster-b",
      planArtifactPath: "external-analysis/run-123-next-check-plan.json",
      queueStatus: "approval-needed",
      failureClass: "approval-missing-or-stale",
      workstream: "incident",
      priorityRationale: "Approval required before execution",
      failureSummary: "Candidate requires operator approval before execution.",
      suggestedNextOperatorMove: "Review approval state",
      rankingReason: "approval-gated",
    },
    {
      candidateId: "candidate-logs",
      candidateIndex: 0,
      description: "Collect kubelet logs for control-plane pods",
      targetCluster: "cluster-a",
      priorityLabel: "primary",
      suggestedCommandFamily: "kubectl-logs",
      safeToAutomate: true,
      requiresOperatorApproval: false,
      approvalState: "not-required",
      executionState: "executed-success",
      outcomeStatus: "executed-success",
      latestArtifactPath: "/artifacts/run-123-next-check-execution-0.json",
      sourceReason: "warning_event_threshold",
      expectedSignal: "logs",
      normalizationReason: "selection_label",
      safetyReason: "known_command",
      approvalReason: null,
      duplicateReason: null,
      blockingReason: null,
      targetContext: "cluster-a · control-plane pods",
      commandPreview: "kubectl logs deployment/control-plane --context cluster-a",
      planArtifactPath: "external-analysis/run-123-next-check-plan.json",
      queueStatus: "completed",
      resultClass: "useful-signal",
      resultSummary: "Captured control-plane logs that highlight recent kubelet errors.",
      suggestedNextOperatorMove: "Correlate this output with the target incident.",
      workstream: "evidence",
    },
    {
      candidateId: "candidate-metrics",
      candidateIndex: 2,
      description: "Capture kubelet metrics for control-plane nodes",
      targetCluster: "cluster-a",
      priorityLabel: "fallback",
      suggestedCommandFamily: "kubectl-get",
      safeToAutomate: false,
      requiresOperatorApproval: true,
      approvalState: "approval-required",
      executionState: "unexecuted",
      outcomeStatus: "not-used",
      latestArtifactPath: null,
      sourceReason: "metric-surge",
      expectedSignal: "metrics",
      normalizationReason: "selection_default",
      safetyReason: "duplicate_evidence",
      approvalReason: "duplicate_evidence",
      duplicateReason: "exact_match",
      blockingReason: "duplicate",
      targetContext: "cluster-a · nodes",
      commandPreview: "kubectl get nodes --context cluster-a",
      planArtifactPath: "external-analysis/run-123-next-check-plan.json",
      queueStatus: "duplicate-or-stale",
      workstream: "drift",
    },
    {
      candidateId: "candidate-storage",
      candidateIndex: 3,
      description: "Collect storage latency metrics",
      targetCluster: "cluster-b",
      priorityLabel: "primary",
      suggestedCommandFamily: "kubectl-get",
      safeToAutomate: true,
      requiresOperatorApproval: false,
      approvalState: "not-required",
      executionState: "unexecuted",
      outcomeStatus: "not-used",
      latestArtifactPath: null,
      latestTimestamp: "2026-04-06T12:07:00Z",
      sourceReason: "storage-latency",
      expectedSignal: "metrics",
      normalizationReason: "selection_default",
      safetyReason: "known_command",
      approvalReason: null,
      duplicateReason: null,
      blockingReason: null,
      targetContext: "cluster-b · storage",
      commandPreview: "kubectl get pv --context cluster-b",
      planArtifactPath: "external-analysis/run-123-next-check-plan.json",
      queueStatus: "safe-ready",
      workstream: "incident",
    },
    {
      candidateId: "candidate-approved",
      candidateIndex: 4,
      description: "Validate networking policies",
      targetCluster: "cluster-a",
      priorityLabel: "secondary",
      suggestedCommandFamily: "kubectl-get",
      safeToAutomate: true,
      requiresOperatorApproval: true,
      approvalState: "approved",
      executionState: "unexecuted",
      outcomeStatus: "approved",
      latestArtifactPath: "/artifacts/approval-1.json",
      latestTimestamp: "2026-04-06T12:08:00Z",
      sourceReason: "network-policy",
      expectedSignal: "policy",
      normalizationReason: "selection_label",
      safetyReason: "known_command",
      approvalReason: "policy_reviewed",
      duplicateReason: null,
      blockingReason: null,
      targetContext: "cluster-a · networking",
      commandPreview: "kubectl get networkpolicies --context cluster-a",
      planArtifactPath: "external-analysis/run-123-next-check-plan.json",
      queueStatus: "approved-ready",
      workstream: "evidence",
    },
    {
      candidateId: "candidate-failed",
      candidateIndex: 5,
      description: "Inspect etcd leader",
      targetCluster: "cluster-b",
      priorityLabel: "secondary",
      suggestedCommandFamily: "kubectl-get",
      safeToAutomate: false,
      requiresOperatorApproval: false,
      approvalState: "not-required",
      executionState: "executed-failed",
      outcomeStatus: "executed-failed",
      latestArtifactPath: "/artifacts/run-123-next-check-execution-1.json",
      latestTimestamp: "2026-04-06T12:03:30Z",
      sourceReason: "etcd-candidate",
      expectedSignal: "events",
      normalizationReason: "selection_default",
      safetyReason: "known_command",
      approvalReason: null,
      duplicateReason: null,
      blockingReason: null,
      targetContext: "cluster-b · etcd",
      commandPreview: "kubectl get endpoints --context cluster-b",
      planArtifactPath: "external-analysis/run-123-next-check-plan.json",
      queueStatus: "failed",
      failureClass: "command-failed",
      failureSummary: "Command returned a non-zero exit code.",
      suggestedNextOperatorMove: "Inspect artifact output",
      workstream: "drift",
    },
  ],
  plannerAvailability: {
    status: "planner-present",
    reason: "Planner generated multiple advisory checks.",
    hint: null,
    artifactPath: "/artifacts/next-check-plan.json",
    nextActionHint:
      "Inspect the planner artifact for candidate context before taking any next-check action.",
  },
  diagnosticPackReview: sampleDiagnosticPackReview,
  diagnosticPack: {
    path: "/artifacts/run-123-diagnostic-pack.zip",
    timestamp: "2026-04-06T12:01:00Z",
    label: "Run 123 pack",
  },
  nextCheckExecutionHistory: [
    {
      timestamp: "2026-04-06T12:05:00Z",
      clusterLabel: "cluster-a",
      candidateId: "candidate-logs",
      candidateIndex: 0,
      candidateDescription: "Collect kubelet logs for control-plane pods",
      commandFamily: "kubectl-logs",
      status: "success",
      durationMs: 95,
      artifactPath: "/artifacts/run-123-next-check-execution-0.json",
      timedOut: false,
      stdoutTruncated: false,
      stderrTruncated: false,
      outputBytesCaptured: 2048,
      resultClass: "useful-signal",
      resultSummary: "Logs include control-plane errors useful for diagnosing the incident.",
      suggestedNextOperatorMove: "Correlate these logs with the ongoing incident timeline.",
      usefulnessClass: "useful",
      usefulnessSummary: "Captured control-plane logs that highlight recent kubelet errors.",
    },
    {
      timestamp: "2026-04-06T12:03:00Z",
      clusterLabel: "cluster-b",
      candidateId: "candidate-describe",
      candidateIndex: 1,
      candidateDescription: "Describe diag status",
      commandFamily: "kubectl-describe",
      status: "failed",
      durationMs: 30,
      artifactPath: "/artifacts/run-123-next-check-execution-1.json",
      timedOut: true,
      stdoutTruncated: true,
      stderrTruncated: false,
      outputBytesCaptured: 4096,
      failureClass: "timed-out",
      failureSummary: "Command timed out.",
      suggestedNextOperatorMove: "Retry candidate",
      usefulnessClass: null,
      usefulnessSummary: null,
    },
    {
      timestamp: "2026-04-06T12:06:00Z",
      clusterLabel: "cluster-a",
      candidateId: "candidate-storage",
      candidateIndex: 2,
      candidateDescription: "Check persistent volume status",
      commandFamily: "kubectl-get",
      status: "success",
      durationMs: 120,
      artifactPath: "/artifacts/run-123-next-check-execution-2.json",
      timedOut: false,
      stdoutTruncated: false,
      stderrTruncated: false,
      outputBytesCaptured: 8192,
      resultClass: "partial-result",
      resultSummary: "Storage metrics captured but some nodes missing data.",
      suggestedNextOperatorMove: "Investigate missing storage metrics.",
      usefulnessClass: "partial",
      usefulnessSummary: "Partially useful - some node metrics were missing.",
    },
    {
      timestamp: "2026-04-06T12:07:00Z",
      clusterLabel: "cluster-b",
      candidateId: "candidate-events",
      candidateIndex: 3,
      candidateDescription: "Get recent events",
      commandFamily: "kubectl-get",
      status: "success",
      durationMs: 45,
      artifactPath: "/artifacts/run-123-next-check-execution-3.json",
      timedOut: false,
      stdoutTruncated: false,
      stderrTruncated: false,
      outputBytesCaptured: 512,
      resultClass: "empty-result",
      resultSummary: "No events found in the specified time window.",
      usefulnessClass: "empty",
      usefulnessSummary: "No useful signal - time window had no events.",
    },
  ],
};

export const makeRunWithOverrides = (overrides: Partial<RunPayload> = {}): RunPayload => {
  const base = JSON.parse(JSON.stringify(sampleRun)) as RunPayload;
  return {
    ...base,
    ...overrides,
  };
};

export const sampleFleet: FleetPayload = {
  runId: "run-123",
  runLabel: "Daily sweep",
  lastRunTimestamp: "2026-04-06T12:00:00Z",
  topProblem: {
    title: "API pressure",
    detail: "Control plane latency is trending upward",
  },
  fleetStatus: {
    ratingCounts: [
      { rating: "Healthy", count: 5 },
      { rating: "Degraded", count: 2 },
    ],
    degradedClusters: ["cluster-a"],
  },
  clusters: [
    {
      label: "cluster-a",
      context: "prod",
      clusterClass: "primary",
      clusterRole: "control",
      baselineCohort: "tier-1",
      controlPlaneVersion: "v1.28.0",
      healthRating: "Degraded",
      warnings: 2,
      nonRunningPods: 3,
      latestRunTimestamp: "2026-04-06T11:58:00Z",
      topTriggerReason: "High CPU",
      drilldownAvailable: true,
      drilldownTimestamp: "2026-04-06T11:59:00Z",
      missingEvidence: ["logs"],
    },
    {
      label: "cluster-b",
      context: "stage",
      clusterClass: "secondary",
      clusterRole: "worker",
      baselineCohort: "tier-2",
      controlPlaneVersion: "v1.27.5",
      healthRating: "Healthy",
      warnings: 0,
      nonRunningPods: 0,
      latestRunTimestamp: "2026-04-06T11:55:00Z",
      topTriggerReason: "Scheduled maintenance",
      drilldownAvailable: false,
      drilldownTimestamp: null,
      missingEvidence: [],
    },
  ],
  proposalSummary: {
    pending: 3,
    total: 5,
    statusCounts: [
      { status: "pending", count: 3 },
      { status: "review", count: 2 },
        ],
    },
};

export const sampleProposals: ProposalsPayload = {
  statusSummary: [
    { status: "pending", count: 2 },
    { status: "review", count: 1 },
  ],
  proposals: [
    {
      proposalId: "critical-01",
      target: "cluster-a",
      status: "pending",
      confidence: "Critical",
      rationale: "Control plane nodes show CPU pressure across multiple zones.",
      expectedBenefit: "Reduce CPU spikes",
      sourceRunId: "run-123",
      latestNote: null,
      lifecycle: [
        { status: "created", timestamp: "2026-04-06T10:00:00Z", note: "Initial detection" },
      ],
      artifacts: [
        { label: "pressure dump", path: "/artifacts/critical-01.json" },
      ],
    },
    {
      proposalId: "medium-01",
      target: "cluster-b",
      status: "pending",
      confidence: "Medium",
      rationale: "Some nodes restarted after kubelet upgrade.",
      expectedBenefit: "Stabilize kubelet",
      sourceRunId: "run-122",
      latestNote: "Awaiting review",
      lifecycle: [
        { status: "created", timestamp: "2026-04-05T22:00:00Z", note: null },
      ],
      artifacts: [],
    },
    {
      proposalId: "low-01",
      target: "cluster-c",
      status: "review",
      confidence: "Low",
      rationale: "Non-critical upgrades are blocking rollout.",
      expectedBenefit: "Improve rollout predictability",
      sourceRunId: "run-121",
      latestNote: "Waiting for final sign-off",
      lifecycle: [
        { status: "created", timestamp: "2026-04-04T09:00:00Z", note: null },
      ],
      artifacts: [],
    },
  ],
};

export const sampleNotifications: NotificationsPayload = {
  notifications: [
    {
      kind: "Warning",
      summary: "Pod restarts rising",
      timestamp: "2026-04-06T11:45:00Z",
      runId: "run-123",
      clusterLabel: "cluster-a",
      context: "prod",
      details: [
        { label: "Pod", value: "api-server-0" },
        { label: "Reason", value: "OOM" },
      ],
      artifactPath: "/artifacts/notification-1.json",
    },
  ],
  total: 1,
  page: 1,
  limit: 50,
  total_pages: 1,
};

export const sampleClusterDetail: ClusterDetailPayload = {
  selectedClusterLabel: "cluster-a",
  selectedClusterContext: "prod",
  assessment: {
    healthRating: "Degraded",
    missingEvidence: ["events", "logs"],
    probableLayer: "control-plane",
    overallConfidence: "High",
    artifactPath: "/artifacts/cluster-a-assessment.json",
    snapshotPath: "/snapshots/cluster-a.json",
  },
  findings: [
    {
      label: "api-server",
      context: "control-plane",
      triggerReasons: ["Latency spike"],
      warningEvents: 2,
      nonRunningPods: 1,
      summaryEntries: [
        { label: "Latency", value: ">2s p99" },
        { label: "Errors", value: "502" },
      ],
      patternDetails: [
        { label: "Zone", value: "us-west-2" },
        { label: "NodePool", value: "control-plane" },
      ],
      rolloutStatus: ["stable"],
      artifactPath: "/artifacts/finding-api-server.json",
    },
  ],
  hypotheses: [
    {
      description: "High control-plane CPU",
      confidence: "Medium",
      probableLayer: "control-plane",
      falsifier: "CPU stays below 60%",
    },
  ],
  nextChecks: [
    {
      description: "Collect kubelet metrics",
      owner: "platform",
      method: "kubectl top nodes",
      evidenceNeeded: ["node CPU", "node memory"],
    },
  ],
  recommendedAction: {
    actionType: "change",
    description: "Throttle background jobs",
    references: ["doc/limit-jobs"],
    safetyLevel: "change-with-caution",
  },
  drilldownAvailability: {
    totalClusters: 2,
    available: 1,
    missing: 1,
    missingClusters: ["cluster-b"],
  },
  drilldownCoverage: [
    {
      label: "cluster-a",
      context: "prod",
      available: true,
      timestamp: "2026-04-06T11:59:00Z",
      artifactPath: "/artifacts/drilldown-cluster-a.json",
    },
  ],
  relatedProposals: [sampleProposals.proposals[0]],
  relatedNotifications: [sampleNotifications.notifications[0]],
  artifacts: [
    { label: "diagnostic bundle", path: "/artifacts/cluster-a-bundle.json" },
  ],
  nextCheckPlan: sampleNextCheckCandidates,
  topProblem: {
    title: "Control plane saturation",
    detail: "gRPC queues are growing",
  },
};

// ============================================================
// Shared test helpers - extracted from multiple test files
// ============================================================

/**
 * Creates a complete mock fetch Response object for tests.
 * Includes headers.get() and text() methods required by api.ts.
 * Use this for inline mocks instead of returning plain objects.
 */
export const makeFetchResponse = (payload: unknown) => {
  const payloadText = JSON.stringify(payload);
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    headers: {
      get: (name: string) => {
        if (name === "Content-Type") return "application/json";
        if (name === "Content-Length") return payloadText.length.toString();
        return null;
      },
    },
    text: () => Promise.resolve(payloadText),
    json: () => Promise.resolve(payload),
  };
};

/**
 * Creates a mock localStorage object for testing.
 * Used in app.test.tsx, panel-selection-binding.test.tsx,
 * queue-workstream-filter.test.tsx, execution-history-filter.test.tsx
 */
export const createStorageMock = () => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => (key in store ? store[key] : null),
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
};

/**
 * Creates a mock fetch function that returns payloads based on URL.
 * @param payloads - Record of URL patterns to return values
 */
export const createFetchMock = (payloads: Record<string, unknown>) =>
  vi.fn((input: RequestInfo) => {
    // Extract URL string robustly from various input types
    const rawUrl =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;

    // Parse URL to extract path and search params
    const parsedUrl = new URL(rawUrl, "http://localhost");
    const pathWithSearch = `${parsedUrl.pathname}${parsedUrl.search}`;
    const pathOnly = parsedUrl.pathname;

    // Look up payload: exact match first, then fallback to base path
    const payload =
      payloads[pathWithSearch] ??
      payloads[rawUrl] ??
      payloads[pathOnly];

    if (!payload) {
      return Promise.reject(new Error(`Unexpected fetch ${rawUrl}`));
    }
    const payloadText = JSON.stringify(payload);
    return Promise.resolve({
      ok: true,
      status: 200,
      statusText: "OK",
      // Include headers object with get method for api.ts debug logging
      headers: {
        get: (name: string) => {
          if (name === "Content-Type") return "application/json";
          if (name === "Content-Length") return payloadText.length.toString();
          return null;
        },
      },
      text: () => Promise.resolve(payloadText),
      json: () => Promise.resolve(payload),
    });
  });

// ============================================================
// Deterministic endpoint queue helper for refresh regression tests
// ============================================================

/**
 * Creates a fetch mock that returns queued responses for specific endpoints.
 * Use this for testing refresh scenarios where the same endpoint needs to return
 * different data at different times.
 *
 * @param queues - Record of endpoint to array of responses. Each call to that endpoint
 *                consumes the next item in the queue. When queue is exhausted, falls back
 *                to defaults if provided.
 * @param defaults - Fallback payloads for unqueued endpoints
 *
 * Example:
 *   createFetchQueueMock({
 *     "/api/runs": [initialRunsList, newerRunsList],
 *   }, {
 *     "/api/run": sampleRun,
 *     "/api/fleet": sampleFleet,
 *   })
 */
export const createFetchQueueMock = (
  queues: Record<string, unknown[]>,
  defaults: Record<string, unknown> = {}
) => {
  const callCounts: Record<string, number> = {};

  return vi.fn((input: RequestInfo) => {
    const url = typeof input === "string" ? input : input.url;
    const base = url.split("?")[0];

    // Check if this endpoint has a queue
    if (base in queues) {
      callCounts[base] = (callCounts[base] ?? 0) + 1;
      const queue = queues[base];
      const callIndex = callCounts[base] - 1;

      // Use the corresponding queue item, or fall back to last item if queue exhausted
      const responseIndex = Math.min(callIndex, queue.length - 1);
      const payload = queue[responseIndex];
      const payloadText = JSON.stringify(payload);

      return Promise.resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        // Include headers object with get method for api.ts debug logging
        headers: {
          get: (name: string) => {
            if (name === "Content-Type") return "application/json";
            if (name === "Content-Length") return payloadText.length.toString();
            return null;
          },
        },
        text: () => Promise.resolve(payloadText),
        json: () => Promise.resolve(payload),
      });
    }

    // Check defaults
    const payload = defaults[url] ?? defaults[base];
    if (!payload) {
      return Promise.reject(new Error(`Unexpected fetch ${url}`));
    }
    const payloadText = JSON.stringify(payload);
    return Promise.resolve({
      ok: true,
      status: 200,
      statusText: "OK",
      // Include headers object with get method for api.ts debug logging
      headers: {
        get: (name: string) => {
          if (name === "Content-Type") return "application/json";
          if (name === "Content-Length") return payloadText.length.toString();
          return null;
        },
      },
      text: () => Promise.resolve(payloadText),
      json: () => Promise.resolve(payload),
    });
  });
};

/**
 * Centralized workflow-critical text strings used in UI assertions.
 * These are fragile to copy changes and should be centralized.
 */
export const UI_STRINGS = {
  // Workflow lane labels (ACT NOW, IMPROVE THE SYSTEM, etc.)
  workflowLanes: {
    safeCandidate: "Safe candidate",
    approvalNeeded: "Approval needed",
    safeToAutomate: "Safe to automate",
    whyNotActionable: "Why not actionable now?",
    why: "Why:",
  },
  // Queue item status labels with counts
  queueStatus: {
    approvalNeeded: "Approval needed",
    awaitingApproval: "Awaiting approval",
    notUsed: "Not used",
    executedSuccess: "Executed (success)",
    safeCandidate: "Safe candidate",
    awaitingApprovalWithCount: (count: number) => `Awaiting approval · ${count}`,
    notUsedWithCount: (count: number) => `Not used · ${count}`,
  },
  // Approval state labels
  approvalStates: {
    approvalStale: "Approval stale",
    orphanedApprovals: "Orphaned approvals",
  },
  // Gating/blocking reasons
  gating: {
    commandNotRecognized: "Command not recognized or too vague",
    matchesDeterministicNextCheck: (checkName: string) =>
      `Matches deterministic next check: ${checkName}`,
  },
  // Promotion messages
  promotion: {
    deterministicPromoted: "Deterministic next check promoted to the queue",
  },
  // Empty states
  emptyState: {
    noEvidenceBasedChecks: "No evidence-based checks are available for this run",
    noEvidenceBasedChecksAvailable: "No evidence-based checks are available",
    notConfiguredForThisRun: "not configured for this run",
    noNextChecksGenerated: "No next checks generated for this run",
    noEvidenceGatheringChecks: "No evidence gathering checks",
    approvalRequiredBeforeExecution: "Approval required before execution",
  },
  // Planner section labels
  planner: {
    plannerCandidates: "Planner candidates",
    reviewNextChecks: "Review next checks",
  },
  // Command preview
  commandPreview: {
    commandPreview: "Command preview",
  },
} as const;

/**
 * Finds the queue panel element and returns a within-scoped query function.
 * @param screen - The screen object from @testing-library/react
 * @returns a within-scoped query function bound to the queue panel element
 */
export const getQueuePanel = async (
  screen: import("@testing-library/react").Screen,
): Promise<ReturnType<typeof within>> => {
  const heading = await screen.findByRole("heading", { name: /Work list/i });
  const queuePanel = heading.closest(".next-check-queue-panel");
  if (!queuePanel) {
    throw new Error("Queue panel is not rendered");
  }
  return within(queuePanel);
};

/**
 * Helper to wait for run data to load and get queue panel scope.
 * This ensures the actual queue content is visible (not just the loading placeholder).
 * Use this instead of getQueuePanel() when testing run-owned queue content.
 * @param screen - The screen object from @testing-library/react
 * @param timeout - Timeout in ms (default 15000)
 * @returns a within-scoped query function bound to the queue panel element
 */
export const getQueuePanelWithRunData = async (
  screen: import("@testing-library/react").Screen,
  timeout: number = 15000,
): Promise<ReturnType<typeof within>> => {
  // Wait for "All workstreams" option to appear - this indicates run data has loaded
  // and the queue panel with workstream filter is rendered
  await screen.findByText("All workstreams", {}, { timeout });
  // Now get the queue panel scope
  return getQueuePanel(screen);
};

/**
 * Helper to wait for run data to load and get execution history panel scope.
 * This ensures the actual execution history content is visible (not just the loading placeholder).
 * Waits for the "Check execution review" heading which appears when run data is loaded.
 * @param screen - The screen object from @testing-library/react
 * @param timeout - Timeout in ms (default 15000)
 * @returns a within-scoped query function bound to the execution history section
 */
export const getExecutionHistoryPanelWithRunData = async (
  screen: import("@testing-library/react").Screen,
  timeout: number = 15000,
): Promise<ReturnType<typeof within>> => {
  // Wait for the heading "Check execution review" which appears when run data is loaded
  // (the placeholder shows "Execution review" which is different)
  const heading = await screen.findByText(/Check execution review/i, {}, { timeout });
  const section = heading.closest("section");
  if (!section) {
    throw new Error("Execution history panel not found");
  }
  return within(section);
};

/**
 * Shared builder for run-123 shape in panel-selection-binding tests.
 * Accepts optional overrides to customize the run payload.
 * Pass { reviewEnrichment: undefined, reviewEnrichmentStatus: undefined } to simulate
 * a run without enrichment data (triggers empty-state rendering).
 */
export const createPanelSelectionRun123 = (
  overrides: Partial<RunPayload> = {}
): RunPayload => {
  const run = makeRunWithOverrides({});

  // Build run-123 specific enrichment with summary "Run 123 enrichment summary"
  const run123Enrichment = {
    status: "success" as const,
    provider: "k8sgpt",
    timestamp: "2026-04-07T12:00:00Z",
    summary: "Run 123 enrichment summary",
    triageOrder: ["cluster-a", "cluster-b"],
    topConcerns: ["Run 123 concern 1", "Run 123 concern 2"],
    evidenceGaps: [],
    nextChecks: [],
    focusNotes: [],
    artifactPath: "/artifacts/run-123-review-enrichment.json",
    errorSummary: null,
    skipReason: null,
  };

  const result: RunPayload = {
    ...run,
    runId: "run-123",
    label: "Run 123",
    reviewEnrichment:
      overrides.reviewEnrichment !== undefined
        ? { ...overrides.reviewEnrichment }
        : run123Enrichment,
    reviewEnrichmentStatus:
      overrides.reviewEnrichmentStatus !== undefined
        ? { ...overrides.reviewEnrichmentStatus }
        : { ...run.reviewEnrichmentStatus },
    providerExecution: {
      autoDrilldown: {
        enabled: true,
        provider: "default",
        maxPerRun: 3,
        eligible: 2,
        attempted: 1,
        succeeded: 1,
        failed: 0,
        skipped: 0,
        unattempted: 1,
        budgetLimited: null,
        notes: null,
      },
      reviewEnrichment: {
        enabled: true,
        provider: "k8sgpt",
        maxPerRun: 1,
        eligible: 1,
        attempted: 1,
        succeeded: 1,
        failed: 0,
        skipped: 0,
        unattempted: 0,
        budgetLimited: null,
        notes: null,
      },
    },
    diagnosticPack: {
      path: "/artifacts/run-123-diagnostic-pack.zip",
      timestamp: "2026-04-07T12:00:00Z",
      label: "Run 123 pack",
    },
    diagnosticPackReview: {
      timestamp: "2026-04-07T12:00:00Z",
      summary: "Run 123 diagnostic review summary",
      majorDisagreements: ["Run 123 disagreement 1"],
      missingChecks: ["Run 123 missing check 1"],
      rankingIssues: [],
      genericChecks: [],
      recommendedNextActions: [],
      driftMisprioritized: false,
      confidence: "high",
      providerStatus: "provider-ok",
      providerSummary: "Run 123 provider summary",
      providerErrorSummary: null,
      providerSkipReason: null,
      providerReview: null,
      artifactPath: "/artifacts/run-123-diagnostic-review.json",
    },
    llmPolicy: {
      autoDrilldown: {
        enabled: true,
        provider: "default",
        maxPerRun: 3,
        usedThisRun: 1,
        successfulThisRun: 1,
        failedThisRun: 0,
        skippedThisRun: 0,
        budgetExhausted: false,
      },
    },
    llmActivity: {
      entries: [
        {
          timestamp: "2026-04-07T12:00:00Z",
          runId: "run-123",
          runLabel: "Run 123",
          clusterLabel: "cluster-a",
          toolName: "k8sgpt",
          provider: "k8sgpt",
          purpose: "review-enrichment",
          status: "success",
          latencyMs: 100,
          artifactPath: "/artifacts/run-123-llm.json",
          summary: "Run 123 LLM activity",
          errorSummary: null,
          skipReason: null,
        },
      ],
      summary: { retainedEntries: 5 },
    },
    deterministicNextChecks:
      overrides.deterministicNextChecks !== undefined
        ? overrides.deterministicNextChecks
        : {
            clusterCount: 1,
            totalNextCheckCount: 1,
            clusters: [
              {
                label: "cluster-a",
                context: "cluster-a",
                topProblem: "Run 123 problem",
                deterministicNextCheckCount: 1,
                deterministicNextCheckSummaries: [
                  {
                    description: "Run 123 deterministic check",
                    workstream: "incident",
                    urgency: "high",
                    isPrimaryTriage: true,
                    method: "kubectl",
                    owner: "platform",
                    whyNow: "Run 123 rationale",
                    evidenceNeeded: ["evidence1"],
                  },
                ],
                drilldownAvailable: true,
                assessmentArtifactPath: "/artifacts/run-123-assessment.json",
                drilldownArtifactPath: "/artifacts/run-123-drilldown.json",
              },
            ],
          },
  };

  // Apply any remaining overrides (e.g., reviewEnrichment: undefined to remove it)
  if ("reviewEnrichment" in overrides && overrides.reviewEnrichment === undefined) {
    delete result.reviewEnrichment;
  }
  if ("reviewEnrichmentStatus" in overrides && overrides.reviewEnrichmentStatus === undefined) {
    delete result.reviewEnrichmentStatus;
  }
  if ("deterministicNextChecks" in overrides && overrides.deterministicNextChecks === undefined) {
    delete result.deterministicNextChecks;
  }

  return result;
};

/**
 * Shared builder for run-122 shape in panel-selection-binding tests.
 * Delegates to createPanelSelectionRun123 with run-122 defaults overridden.
 */
export const createPanelSelectionRun122 = (
  overrides: Partial<RunPayload> = {}
): RunPayload => {
  const run = makeRunWithOverrides({});

  // Build run-122 specific enrichment with summary "Run 122 enrichment summary"
  const run122Enrichment = {
    status: "success" as const,
    provider: "llamacpp",
    timestamp: "2026-04-07T11:00:00Z",
    summary: "Run 122 enrichment summary",
    triageOrder: ["cluster-b"],
    topConcerns: ["Run 122 concern 1"],
    evidenceGaps: [],
    nextChecks: [],
    focusNotes: [],
    artifactPath: "/artifacts/run-122-review-enrichment.json",
    errorSummary: null,
    skipReason: null,
  };

  const result: RunPayload = {
    ...run,
    runId: "run-122",
    label: "Run 122",
    reviewEnrichment:
      overrides.reviewEnrichment !== undefined
        ? { ...overrides.reviewEnrichment }
        : run122Enrichment,
    reviewEnrichmentStatus:
      overrides.reviewEnrichmentStatus !== undefined
        ? { ...overrides.reviewEnrichmentStatus }
        : { ...run.reviewEnrichmentStatus, status: "not-attempted", provider: "llamacpp", reason: "Run 122 not attempted." },
    providerExecution: {
      autoDrilldown: {
        enabled: true,
        provider: "stub",
        maxPerRun: 3,
        eligible: 1,
        attempted: 0,
        succeeded: 0,
        failed: 0,
        skipped: 1,
        unattempted: 0,
        budgetLimited: null,
        notes: null,
      },
      reviewEnrichment: {
        enabled: true,
        provider: "llamacpp",
        maxPerRun: 1,
        eligible: 1,
        attempted: 1,
        succeeded: 0,
        failed: 1,
        skipped: 0,
        unattempted: 0,
        budgetLimited: null,
        notes: null,
      },
    },
    diagnosticPack: {
      path: "/artifacts/run-122-diagnostic-pack.zip",
      timestamp: "2026-04-07T11:00:00Z",
      label: "Run 122 pack",
    },
    diagnosticPackReview: {
      timestamp: "2026-04-07T11:00:00Z",
      summary: "Run 122 diagnostic review summary",
      majorDisagreements: ["Run 122 disagreement 1", "Run 122 disagreement 2"],
      missingChecks: ["Run 122 missing check 1", "Run 122 missing check 2"],
      rankingIssues: [],
      genericChecks: [],
      recommendedNextActions: [],
      driftMisprioritized: true,
      confidence: "low",
      providerStatus: "provider-ok",
      providerSummary: "Run 122 provider summary",
      providerErrorSummary: null,
      providerSkipReason: null,
      providerReview: null,
      artifactPath: "/artifacts/run-122-diagnostic-review.json",
    },
    llmPolicy: {
      autoDrilldown: {
        enabled: false,
        provider: "stub",
        maxPerRun: 3,
        usedThisRun: 0,
        successfulThisRun: 0,
        failedThisRun: 0,
        skippedThisRun: 0,
        budgetExhausted: false,
      },
    },
    llmActivity: {
      entries: [
        {
          timestamp: "2026-04-07T11:00:00Z",
          runId: "run-122",
          runLabel: "Run 122",
          clusterLabel: "cluster-b",
          toolName: "llamacpp",
          provider: "llamacpp",
          purpose: "manual",
          status: "failed",
          latencyMs: 200,
          artifactPath: "/artifacts/run-122-llm.json",
          summary: "Run 122 LLM activity",
          errorSummary: "timeout",
          skipReason: null,
        },
      ],
      summary: { retainedEntries: 3 },
    },
    deterministicNextChecks: undefined,
  };

  // Apply any remaining overrides (e.g., deterministicNextChecks: null to remove it)
  if ("reviewEnrichment" in overrides && overrides.reviewEnrichment === undefined) {
    delete result.reviewEnrichment;
  }
  if ("reviewEnrichmentStatus" in overrides && overrides.reviewEnrichmentStatus === undefined) {
    delete result.reviewEnrichmentStatus;
  }
  if ("deterministicNextChecks" in overrides && overrides.deterministicNextChecks === undefined) {
    delete result.deterministicNextChecks;
  }

  return result;
};
