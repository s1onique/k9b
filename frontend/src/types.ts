export type ArtifactLink = {
  label: string;
  path: string;
};

export type ProblemSummary = {
  title: string;
  detail: string;
};

export type StatusCount = {
  status: string;
  count: number;
};

export type ProposalSummary = {
  pending: number;
  total: number;
  statusCounts: StatusCount[];
};

export type RunPayload = {
  runId: string;
  label: string;
  timestamp: string;
  collectorVersion: string;
  clusterCount: number;
  drilldownCount: number;
  proposalCount: number;
  externalAnalysisCount: number;
  notificationCount: number;
  artifacts: ArtifactLink[];
  runStats: RunStats;
  llmStats: LLMStats;
  historicalLlmStats?: LLMStats | null;
  llmActivity: LLMActivity;
  llmPolicy?: LLMPolicy | null;
  reviewEnrichment?: ReviewEnrichment | null;
  reviewEnrichmentStatus?: ReviewEnrichmentStatus | null;
};

export type RunStats = {
  lastRunDurationSeconds: number | null;
  totalRuns: number;
  p50RunDurationSeconds: number | null;
  p95RunDurationSeconds: number | null;
  p99RunDurationSeconds: number | null;
};

export type LLMProviderBreakdown = {
  provider: string;
  calls: number;
  failedCalls: number;
};

export type LLMStats = {
  totalCalls: number;
  successfulCalls: number;
  failedCalls: number;
  lastCallTimestamp: string | null;
  p50LatencyMs: number | null;
  p95LatencyMs: number | null;
  p99LatencyMs: number | null;
  providerBreakdown: LLMProviderBreakdown[];
  scope?: string;
};

export type AutoDrilldownPolicy = {
  enabled: boolean;
  provider: string;
  maxPerRun: number;
  usedThisRun: number;
  successfulThisRun: number;
  failedThisRun: number;
  skippedThisRun: number;
  budgetExhausted: boolean | null;
};

export type LLMPolicy = {
  autoDrilldown?: AutoDrilldownPolicy | null;
};

export type LLMActivityEntry = {
  timestamp: string | null;
  runId: string | null;
  runLabel: string | null;
  clusterLabel: string | null;
  toolName: string | null;
  provider: string | null;
  purpose: string | null;
  status: string | null;
  latencyMs: number | null;
  artifactPath: string | null;
  summary: string | null;
  errorSummary: string | null;
  skipReason: string | null;
};

export type LLMActivitySummary = {
  retainedEntries: number;
};

export type LLMActivity = {
  entries: LLMActivityEntry[];
  summary: LLMActivitySummary;
};

export type ClusterSummary = {
  label: string;
  context: string;
  clusterClass: string;
  clusterRole: string;
  baselineCohort: string;
  controlPlaneVersion: string;
  healthRating: string;
  warnings: number;
  nonRunningPods: number;
  latestRunTimestamp: string;
  topTriggerReason: string | null;
  drilldownAvailable: boolean;
  drilldownTimestamp: string | null;
  missingEvidence: string[];
};

export type FleetPayload = {
  runId: string;
  runLabel: string;
  lastRunTimestamp: string;
  topProblem: ProblemSummary;
  fleetStatus: {
    ratingCounts: { rating: string; count: number }[];
    degradedClusters: string[];
  };
  clusters: ClusterSummary[];
  proposalSummary: ProposalSummary;
};

export type LifecycleEntry = {
  status: string;
  timestamp: string;
  note: string | null;
};

export type ProposalEntry = {
  proposalId: string;
  target: string;
  status: string;
  confidence: string;
  rationale: string;
  expectedBenefit: string;
  sourceRunId: string;
  latestNote: string | null;
  lifecycle: LifecycleEntry[];
  artifacts: ArtifactLink[];
};

export type ProposalsPayload = {
  statusSummary: StatusCount[];
  proposals: ProposalEntry[];
};

export type NotificationDetail = {
  label: string;
  value: string;
};

export type NotificationEntry = {
  kind: string;
  summary: string;
  timestamp: string;
  runId: string | null;
  clusterLabel: string | null;
  context: string | null;
  details: NotificationDetail[];
  artifactPath: string | null;
};

export type NotificationsPayload = {
  notifications: NotificationEntry[];
};

export type FindingEntry = {
  label: string | null;
  context: string | null;
  triggerReasons: string[];
  warningEvents: number;
  nonRunningPods: number;
  summaryEntries: NotificationDetail[];
  patternDetails: NotificationDetail[];
  rolloutStatus: string[];
  artifactPath: string | null;
};

export type HypothesisEntry = {
  description: string;
  confidence: string;
  probableLayer: string;
  falsifier: string;
};

export type NextCheckEntry = {
  description: string;
  owner: string;
  method: string;
  evidenceNeeded: string[];
};

export type RecommendedAction = {
  actionType: string;
  description: string;
  references: string[];
  safetyLevel: string;
};

export type DrilldownCoverage = {
  label: string;
  context: string;
  available: boolean;
  timestamp: string | null;
  artifactPath: string | null;
};

export type DrilldownSummary = {
  totalClusters: number;
  available: number;
  missing: number;
  missingClusters: string[];
};

export type ClusterDetailPayload = {
  selectedClusterLabel: string | null;
  selectedClusterContext: string | null;
  assessment:
    | {
        healthRating: string;
        missingEvidence: string[];
        probableLayer: string | null;
        overallConfidence: string | null;
        artifactPath: string | null;
        snapshotPath: string | null;
      }
    | null;
  findings: FindingEntry[];
  hypotheses: HypothesisEntry[];
  nextChecks: NextCheckEntry[];
  recommendedAction: RecommendedAction | null;
  drilldownAvailability: DrilldownSummary;
  drilldownCoverage: DrilldownCoverage[];
  relatedProposals: ProposalEntry[];
  relatedNotifications: NotificationEntry[];
  artifacts: ArtifactLink[];
  autoInterpretation: AutoInterpretation | null;
  topProblem: ProblemSummary;
};

export type AutoInterpretation = {
  adapter: string;
  status: string;
  summary: string | null;
  timestamp: string;
  artifactPath: string | null;
  provider: string | null;
  durationMs: number | null;
  payload: Record<string, unknown> | null;
  errorSummary: string | null;
  skipReason: string | null;
};

export type ReviewEnrichment = {
  status: string;
  provider: string | null;
  timestamp: string | null;
  summary: string | null;
  triageOrder: string[];
  topConcerns: string[];
  evidenceGaps: string[];
  nextChecks: string[];
  focusNotes: string[];
  artifactPath: string | null;
  errorSummary: string | null;
  skipReason: string | null;
};

export type ReviewEnrichmentStatus = {
  status: string;
  reason: string | null;
  provider: string | null;
  policyEnabled: boolean;
  providerConfigured: boolean;
  adapterAvailable: boolean | null;
};
