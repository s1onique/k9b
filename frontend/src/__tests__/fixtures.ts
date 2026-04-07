import type {
  ClusterDetailPayload,
  FleetPayload,
  NotificationsPayload,
  ProposalsPayload,
  RunPayload,
} from "../types";

export const sampleRun: RunPayload = {
  runId: "run-123",
  label: "Daily sweep",
  timestamp: "2026-04-06T12:00:00Z",
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
      { provider: "k8sgpt", calls: 3, failedCalls: 1 },
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
  topProblem: {
    title: "Control plane saturation",
    detail: "gRPC queues are growing",
  },
};
