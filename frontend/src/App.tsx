import { useCallback, useEffect, useMemo, useState } from "react";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import utc from "dayjs/plugin/utc";
import {
  approveNextCheckCandidate,
  executeNextCheckCandidate,
  fetchClusterDetail,
  fetchFleet,
  fetchNotifications,
  fetchProposals,
  fetchRun,
} from "./api";
import type {
  AutoInterpretation,
  ClusterDetailPayload,
  FleetPayload,
  LLMPolicy,
  LLMStats,
  NextCheckExecutionHistoryEntry,
  NextCheckExecutionResponse,
  NextCheckPlanCandidate,
  NotificationDetail,
  NotificationEntry,
  NotificationsPayload,
  ProposalEntry,
  ProposalsPayload,
  ProviderExecution,
  ProviderExecutionBranch,
  ReviewEnrichmentStatus,
  RunPayload,
  NextCheckApprovalResponse,
} from "./types";
import "./index.css";

dayjs.extend(relativeTime);
dayjs.extend(utc);

type SortKey = "proposalId" | "confidence" | "status";

const confidenceWeight = (value: string) => {
  const tier = value.toLowerCase();
  const order = ["critical", "high", "medium", "low"];
  const idx = order.indexOf(tier);
  return idx === -1 ? order.length : idx;
};

const truncateText = (value: string, length = 160) => {
  if (value.length <= length) {
    return value;
  }
  return `${value.slice(0, length).trim()}…`;
};

const FRESHNESS_THRESHOLD_MINUTES = 10;
const relativeRecency = (timestamp: string) => dayjs(timestamp).fromNow();
const isStaleTimestamp = (timestamp: string) =>
  dayjs().diff(timestamp, "minute") >= FRESHNESS_THRESHOLD_MINUTES;

const statusClass = (value: string) => {
  const normalized = value.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  return `status-pill status-pill-${normalized}`;
};

const formatTimestamp = (value: string) => dayjs(value).format("MMM D, YYYY HH:mm [UTC]");

const formatDuration = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) {
    return "—";
  }
  const seconds = Math.max(0, Math.round(value));
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder === 0 ? `${minutes}m` : `${minutes}m ${remainder}s`;
};

const formatLatency = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) {
    return "—";
  }
  return `${Math.round(value)}ms`;
};

const NOTIFICATIONS_PER_PAGE = 50;

const getLlmScopeLabel = (scope?: string | null) =>
  scope === "retained_history" ? "Historical LLM" : "Run LLM";

const buildLlmStatEntries = (stats: LLMStats) => {
  const scopeLabel = getLlmScopeLabel(stats.scope ?? null);
  const lastCallValue = stats.lastCallTimestamp ? relativeRecency(stats.lastCallTimestamp) : "—";
  return [
    { label: `${scopeLabel} calls`, value: String(stats.totalCalls) },
    { label: "OK", value: String(stats.successfulCalls) },
    { label: "Failed", value: String(stats.failedCalls) },
    { label: "P50", value: formatLatency(stats.p50LatencyMs) },
    { label: "P95", value: formatLatency(stats.p95LatencyMs) },
    { label: "P99", value: formatLatency(stats.p99LatencyMs) },
    { label: "Last call", value: lastCallValue },
  ];
};

const renderLlmStatsLine = (stats: LLMStats, modifier?: string) => {
  const entries = buildLlmStatEntries(stats);
  const classNames = [
    "run-header-inline-stats",
    "llm-stats-line",
    "muted",
    "small",
    modifier,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <p className={classNames}>
      {entries.map((stat) => (
        <span key={`${stat.label}-${stat.value}`}>
          <span className="run-stat-label">{stat.label}: </span>
          <strong>{stat.value}</strong>
        </span>
      ))}
    </p>
  );
};

export const AUTOREFRESH_STORAGE_KEY = "dashboard-autorefresh-interval";
const DEFAULT_AUTOREFRESH_SECONDS = 5;
const AUTOREFRESH_OPTIONS = [
  { label: "Off", value: "off" },
  { label: "5s", value: "5" },
  { label: "10s", value: "10" },
  { label: "30s", value: "30" },
  { label: "1m", value: "60" },
  { label: "5m", value: "300" },
];

const readStoredAutoRefreshInterval = () => {
  if (typeof window === "undefined") {
    return DEFAULT_AUTOREFRESH_SECONDS;
  }
  const stored = window.localStorage.getItem(AUTOREFRESH_STORAGE_KEY);
  if (!stored) {
    return DEFAULT_AUTOREFRESH_SECONDS;
  }
  if (stored === "off") {
    return null;
  }
  const parsed = Number(stored);
  if (Number.isNaN(parsed) || parsed <= 0) {
    return DEFAULT_AUTOREFRESH_SECONDS;
  }
  return parsed;
};

const persistAutoRefreshInterval = (value: string) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(AUTOREFRESH_STORAGE_KEY, value);
};

const artifactUrl = (path: string | null) => {
  if (!path) {
    return null;
  }
  return `/artifact?path=${encodeURIComponent(path)}`;
};

const buildClusterRecommendedArtifacts = (detail?: ClusterDetailPayload) => {
  if (!detail) {
    return [];
  }
  const seen = new Map<string, ArtifactLink>();
  const add = (artifact: ArtifactLink | null | undefined) => {
    if (!artifact || !artifact.path) {
      return;
    }
    if (seen.has(artifact.path)) {
      return;
    }
    seen.set(artifact.path, artifact);
  };
  if (detail.assessment?.artifactPath) {
    add({ label: "Assessment artifact", path: detail.assessment.artifactPath });
  }
  detail.artifacts.forEach((artifact) => add(artifact));
  detail.drilldownCoverage.forEach((entry) => {
    if (entry.available && entry.artifactPath) {
      add({ label: `${entry.label} drilldown`, path: entry.artifactPath });
    }
  });
  return Array.from(seen.values()).slice(0, 3);
};

const safetyClass = (value?: string) => {
  const normalized = value ? value.replace(/[^a-z0-9]+/gi, "-").toLowerCase() : "";
  return `safety-pill ${normalized ? `safety-pill-${normalized}` : ""}`.trim();
};

const priorityLabel = (confidence: string) => {
  const normalized = confidence.toLowerCase();
  if (normalized.includes("critical")) return "critical";
  if (normalized.includes("high")) return "high";
  if (normalized.includes("medium")) return "medium";
  if (normalized.includes("low")) return "low";
  return "default";
};

const ALLOWED_MANUAL_FAMILIES = new Set([
  "kubectl-get",
  "kubectl-describe",
  "kubectl-logs",
  "kubectl-get-crd",
]);

type ExecutionResult =
  | NextCheckExecutionResponse
  | {
      status: "error";
      summary: string;
    };

type ApprovalResult = {
  status: "success" | "error";
  summary: string;
  artifactPath?: string | null;
  approvalTimestamp?: string | null;
};

type NextCheckStatusVariant = "safe" | "approval" | "approved" | "duplicate";

const determineNextCheckStatusVariant = (
  candidate: NextCheckPlanCandidate
): NextCheckStatusVariant => {
  if (candidate.duplicateOfExistingEvidence) {
    return "duplicate";
  }
  if (candidate.requiresOperatorApproval) {
    return candidate.approvalStatus === "approved" ? "approved" : "approval";
  }
  return "safe";
};

const nextCheckStatusLabel = (variant: NextCheckStatusVariant) => {
  switch (variant) {
    case "approval":
      return "Approval needed";
    case "approved":
      return "Approved candidate";
    case "duplicate":
      return "Duplicate / already covered";
    default:
      return "Safe candidate";
  }
};

const EvidenceDetails = ({
  title,
  entries,
}: {
  title: string;
  entries: NotificationDetail[];
}) => {
  if (!entries.length) {
    return null;
  }
  return (
    <details className="evidence-details">
      <summary>
        {title} · {entries.length} evidence point{entries.length === 1 ? "" : "s"}
      </summary>
      <ul>
        {entries.map((entry) => (
          <li key={`${entry.label}-${entry.value}`}>
            <strong>{entry.label}:</strong> {entry.value}
          </li>
        ))}
      </ul>
    </details>
  );
};

const normalizeFilterValue = (value: string | null | undefined) =>
  value && value.trim() ? value : "unknown";

const LLMActivityPanel = ({
  activity,
}: {
  activity: RunPayload["llmActivity"] | undefined;
}) => {
  const entries = activity?.entries ?? [];
  const [statusFilter, setStatusFilter] = useState("all");
  const [providerFilter, setProviderFilter] = useState("all");
  const [purposeFilter, setPurposeFilter] = useState("all");
  const [clusterFilter, setClusterFilter] = useState("all");

  const statusOptions = useMemo(() => {
    const values = new Set<string>();
    entries.forEach((entry) => values.add(normalizeFilterValue(entry.status)));
    return ["all", ...Array.from(values)];
  }, [entries]);

  const providerOptions = useMemo(() => {
    const values = new Set<string>();
    entries.forEach((entry) => values.add(normalizeFilterValue(entry.provider)));
    return ["all", ...Array.from(values)];
  }, [entries]);

  const purposeOptions = useMemo(() => {
    const values = new Set<string>();
    entries.forEach((entry) => values.add(normalizeFilterValue(entry.purpose)));
    return ["all", ...Array.from(values)];
  }, [entries]);

  const clusterOptions = useMemo(() => {
    const values = new Set<string>();
    entries.forEach((entry) => values.add(normalizeFilterValue(entry.clusterLabel)));
    return ["all", ...Array.from(values)];
  }, [entries]);

  const filteredEntries = useMemo(() => {
    return entries.filter((entry) => {
      const statusValue = normalizeFilterValue(entry.status);
      const providerValue = normalizeFilterValue(entry.provider);
      const purposeValue = normalizeFilterValue(entry.purpose);
      const clusterValue = normalizeFilterValue(entry.clusterLabel);
      return (
        (statusFilter === "all" || statusValue === statusFilter) &&
        (providerFilter === "all" || providerValue === providerFilter) &&
        (purposeFilter === "all" || purposeValue === purposeFilter) &&
        (clusterFilter === "all" || clusterValue === clusterFilter)
      );
    });
  }, [entries, statusFilter, providerFilter, purposeFilter, clusterFilter]);

  if (!activity) {
    return <p className="muted">LLM activity data is unavailable.</p>;
  }

  const summary = activity.summary;
  const displayCount = filteredEntries.length;
  const availableCount = entries.length;

  return (
    <div>
      <div className="section-head">
        <div>
          <h2>LLM activity</h2>
          <p className="muted small">Provider-assisted provenance from retained artifacts.</p>
        </div>
        <p className="muted small">
          Retained entries: {summary.retainedEntries} · Showing {displayCount} of {availableCount}
        </p>
      </div>
      <div className="llm-activity-filters">
        <label>
          Status
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            {statusOptions.map((option) => (
              <option key={option} value={option}>
                {option === "unknown" ? "Unknown" : option}
              </option>
            ))}
          </select>
        </label>
        <label>
          Provider
          <select value={providerFilter} onChange={(event) => setProviderFilter(event.target.value)}>
            {providerOptions.map((option) => (
              <option key={option} value={option}>
                {option === "unknown" ? "Unknown" : option}
              </option>
            ))}
          </select>
        </label>
        <label>
          Purpose
          <select value={purposeFilter} onChange={(event) => setPurposeFilter(event.target.value)}>
            {purposeOptions.map((option) => (
              <option key={option} value={option}>
                {option === "unknown" ? "Unknown" : option}
              </option>
            ))}
          </select>
        </label>
        <label>
          Cluster
          <select value={clusterFilter} onChange={(event) => setClusterFilter(event.target.value)}>
            {clusterOptions.map((option) => (
              <option key={option} value={option}>
                {option === "unknown" ? "Unknown" : option}
              </option>
            ))}
          </select>
        </label>
      </div>
      {displayCount ? (
        <div className="llm-activity-table-wrapper">
          <table className="llm-activity-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Cluster / Run</th>
                <th>Provider</th>
                <th>Purpose</th>
                <th>Status</th>
                <th>Latency</th>
                <th>Artifact</th>
                <th>Summary</th>
              </tr>
            </thead>
            <tbody>
              {filteredEntries.map((entry, index) => {
                const artifactLink = entry.artifactPath ? artifactUrl(entry.artifactPath) : null;
                const detailText = entry.summary || entry.errorSummary || entry.skipReason || "—";
                return (
                  <tr key={`${entry.timestamp}-${entry.runId}-${index}`}>
                    <td>
                      <strong>{entry.timestamp ? formatTimestamp(entry.timestamp) : "—"}</strong>
                      {entry.timestamp ? (
                        <p className="tiny compact">{relativeRecency(entry.timestamp)}</p>
                      ) : null}
                    </td>
                    <td>
                      <strong>{entry.clusterLabel || "—"}</strong>
                      {entry.runLabel ? (
                        <p className="tiny compact">Run {entry.runLabel}</p>
                      ) : null}
                      {entry.runId ? (
                        <p className="tiny compact">ID {entry.runId}</p>
                      ) : null}
                    </td>
                    <td>
                      <strong>{entry.provider || "—"}</strong>
                      {entry.toolName ? (
                        <p className="tiny compact">Tool {entry.toolName}</p>
                      ) : null}
                    </td>
                    <td>{entry.purpose || "—"}</td>
                    <td>
                      <span className={statusClass(entry.status || "unknown")}>
                        {entry.status || "unknown"}
                      </span>
                    </td>
                    <td>{formatLatency(entry.latencyMs)}</td>
                    <td>
                      {artifactLink ? (
                        <a className="artifact-link" href={artifactLink} target="_blank" rel="noreferrer">
                          View
                        </a>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      <p className="tiny">{truncateText(detailText, 120)}</p>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">No retained LLM activity matches the current filters.</p>
      )}
    </div>
  );
};

const LLMPolicyPanel = ({ policy }: { policy?: LLMPolicy | null }) => {
  const auto = policy?.autoDrilldown;
  const budgetStatus = auto
    ? auto.budgetExhausted === null
      ? "Budget status unknown"
      : auto.budgetExhausted
      ? "Budget exhausted"
      : "Within budget"
    : "Budget status unknown";
  const statusModifier = auto?.enabled ? "status-pill-healthy" : "status-pill-pending";
  return (
    <section className="panel llm-policy-panel" id="llm-policy">
      <div className="section-head">
        <div>
          <h2>LLM policy</h2>
          <p className="muted small">Auto drilldown policy and current usage.</p>
        </div>
        {auto ? (
          <span className={`status-pill ${statusModifier}`}>
            Auto drilldown {auto.enabled ? "enabled" : "disabled"}
          </span>
        ) : null}
      </div>
      {auto ? (
        <div className="llm-policy-grid">
          <div>
            <p className="tiny">Provider</p>
            <strong>{auto.provider || "default"}</strong>
          </div>
          <div>
            <p className="tiny">Budget</p>
            <strong>{auto.maxPerRun} per run</strong>
          </div>
          <div>
            <p className="tiny">Used this run</p>
            <strong>{auto.usedThisRun}</strong>
          </div>
          <div>
            <p className="tiny">Success / Failed / Skipped</p>
            <strong>
              {auto.successfulThisRun} / {auto.failedThisRun} / {auto.skippedThisRun}
            </strong>
          </div>
          <div>
            <p className="tiny">Budget status</p>
            <strong>{budgetStatus}</strong>
          </div>
        </div>
      ) : (
        <p className="muted small">LLM policy data is unavailable.</p>
      )}
    </section>
  );
};

const ReviewEnrichmentList = ({
  title,
  entries,
}: {
  title: string;
  entries: string[];
}) => {
  if (!entries.length) {
    return null;
  }
  return (
    <div className="review-enrichment-item">
      <p className="tiny">{title}</p>
      <ul>
        {entries.map((entry) => (
          <li key={entry}>{entry}</li>
        ))}
      </ul>
    </div>
  );
};

const reviewEnrichmentStatusMessage = (status?: ReviewEnrichmentStatus) => {
  if (!status) {
    return "Provider-assisted review enrichment is not configured for this run.";
  }
  const reason = status.reason;
  switch (status.status) {
    case "policy-disabled":
      return reason || "Review enrichment is disabled in the current configuration.";
    case "provider-missing":
      return reason || "No provider is configured for review enrichment.";
    case "adapter-unavailable":
      return reason || "The configured adapter is not registered for review enrichment.";
    case "awaiting-next-run":
      return (
        reason || "Review enrichment is enabled now, but the latest recorded run predates this setting."
      );
    case "not-attempted":
      return (
        reason || "Review enrichment was enabled for this run, but no artifact was recorded."
      );
    case "unknown":
      return reason || "Review enrichment status cannot be determined for this run.";
    default:
      return (
        reason || "Review enrichment will run once the deterministic review artifact is available."
      );
  }
};

const ReviewEnrichmentPanel = ({
  reviewEnrichment,
  reviewEnrichmentStatus,
}: {
  reviewEnrichment: RunPayload["reviewEnrichment"] | undefined;
  reviewEnrichmentStatus: RunPayload["reviewEnrichmentStatus"] | undefined;
}) => {
  const status =
    reviewEnrichment?.status || reviewEnrichmentStatus?.status || "pending";
  const artifactLink = reviewEnrichment?.artifactPath
    ? artifactUrl(reviewEnrichment.artifactPath)
    : null;
  const runConfigDescription = () => {
    if (!reviewEnrichmentStatus) {
      return null;
    }
    if (reviewEnrichmentStatus.runEnabled === null) {
      return "Run metadata unavailable";
    }
    if (!reviewEnrichmentStatus.runEnabled) {
      return "Run configuration disabled review enrichment";
    }
    const runProvider = reviewEnrichmentStatus.runProvider
      ? ` (${reviewEnrichmentStatus.runProvider})`
      : "";
    return `Run configuration enabled${runProvider}`;
  };
  const providerLabel =
    reviewEnrichmentStatus?.provider ?? reviewEnrichmentStatus?.runProvider;
  const providerDisplay = providerLabel ? `Provider ${providerLabel}` : "Provider unspecified";
  return (
    <section className="panel review-enrichment" id="review-enrichment">
      <div className="section-head">
        <div>
          <p className="eyebrow">Review enrichment</p>
          <h2>Provider-assisted advisory</h2>
        </div>
        <span className={`status-pill ${statusClass(status)}`}>{status}</span>
      </div>
      {reviewEnrichment ? (
        <div className="review-enrichment-body">
          <p className="small">
            {reviewEnrichment.provider
              ? `Provider ${reviewEnrichment.provider}`
              : "Provider unspecified"}{' '}
            ·{' '}
            {reviewEnrichment.timestamp
              ? formatTimestamp(reviewEnrichment.timestamp)
              : "Timestamp unavailable"}
          </p>
          <p className="review-enrichment-summary">
            {reviewEnrichment.summary || "No advisory summary was generated."}
          </p>
          <div className="review-enrichment-grid">
            <ReviewEnrichmentList title="Triage order" entries={reviewEnrichment.triageOrder} />
            <ReviewEnrichmentList title="Top concerns" entries={reviewEnrichment.topConcerns} />
            <ReviewEnrichmentList title="Evidence gaps" entries={reviewEnrichment.evidenceGaps} />
            <ReviewEnrichmentList title="Next checks" entries={reviewEnrichment.nextChecks} />
            <ReviewEnrichmentList title="Focus notes" entries={reviewEnrichment.focusNotes} />
          </div>
          {reviewEnrichment.errorSummary ? (
            <p className="small muted">Error: {reviewEnrichment.errorSummary}</p>
          ) : null}
          {reviewEnrichment.skipReason ? (
            <p className="small muted">Skipped because {reviewEnrichment.skipReason}</p>
          ) : null}
          {artifactLink ? (
            <a className="link" href={artifactLink} target="_blank" rel="noreferrer">
              View enrichment artifact
            </a>
          ) : null}
        </div>
      ) : (
        <div className="review-enrichment-body">
          <p className="small">
            {reviewEnrichmentStatusMessage(reviewEnrichmentStatus)}
          </p>
          <p className="small muted">
            {providerDisplay}
            {runConfigDescription() ? ` · ${runConfigDescription()}` : ""}
          </p>
        </div>
      )}
    </section>
  );
};

const ExecutionLine = ({
  title,
  data,
}: {
  title: string;
  data: ProviderExecutionBranch | undefined | null;
}) => {
  if (!data) {
    return (
      <div className="provider-execution-line">
        <strong>{title}</strong>
        <p className="small muted">Execution data unavailable for this branch.</p>
      </div>
    );
  }
  const segments = [
    data.eligible != null && `eligible ${data.eligible}`,
    `attempted ${data.attempted}`,
    `ok ${data.succeeded}`,
    `failed ${data.failed}`,
    `skipped ${data.skipped}`,
    data.unattempted != null && `unattempted ${data.unattempted}`,
    data.budgetLimited != null && data.budgetLimited > 0 && `budget-limited ${data.budgetLimited}`,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <div className="provider-execution-line">
      <strong>{title}</strong>
      <p className="muted tiny provider-execution-summary">{segments || "No counts yet."}</p>
      {data.notes ? <p className="muted tiny provider-execution-note">{data.notes}</p> : null}
    </div>
  );
};

const ProviderExecutionPanel = ({
  execution,
}: {
  execution: ProviderExecution | undefined | null;
}) => (
  <section className="panel provider-execution" id="provider-execution">
    <div className="section-head">
      <div>
        <p className="eyebrow">Provider execution</p>
        <h2>Provider-assisted branches</h2>
      </div>
      <p className="muted small">
        Counts derived from deterministic artifacts and run-config provenance for each branch.
      </p>
    </div>
    <div className="provider-execution-body">
      <ExecutionLine title="Auto drilldown" data={execution?.autoDrilldown} />
      <ExecutionLine title="Review enrichment" data={execution?.reviewEnrichment} />
    </div>
  </section>
);

const ExecutionHistoryPanel = ({
  history,
}: {
  history: NextCheckExecutionHistoryEntry[];
}) => (
  <section className="panel execution-history-panel" id="execution-history">
    <div className="section-head">
      <div>
        <p className="eyebrow">Execution history</p>
        <h2>Manual next-check runs</h2>
        <p className="muted small">Bounded artifacts recorded after each manual execution.</p>
      </div>
    </div>
    {history.length ? (
      <div className="execution-history-grid">
        {history.map((entry) => {
          const key = `${entry.timestamp}-${entry.artifactPath ?? entry.candidateDescription ?? ""}`;
          const badges = [
            entry.timedOut ? "Timed out" : null,
            entry.stdoutTruncated ? "stdout truncated" : null,
            entry.stderrTruncated ? "stderr truncated" : null,
          ].filter(Boolean) as string[];
          const durationSeconds = entry.durationMs != null ? entry.durationMs / 1000 : null;
          return (
            <article className="execution-history-card" key={key}>
              <header>
                <div>
                  <p className="tiny muted">{relativeRecency(entry.timestamp)}</p>
                  <strong>{formatTimestamp(entry.timestamp)}</strong>
                </div>
                <span className={statusClass(entry.status)}>{entry.status}</span>
              </header>
              <p className="small">
                {entry.candidateDescription || "Candidate description unavailable."}
              </p>
              <div className="execution-history-meta">
                <span>Cluster: {entry.clusterLabel || "unknown"}</span>
                <span>Command: {entry.commandFamily || "—"}</span>
                <span>Duration: {formatDuration(durationSeconds)}</span>
              </div>
              <div className="execution-history-badges">
                {badges.map((badge) => (
                  <span key={badge} className="execution-history-badge">
                    {badge}
                  </span>
                ))}
                {entry.outputBytesCaptured != null && (
                  <span className="execution-history-badge">
                    Captured {entry.outputBytesCaptured} bytes
                  </span>
                )}
              </div>
              {entry.artifactPath ? (
                <a
                  className="link"
                  href={artifactUrl(entry.artifactPath)}
                  target="_blank"
                  rel="noreferrer"
                >
                  View artifact
                </a>
              ) : null}
            </article>
          );
        })}
      </div>
    ) : (
      <p className="muted">Manual next-check executions appear here once recorded.</p>
    )}
  </section>
);

export const ProposalList = ({
  proposals,
  filter,
  sortKey,
  searchText,
  expanded,
  toggle,
}: {
  proposals: ProposalEntry[];
  filter: string;
  sortKey: SortKey;
  searchText: string;
  expanded: Set<string>;
  toggle: (id: string) => void;
}) => {
  const visible = useMemo(() => {
    return proposals
      .filter((entry) => {
        if (filter !== "all" && entry.status !== filter) {
          return false;
        }
        if (!searchText) {
          return true;
        }
        const needle = searchText.toLowerCase();
        return (
          entry.target.toLowerCase().includes(needle) ||
          entry.rationale.toLowerCase().includes(needle)
        );
      })
      .sort((a, b) => {
        if (sortKey === "confidence") {
          return confidenceWeight(a.confidence) - confidenceWeight(b.confidence);
        }
        return a[sortKey].localeCompare(b[sortKey]);
      });
  }, [filter, proposals, searchText, sortKey]);

  if (!visible.length) {
    return <p className="muted">No proposals match the current filters.</p>;
  }

  return (
    <div className="proposal-table">
      {visible.map((proposal) => {
        const expandedEntry = expanded.has(proposal.proposalId);
        const summaryRationale = expandedEntry
          ? proposal.rationale
          : truncateText(proposal.rationale, 180);
        return (
          <article
            className="proposal-row"
            key={proposal.proposalId}
            data-testid="proposal-row"
            data-proposal-id={proposal.proposalId}
          >
            <div className="proposal-row-summary">
              <div>
                <p className="eyebrow compact">{proposal.target}</p>
                <strong>{proposal.proposalId}</strong>
                <div className="proposal-status-line">
                  <span className={statusClass(proposal.status)}>{proposal.status}</span>
                  <span
                    className={`confidence-badge level-${priorityLabel(proposal.confidence)}`}
                  >
                    {proposal.confidence} confidence
                  </span>
                </div>
              </div>
              <div className="proposal-row-actions">
                <span className="small">Run {proposal.sourceRunId}</span>
                <button type="button" className="text-button" onClick={() => toggle(proposal.proposalId)}>
                  {expandedEntry ? "Hide details" : "Show details"}
                </button>
              </div>
            </div>
            <div className={`proposal-row-details ${expandedEntry ? "is-visible" : ""}`}>
              <p className="proposal-rationale">{summaryRationale}</p>
              <div className="proposal-meta-grid">
                <div>
                  <p className="small">Expected benefit</p>
                  <p className="small">{proposal.expectedBenefit}</p>
                </div>
                <div>
                  <p className="small">Lifecycle</p>
                  <div className="lifecycle-row">
                    {proposal.lifecycle.map((step) => (
                      <span className="lifecycle-chip" key={`${step.status}-${step.timestamp}`}>
                        {step.status}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="small">Latest note</p>
                  <p className="small">{proposal.latestNote || "n/a"}</p>
                </div>
              </div>
              <div className="proposal-artifacts">
                {proposal.artifacts.map((artifact) => {
                  const url = artifactUrl(artifact.path);
                  return (
                    url && (
                      <a
                        key={artifact.label}
                        className="artifact-chip"
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {artifact.label}
                      </a>
                    )
                  );
                })}
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
};

const detailPreferenceKeys = ["confidence", "target"];

const getNotificationDetailText = (entry: NotificationEntry) => {
  const priorityDetail = entry.details.find((detail) =>
    detailPreferenceKeys.some((keyword) => detail.label.toLowerCase().includes(keyword))
  );
  const detailEntry = priorityDetail ?? entry.details[0];
  if (detailEntry) {
    return `${detailEntry.label}: ${detailEntry.value}`;
  }
  if (entry.context) {
    return entry.context;
  }
  return "—";
};

const NotificationHistoryTable = () => {
  const [entries, setEntries] = useState<NotificationEntry[]>([]);
  const [totalResults, setTotalResults] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [perPage, setPerPage] = useState(NOTIFICATIONS_PER_PAGE);
  const [kindFilter, setKindFilter] = useState("all");
  const [clusterFilter, setClusterFilter] = useState("all");
  const [searchFilter, setSearchFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const normalizedSearch = searchFilter.trim();

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchNotifications({
          kind: kindFilter !== "all" ? kindFilter : undefined,
          cluster_label: clusterFilter !== "all" ? clusterFilter : undefined,
          search: normalizedSearch || undefined,
          limit: NOTIFICATIONS_PER_PAGE,
          page,
        });
        if (!active) {
          return;
        }
        const limitValue = Math.max(1, response.limit ?? NOTIFICATIONS_PER_PAGE);
        const totalValue = response.total ?? response.notifications.length;
        const pages = response.total_pages && response.total_pages >= 1
          ? response.total_pages
          : Math.max(1, Math.ceil(totalValue / limitValue));
        const requestedPage = response.page ?? page;
        if (requestedPage > pages) {
          setPage(pages);
          return;
        }
        setEntries(response.notifications);
        setTotalResults(totalValue);
        setTotalPages(pages);
        setPerPage(limitValue);
      } catch (err) {
        if (!active) {
          return;
        }
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [kindFilter, clusterFilter, searchFilter, page]);

  const kindOptions = useMemo(() => {
    const values = new Set<string>();
    entries.forEach((entry) => values.add(normalizeFilterValue(entry.kind)));
    return ["all", ...Array.from(values)];
  }, [entries]);
  const clusterOptions = useMemo(() => {
    const values = new Set<string>();
    entries.forEach((entry) => values.add(normalizeFilterValue(entry.clusterLabel)));
    return ["all", ...Array.from(values)];
  }, [entries]);
  const displayStart = entries.length ? (page - 1) * perPage + 1 : 0;
  const displayEnd = entries.length ? (page - 1) * perPage + entries.length : 0;
  const handlePrev = () => setPage((current) => Math.max(1, current - 1));
  const handleNext = () => setPage((current) => Math.min(totalPages, current + 1));
  const formatFilterOption = (value: string) => {
    if (value === "all") {
      return "All";
    }
    if (value === "unknown") {
      return "Unknown";
    }
    return value;
  };
  const summaryText = loading
    ? "Loading notifications…"
    : error
    ? error
    : totalResults
    ? `Showing ${displayStart}–${displayEnd} of ${totalResults}`
    : "No notifications available.";

  return (
    <>
      <div className="notification-table-wrapper">
        <div className="notification-table-controls">
          <label>
            Kind
            <select
              aria-label="Notification kind filter"
              value={kindFilter}
              onChange={(event) => {
                setKindFilter(event.target.value);
                setPage(1);
              }}
            >
              {kindOptions.map((option) => (
                <option key={option} value={option}>
                  {formatFilterOption(option)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Cluster
            <select
              aria-label="Notification cluster filter"
              value={clusterFilter}
              onChange={(event) => {
                setClusterFilter(event.target.value);
                setPage(1);
              }}
            >
              {clusterOptions.map((option) => (
                <option key={option} value={option}>
                  {formatFilterOption(option)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Search
            <input
              type="search"
              aria-label="Notification text search"
              placeholder="Summary or detail"
              value={searchFilter}
              onChange={(event) => {
                setSearchFilter(event.target.value);
                setPage(1);
              }}
            />
          </label>
        </div>
        <p className="muted small notification-summary">
          {summaryText}
          {summaryText.startsWith("Showing") ? ` · ${perPage} per page` : ""}
        </p>
        <div className="notification-table-scroll">
          {loading ? (
            <p className="muted small">Loading notifications…</p>
          ) : error ? (
            <div className="alert alert-inline">{error}</div>
          ) : (
              <table className="notification-table" aria-label="Notification history table">
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Kind</th>
                  <th>Summary</th>
                  <th>Run / Cluster</th>
                  <th>Key detail</th>
                  <th>Artifact</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry, index) => {
                  const detailText = getNotificationDetailText(entry);
                  const artifactLink = entry.artifactPath ? artifactUrl(entry.artifactPath) : null;
                  const runLabels: string[] = [];
                  if (entry.runId) {
                    runLabels.push(`Run ${entry.runId}`);
                  }
                  if (entry.clusterLabel) {
                    runLabels.push(`Cluster ${entry.clusterLabel}`);
                  }
                  const runClusterLabel = runLabels.length ? runLabels.join(" · ") : "—";
                  return (
                    <tr key={`${entry.kind}-${entry.timestamp}-${index}`} data-testid="notification-row">
                      <td>
                        <strong>{formatTimestamp(entry.timestamp)}</strong>
                        <p className="tiny compact">{relativeRecency(entry.timestamp)}</p>
                      </td>
                      <td>
                        <span className={statusClass(entry.kind)}>{entry.kind}</span>
                      </td>
                      <td>
                        <p className="notification-summary">{truncateText(entry.summary, 120)}</p>
                      </td>
                      <td>
                        <p className="tiny compact notification-run-cluster">{runClusterLabel}</p>
                      </td>
                      <td>
                        <p className="notification-detail">{truncateText(detailText, 100)}</p>
                      </td>
                      <td>
                        {artifactLink ? (
                          <a
                            className="artifact-link"
                            href={artifactLink}
                            target="_blank"
                            rel="noreferrer"
                          >
                            View
                          </a>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  );
                })}
                {!entries.length && (
                  <tr>
                    <td colSpan={6} className="muted small">
                      No notifications match the current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <div className="notification-pagination">
        <div className="notification-pagination-controls">
          <button
            type="button"
            onClick={handlePrev}
            disabled={loading || page <= 1}
            aria-label="Previous notifications page"
          >
            Previous
          </button>
          <span>
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            onClick={handleNext}
            disabled={loading || page >= totalPages}
            aria-label="Next notifications page"
          >
            Next
          </button>
        </div>
        <p className="muted small">
          Showing {displayStart}–{displayEnd} of {totalResults}
        </p>
      </div>
    </>
  );
};

const App = () => {
  const [run, setRun] = useState<RunPayload | null>(null);
  const [fleet, setFleet] = useState<FleetPayload | null>(null);
  const [proposals, setProposals] = useState<ProposalsPayload | null>(null);
  const [clusterDetail, setClusterDetail] = useState<ClusterDetailPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [searchText, setSearchText] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("proposalId");
  const [expandedProposals, setExpandedProposals] = useState<Set<string>>(new Set());
  const [activeTab, setActiveTab] = useState<"findings" | "hypotheses" | "checks">("findings");
  const [lastRefresh, setLastRefresh] = useState(() => dayjs());
  const [selectedClusterLabel, setSelectedClusterLabel] = useState<string | null>(null);
  const [clusterDetailExpanded, setClusterDetailExpanded] = useState(false);
  const [autoRefreshInterval, setAutoRefreshInterval] = useState<number | null>(() => {
    return readStoredAutoRefreshInterval();
  });
  const [executionResults, setExecutionResults] = useState<Record<string, ExecutionResult>>({});
  const [executingCandidate, setExecutingCandidate] = useState<string | null>(null);
  const [approvalResults, setApprovalResults] = useState<Record<string, ApprovalResult>>({});
  const [approvingCandidate, setApprovingCandidate] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const [runPayload, fleetPayload, proposalsPayload] = await Promise.all([
        fetchRun(),
        fetchFleet(),
        fetchProposals(),
      ]);
      setRun(runPayload);
      setFleet(fleetPayload);
      setProposals(proposalsPayload);
      if (!selectedClusterLabel) {
        const fallbackLabel = fleetPayload.clusters[0]?.label ?? null;
        if (fallbackLabel) {
          setSelectedClusterLabel(fallbackLabel);
        }
      }
      setLastRefresh(dayjs());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [selectedClusterLabel]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    let timerId: ReturnType<typeof setInterval> | null = null;
    if (autoRefreshInterval) {
      timerId = setInterval(() => {
        refresh();
      }, autoRefreshInterval * 1000);
    }
    return () => {
      if (timerId !== null) {
        clearInterval(timerId);
      }
    };
  }, [autoRefreshInterval, refresh]);

  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        refresh();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [refresh]);

  useEffect(() => {
    if (!selectedClusterLabel) {
      setClusterDetail(null);
      return;
    }
    let active = true;
    const loadDetail = async () => {
      try {
        const detailPayload = await fetchClusterDetail(selectedClusterLabel);
        if (active) {
          setClusterDetail(detailPayload);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : String(err));
        }
      }
    };
    loadDetail();
    return () => {
      active = false;
    };
  }, [selectedClusterLabel, lastRefresh]);

  const statusOptions = useMemo(() => {
    const entries = proposals?.statusSummary.map((entry) => entry.status) ?? [];
    return ["all", ...Array.from(new Set(entries))];
  }, [proposals]);

  const handleToggleProposal = (id: string) => {
    setExpandedProposals((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleClusterSelection = (label: string) => {
    if (!label || label === selectedClusterLabel) {
      return;
    }
    setSelectedClusterLabel(label);
    setClusterDetailExpanded(false);
  };

  const handleAutoRefreshChange = (value: string) => {
    if (value === "off") {
      persistAutoRefreshInterval("off");
      setAutoRefreshInterval(null);
      return;
    }
    const parsed = Number(value);
    if (!Number.isNaN(parsed) && parsed > 0) {
      persistAutoRefreshInterval(value);
      setAutoRefreshInterval(parsed);
    }
  };

  const buildCandidateKey = (candidate: NextCheckPlanCandidate, index: number) =>
    `next-check-${candidate.candidateId ?? candidate.candidateIndex ?? index}-${
      candidate.targetCluster ?? selectedClusterLabel ?? "global"
    }`;

  const isManualExecutionAllowed = (candidate: NextCheckPlanCandidate) => {
    const hasCandidateIdentifier = Boolean(candidate.candidateId?.trim()) || candidate.candidateIndex != null;
    if (!hasCandidateIdentifier) {
      return false;
    }
    if (!candidate.safeToAutomate) {
      return false;
    }
    if (candidate.requiresOperatorApproval && candidate.approvalStatus !== "approved") {
      return false;
    }
    if (candidate.duplicateOfExistingEvidence) {
      return false;
    }
    if (!candidate.suggestedCommandFamily) {
      return false;
    }
    if (!ALLOWED_MANUAL_FAMILIES.has(candidate.suggestedCommandFamily)) {
      return false;
    }
    const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
    if (!targetLabel) {
      return false;
    }
    if (selectedClusterLabel && candidate.targetCluster && candidate.targetCluster !== selectedClusterLabel) {
      return false;
    }
    return true;
  };

  const handleManualExecution = async (candidate: NextCheckPlanCandidate, candidateKey: string) => {
    const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
    const candidateId = candidate.candidateId?.trim() ? candidate.candidateId : undefined;
    const candidateIndex = candidate.candidateIndex;
    if (!targetLabel || (candidateIndex == null && !candidateId)) {
      setExecutionResults((prev) => ({
        ...prev,
        [candidateKey]: { status: "error", summary: "Unable to determine candidate target." },
      }));
      return;
    }
    setExecutingCandidate(candidateKey);
    try {
      const result = await executeNextCheckCandidate({
        candidateId,
        candidateIndex: candidateIndex ?? undefined,
        clusterLabel: targetLabel,
      });
      setExecutionResults((prev) => ({
        ...prev,
        [candidateKey]: result,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Manual execution failed";
      setExecutionResults((prev) => ({
        ...prev,
        [candidateKey]: { status: "error", summary: message },
      }));
    } finally {
      setExecutingCandidate((current) => (current === candidateKey ? null : current));
    }
  };

  const handleApproveCandidate = async (
    candidate: NextCheckPlanCandidate,
    candidateKey: string
  ) => {
    const targetLabel = candidate.targetCluster ?? selectedClusterLabel;
    const candidateId = candidate.candidateId?.trim() ? candidate.candidateId : undefined;
    const candidateIndex = candidate.candidateIndex;
    if (!targetLabel || (candidateIndex == null && !candidateId)) {
      setApprovalResults((prev) => ({
        ...prev,
        [candidateKey]: {
          status: "error",
          summary: "Unable to determine candidate target",
        },
      }));
      return;
    }
    setApprovingCandidate(candidateKey);
    try {
      const result = await approveNextCheckCandidate({
        candidateId,
        candidateIndex: candidateIndex ?? undefined,
        clusterLabel: targetLabel,
      });
      setApprovalResults((prev) => ({
        ...prev,
        [candidateKey]: {
          status: result.status === "success" ? "success" : "error",
          summary:
            result.summary ||
            (result.status === "success" ? "Candidate approved" : "Approval failed"),
          artifactPath: result.artifactPath,
          approvalTimestamp: result.approvalTimestamp,
        },
      }));
      await refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Approval failed";
      setApprovalResults((prev) => ({
        ...prev,
        [candidateKey]: { status: "error", summary: message },
      }));
    } finally {
      setApprovingCandidate((current) => (current === candidateKey ? null : current));
    }
  };

  if (!run || !fleet || !proposals) {
    return (
      <div className="app-shell loading">
        <div>
          <p>Loading operator data…</p>
          {error && <div className="alert">{error}</div>}
        </div>
      </div>
    );
  }

  const runRecency = relativeRecency(run.timestamp);
  const runFresh = !isStaleTimestamp(run.timestamp);
  const runAgeMinutes = Math.floor(dayjs().diff(run.timestamp, "minute"));
  const degradedCount =
    fleet.fleetStatus.ratingCounts.find((entry) => entry.rating.toLowerCase() === "degraded")?.count ?? 0;
  const headerStats = [
    { label: "Last", value: formatDuration(run.runStats.lastRunDurationSeconds) },
    { label: "Runs", value: String(run.runStats.totalRuns) },
    { label: "P50", value: formatDuration(run.runStats.p50RunDurationSeconds) },
    { label: "P95", value: formatDuration(run.runStats.p95RunDurationSeconds) },
    { label: "P99", value: formatDuration(run.runStats.p99RunDurationSeconds) },
  ];
  const runStatsSummary = headerStats.map((stat) => `${stat.label} ${stat.value}`).join(" · ");
  const runSummaryStats = [
    { label: "Clusters", value: run.clusterCount },
    { label: "Degraded", value: degradedCount },
    { label: "Proposals", value: run.proposalCount },
    { label: "Notifications", value: run.notificationCount },
    { label: "Drilldowns", value: run.drilldownCount },
  ];
  const selectedCluster = fleet.clusters.find((cluster) => cluster.label === selectedClusterLabel) ?? null;
  const clusterRecency = selectedCluster?.latestRunTimestamp
    ? relativeRecency(selectedCluster.latestRunTimestamp)
    : null;
  const clusterFresh = selectedCluster ? !isStaleTimestamp(selectedCluster.latestRunTimestamp) : true;
  const autoRefreshSelectValue = autoRefreshInterval ? String(autoRefreshInterval) : "off";
  const autoRefreshStatusText = autoRefreshInterval
    ? `Auto refresh every ${autoRefreshInterval}s`
    : "Auto refresh is off";
  const interpretation: AutoInterpretation | null = clusterDetail?.autoInterpretation || null;
  const recommendedArtifacts = buildClusterRecommendedArtifacts(clusterDetail);
  const clusterTriggerReason =
    selectedCluster?.topTriggerReason ||
    clusterDetail?.findings?.[0]?.triggerReasons?.[0] ||
    clusterDetail?.topProblem?.title ||
    "Trigger reason pending";

  const drilldownAvailability = clusterDetail?.drilldownAvailability;
  const drilldownSummary = drilldownAvailability
    ? `${drilldownAvailability.available}/${drilldownAvailability.totalClusters} drilldown${
        drilldownAvailability.available === 1 ? "" : "s"
      } ready`
    : "Drilldown data pending";
  const recencyTimestamp = selectedCluster?.latestRunTimestamp
    ? formatTimestamp(selectedCluster.latestRunTimestamp)
    : "Awaiting run";
  const planCandidates: NextCheckPlanCandidate[] = clusterDetail?.nextCheckPlan ?? [];
  const planArtifactLink = run.nextCheckPlan?.artifactPath
    ? artifactUrl(run.nextCheckPlan.artifactPath)
    : null;
  const planSummaryText =
    run.nextCheckPlan?.summary ?? "Provider-assisted next-check candidates are available.";
  const planCandidateCountLabel =
    run.nextCheckPlan?.candidateCount != null
      ? `${run.nextCheckPlan.candidateCount} candidate${
          run.nextCheckPlan.candidateCount === 1 ? "" : "s"
        }`
      : `${planCandidates.length} candidate${planCandidates.length === 1 ? "" : "s"}`;
  const planStatusText = run.nextCheckPlan?.status ?? null;
  const executionHistory: NextCheckExecutionHistoryEntry[] = run.nextCheckExecutionHistory ?? [];

  const runLlmStatsLine = renderLlmStatsLine(run.llmStats);
  const historicalLlmStatsLine = run.historicalLlmStats
    ? renderLlmStatsLine(run.historicalLlmStats, "llm-stats-line-historical")
    : null;
  const providerBreakdown = run.llmStats.providerBreakdown
    .map((entry) => `${entry.provider} ${entry.calls} (${entry.failedCalls} failed)`)
    .join(" · ");

  return (
    <div className="app-shell">
      <header className="panel hero compact">
        <div className="hero-content">
          <p className="eyebrow">Operator console</p>
          <h1>Fleet triage cockpit</h1>
          <div className="hero-run">
            <div className="hero-run-identity">
              <p className="eyebrow hero-run-label">Current run</p>
              <div className="hero-run-title">
                <strong>Run {run.label}</strong>
                <span className="hero-run-id">ID {run.runId}</span>
              </div>
            </div>
            <div className="hero-run-freshness">
              <span className={`freshness-pill ${runFresh ? "fresh" : "stale"}`}>
                {runFresh ? "Fresh data" : "Stale data"}
              </span>
              <p className="hero-run-recency small muted">Last run {runRecency}</p>
            </div>
          </div>
        </div>
        <div className="hero-actions">
          <div className="refresh-controls">
            <button type="button" onClick={refresh}>
              Refresh data
            </button>
            <div className="autorefresh-control">
              <label htmlFor="auto-refresh-interval">Auto refresh</label>
              <select
                id="auto-refresh-interval"
                value={autoRefreshSelectValue}
                onChange={(event) => handleAutoRefreshChange(event.target.value)}
              >
                {AUTOREFRESH_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <span className="autorefresh-status muted small">{autoRefreshStatusText}</span>
            </div>
          </div>
          <span className="small">Updated {dayjs(lastRefresh).fromNow()}</span>
        </div>
      </header>
      <nav className="floating-nav">
        <a href="#fleet">Fleet overview</a>
        <a href="#cluster">Cluster detail</a>
        <a href="#proposals">Proposal queue</a>
        <a href="#run-detail">Run summary</a>
        <a href="#execution-history">Execution history</a>
        <a href="#review-enrichment">Review enrichment</a>
        <a href="#llm-activity">LLM activity</a>
        <a href="#llm-policy">LLM policy</a>
        <a href="#notifications">Notifications</a>
      </nav>
      {error && <div className="alert">{error}</div>}
      <section className="panel run-summary" id="run-detail">
        <div className="run-summary-head">
          <div>
            <p className="eyebrow">Run summary</p>
            <h2>{run.label}</h2>
            <p className="muted tiny run-summary-collector">Collector {run.collectorVersion}</p>
          </div>
          <div className="run-summary-freshness">
            <p className="muted small">{formatTimestamp(run.timestamp)}</p>
          </div>
        </div>
        <div className="run-summary-metrics">
          <div className="run-summary-stats">
            {runSummaryStats.map((stat) => (
              <article
                className="run-stat-card"
                key={stat.label}
                aria-label={`${stat.label}: ${stat.value}`}
              >
                <strong>{stat.value}</strong>
                <span>{stat.label}</span>
              </article>
            ))}
          </div>
          <p className="run-duration-summary muted small">{runStatsSummary}</p>
        </div>
        <div className="run-summary-llm">
          <div className="run-summary-llm-heading">
            <p className="eyebrow">LLM telemetry</p>
            <span className="muted tiny">Provider call metrics from artifacts</span>
          </div>
          <div className="llm-current-line">
            {runLlmStatsLine}
            {providerBreakdown && (
              <p className="llm-provider-breakdown muted tiny">Providers: {providerBreakdown}</p>
            )}
          </div>
          {historicalLlmStatsLine && (
            <details className="llm-historical">
              <summary>Retained history stats</summary>
              {historicalLlmStatsLine}
            </details>
          )}
        </div>
        <div className="artifact-strip run-artifacts">
          {run.artifacts.map((artifact) => {
            const url = artifactUrl(artifact.path);
            return (
              url && (
                <a
                  key={artifact.label}
                  className="artifact-link run-artifact-link"
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {artifact.label}
                </a>
              )
            );
          })}
        </div>
        {!runFresh && (
          <div className="alert alert-inline">
            Latest run is {runAgeMinutes} minute{runAgeMinutes === 1 ? "" : "s"} old; ensure the scheduler is running.
          </div>
        )}
      </section>
      <ExecutionHistoryPanel history={executionHistory} />
      <ReviewEnrichmentPanel
        reviewEnrichment={run.reviewEnrichment}
        reviewEnrichmentStatus={run.reviewEnrichmentStatus}
      />
      <ProviderExecutionPanel execution={run.providerExecution} />
      <section className="panel llm-activity-panel" id="llm-activity">
        <LLMActivityPanel activity={run.llmActivity} />
      </section>
      <LLMPolicyPanel policy={run.llmPolicy} />
      <section className="panel" id="fleet">
        <div className="section-head">
          <div>
            <h2>Fleet overview</h2>
            <p className="muted">Top problem: {fleet.topProblem.detail}</p>
          </div>
          <div className="status-badges">
            {fleet.fleetStatus.ratingCounts.map((entry) => (
              <span key={entry.rating} className={statusClass(entry.rating)}>
                {entry.rating} · {entry.count}
              </span>
            ))}
          </div>
        </div>
        <div className="fleet-metrics">
          <article>
            <p className="eyebrow">Pending proposals</p>
            <strong>{fleet.proposalSummary.pending}</strong>
          </article>
          <article>
            <p className="eyebrow">Total proposals</p>
            <strong>{fleet.proposalSummary.total}</strong>
          </article>
        </div>
        <div className="fleet-table">
          <table>
            <thead>
              <tr>
                <th>Cluster</th>
                <th>Rating</th>
                <th>Latest run</th>
                <th>Trigger</th>
                <th>Drilldown</th>
              </tr>
            </thead>
            <tbody>
              {fleet.clusters.map((cluster) => {
                const isSelected = cluster.label === selectedClusterLabel;
                const clusterRowFresh = !isStaleTimestamp(cluster.latestRunTimestamp);
                const clusterRowRecency = relativeRecency(cluster.latestRunTimestamp);
                return (
                  <tr
                    key={cluster.label}
                    className={isSelected ? "row-selected" : undefined}
                    onClick={() => handleClusterSelection(cluster.label)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        handleClusterSelection(cluster.label);
                      }
                    }}
                    tabIndex={0}
                  >
                    <td>
                      <strong>{cluster.label}</strong>
                      <p className="small compact">{cluster.context}</p>
                      <p className="tiny compact">
                        {cluster.clusterClass}/{cluster.clusterRole} · {cluster.baselineCohort}
                      </p>
                    </td>
                    <td>
                      <span className={statusClass(cluster.healthRating)}>{cluster.healthRating}</span>
                    </td>
                    <td>
                      <span className={`recency-pill ${clusterRowFresh ? "fresh" : "stale"}`}>
                        {clusterRowRecency}
                      </span>
                      <p className="small compact">{formatTimestamp(cluster.latestRunTimestamp)}</p>
                    </td>
                    <td>
                      <p className="small">{cluster.topTriggerReason || "Awaiting trigger"}</p>
                    </td>
                    <td>
                      <span className="small">
                        {cluster.drilldownAvailable ? "Ready" : "Missing"}
                      </span>
                      <p className="small compact">{cluster.drilldownTimestamp || "pending"}</p>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel" id="cluster">
        <div className="section-head">
          <h2>Cluster detail</h2>
          <div className="cluster-controls">
            <label>
              Cluster
              <select
                value={selectedClusterLabel ?? ""}
                onChange={(event) => handleClusterSelection(event.target.value)}
              >
                {fleet.clusters.length ? (
                  fleet.clusters.map((cluster) => (
                    <option key={cluster.label} value={cluster.label}>
                      {cluster.label} · {cluster.context}
                    </option>
                  ))
                ) : (
                  <option value="">No clusters configured</option>
                )}
              </select>
            </label>
          </div>
        </div>
        <details
          className="cluster-detail-panel"
          open={clusterDetailExpanded}
          onToggle={(event) => setClusterDetailExpanded(event.currentTarget.open)}
        >
          <summary>
            <div className="cluster-detail-summary">
              <div>
                <p className="eyebrow">Selected cluster</p>
                <strong>
                  {clusterDetail?.selectedClusterLabel || selectedClusterLabel || "Cluster"}
                </strong>
                <p className="small compact">
                  {selectedCluster?.context || clusterDetail?.selectedClusterContext || "Context unknown"}
                </p>
              </div>
              <div className="cluster-detail-summary-meta">
                <span
                  className={statusClass(
                    clusterDetail?.assessment?.healthRating ?? selectedCluster?.healthRating ?? "pending"
                  )}
                >
                  {clusterDetail?.assessment?.healthRating ?? selectedCluster?.healthRating ?? "Pending"}
                </span>
                <span className={`recency-pill ${clusterFresh ? "fresh" : "stale"}`}>
                  {clusterRecency ?? "Awaiting run"}
                </span>
              </div>
            </div>
            <div className="cluster-detail-summary-grid">
              <article className="cluster-summary-card">
                <p className="eyebrow">Current health state</p>
                <span
                  className={statusClass(
                    clusterDetail?.assessment?.healthRating ?? selectedCluster?.healthRating ?? "pending"
                  )}
                >
                  {clusterDetail?.assessment?.healthRating ?? selectedCluster?.healthRating ?? "Pending"}
                </span>
                <p className="small">
                  Missing evidence: {clusterDetail?.assessment?.missingEvidence.join(", ") || "none"}
                </p>
              </article>
              <article className="cluster-summary-card">
                <p className="eyebrow">Top problem</p>
                <strong>{clusterDetail?.topProblem?.title || "Awaiting problem"}</strong>
                <p className="small">
                  {clusterDetail?.topProblem?.detail || "Control plane assessments are still running."}
                </p>
              </article>
              <article className="cluster-summary-card">
                <p className="eyebrow">Trigger / drilldown reason</p>
                <p className="small">{clusterTriggerReason}</p>
                <p className="small">{drilldownSummary}</p>
              </article>
              <article className="cluster-summary-card">
                <p className="eyebrow">Recency & freshness</p>
                <span className={`recency-pill ${clusterFresh ? "fresh" : "stale"}`}>
                  {clusterRecency ?? "Awaiting run"}
                </span>
                <p className="small">{recencyTimestamp}</p>
              </article>
            </div>
            <div className="cluster-detail-summary-artifacts">
              <p className="eyebrow">Recommended artifacts</p>
              {recommendedArtifacts.length ? (
                <div className="artifact-strip">
                  {recommendedArtifacts.map((artifact) => {
                    const url = artifactUrl(artifact.path);
                    return (
                      url && (
                        <a
                          key={`${artifact.label}-${artifact.path}`}
                          className="artifact-link cluster-summary-artifact-link"
                          href={url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {artifact.label}
                        </a>
                      )
                    );
                  })}
                </div>
              ) : (
                <p className="small muted">Artifacts are being captured; check back once collection finishes.</p>
              )}
            </div>
            <p className="small muted">Tap to expand findings, hypotheses, and next checks</p>
          </summary>
          <div className="cluster-detail-body">
            {clusterDetail ? (
              <>
                <div className="cluster-assessment">
                  <div className="cluster-assessment-heading">
                    <div>
                      <p className="eyebrow">Deterministic evidence</p>
                      <h3>{clusterDetail.selectedClusterLabel || "Cluster"}</h3>
                      {clusterDetail.selectedClusterContext ? (
                        <p className="small">{clusterDetail.selectedClusterContext}</p>
                      ) : null}
                    </div>
                  </div>
                  {clusterDetail.assessment ? (
                    <div className="assessment-meta">
                      <span className={statusClass(clusterDetail.assessment.healthRating)}>
                        {clusterDetail.assessment.healthRating}
                      </span>
                      <p className="small">
                        Missing evidence: {clusterDetail.assessment.missingEvidence.join(", ") || "none"}
                      </p>
                      <p className="small">
                        Confidence: {clusterDetail.assessment.overallConfidence || "unknown"}
                      </p>
                      {clusterDetail.assessment.artifactPath ? (
                        <a
                          className="link"
                          href={artifactUrl(clusterDetail.assessment.artifactPath)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          View assessment artifact
                        </a>
                      ) : null}
                    </div>
                  ) : (
                    <p className="muted">No assessment data is available yet.</p>
                  )}
                  {clusterDetail.artifacts.length ? (
                    <div className="artifact-strip cluster-artifacts">
                      {clusterDetail.artifacts.map((artifact) => {
                        const url = artifactUrl(artifact.path);
                        return (
                          url && (
                            <a
                              key={artifact.label}
                              className="artifact-link"
                              href={url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {artifact.label}
                            </a>
                          )
                        );
                      })}
                    </div>
                  ) : null}
                  {clusterDetail.recommendedAction ? (
                    <div className="recommended-action">
                      <p className="eyebrow">Recommended action</p>
                      <strong>{clusterDetail.recommendedAction.description}</strong>
                      <p className="small">
                        Safety:
                        <span className={safetyClass(clusterDetail.recommendedAction.safetyLevel)}>
                          {clusterDetail.recommendedAction.safetyLevel}
                        </span>
                      </p>
                      {clusterDetail.recommendedAction.references.length ? (
                        <p className="small">
                          References: {clusterDetail.recommendedAction.references.join(", ")}
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                </div>
                <div className="provider-assisted-block">
                  <p className="eyebrow">Provider-assisted advisory</p>
                  {interpretation ? (
                    <div className="llm-interpretation-card">
                      <h3>LLM drilldown interpretation</h3>
                      <p className="small">
                        Adapter: {interpretation.adapter} · Status:
                        <span className={statusClass(interpretation.status)}>{interpretation.status}</span>
                      </p>
                      <p className="small">Captured: {formatTimestamp(interpretation.timestamp)}</p>
                      {interpretation.summary ? <p className="small">{interpretation.summary}</p> : null}
                      {interpretation.artifactPath ? (
                        <a className="link" href={artifactUrl(interpretation.artifactPath)!} target="_blank" rel="noreferrer">
                          View interpretation artifact
                        </a>
                      ) : null}
                      {interpretation.errorSummary ? (
                        <p className="small muted">Error: {interpretation.errorSummary}</p>
                      ) : null}
                      {interpretation.skipReason ? (
                        <p className="small muted">Skipped because {interpretation.skipReason}</p>
                      ) : null}
                    </div>
                   ) : (
                     <p className="muted small">LLM drilldown interpretation not available.</p>
                   )}
                 </div>
                {planCandidates.length ? (
                  <div className="next-check-plan">
                    <div className="section-head next-check-plan-head">
                      <div>
                        <h3>Next check plan</h3>
                        <p className="muted small">{planSummaryText}</p>
                        <p className="muted tiny">
                          {planCandidateCountLabel}
                          {planStatusText ? ` · ${planStatusText}` : ""}
                        </p>
                      </div>
                      {planArtifactLink ? (
                        <a
                          className="link"
                          href={planArtifactLink}
                          target="_blank"
                          rel="noreferrer"
                        >
                          View planner artifact
                        </a>
                      ) : null}
                    </div>
                    <div className="next-check-plan-grid">
                        {planCandidates.map((candidate, index) => {
                          const variant = determineNextCheckStatusVariant(candidate);
                          const statusLabel = nextCheckStatusLabel(variant);
                          const statusClassName = `plan-status-pill plan-status-pill-${variant}`;
                          const targetLabel =
                            candidate.targetCluster ||
                            clusterDetail?.selectedClusterLabel ||
                            selectedClusterLabel ||
                            "cluster";
                          const candidateKey = buildCandidateKey(candidate, index);
                          const manualAllowed = isManualExecutionAllowed(candidate);
                          const executionResult = executionResults[candidateKey];
                          const approvalResult = approvalResults[candidateKey];
                          const approvalArtifactPath =
                            approvalResult?.artifactPath ?? candidate.approvalArtifactPath;
                          const approvalArtifactBaseLink =
                            approvalArtifactPath && artifactUrl(approvalArtifactPath);
                          const approvalArtifactLink =
                            approvalArtifactBaseLink && approvalArtifactPath
                              ? `${approvalArtifactBaseLink}#${approvalArtifactPath}`
                              : null;
                          const approvalTimestamp =
                            candidate.approvalTimestamp ?? approvalResult?.approvalTimestamp;
                          const approvalRecency = approvalTimestamp && relativeRecency(approvalTimestamp);
                        return (
                          <article
                            className="next-check-plan-card"
                            key={`${candidate.description}-${index}`}
                          >
                            <header className="next-check-plan-card-header">
                              <div>
                                <p className="tiny muted">
                                  Source: {candidate.sourceReason || "Planner advisory"}
                                </p>
                                <strong>{candidate.description}</strong>
                              </div>
                              <span className={statusClassName}>{statusLabel}</span>
                            </header>
                            <div className="next-check-plan-meta">
                              <div>
                                <p className="tiny">Command family</p>
                                <strong>{candidate.suggestedCommandFamily || "—"}</strong>
                              </div>
                              <div>
                                <p className="tiny">Target</p>
                                <strong>{targetLabel}</strong>
                              </div>
                              <div>
                                <p className="tiny">Expected signal</p>
                                <strong>{candidate.expectedSignal || "—"}</strong>
                              </div>
                              <div>
                                <p className="tiny">Risk level</p>
                                <strong>{candidate.riskLevel}</strong>
                              </div>
                              <div>
                                <p className="tiny">Confidence</p>
                                <strong>{candidate.confidence}</strong>
                              </div>
                            </div>
                            <div className="next-check-plan-flags">
                              <span>
                                Safe to automate: <strong>{candidate.safeToAutomate ? "Yes" : "No"}</strong>
                              </span>
                              <span>
                                Operator approval: <strong>{candidate.requiresOperatorApproval ? "Yes" : "No"}</strong>
                              </span>
                              <span>
                                Estimated cost: <strong>{candidate.estimatedCost || "—"}</strong>
                              </span>
                            </div>
                            {variant === "approval" && (
                              <div className="next-check-approval-actions">
                                <button
                                  type="button"
                                  className="button secondary small"
                                  onClick={() => handleApproveCandidate(candidate, candidateKey)}
                                  disabled={approvingCandidate === candidateKey}
                                >
                                  {approvingCandidate === candidateKey ? "Approving…" : "Approve candidate"}
                                </button>
                                {approvalResult ? (
                                  <p
                                    className={`next-check-approval-note next-check-approval-note-${approvalResult.status}`}
                                  >
                                    {approvalResult.summary}
                                  </p>
                                ) : null}
                                {approvalArtifactLink ? (
                                  <a
                                    className="link"
                                    href={approvalArtifactLink}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    View approval record
                                  </a>
                                ) : null}
                              </div>
                            )}
                            {variant === "approved" && (
                              <div className="next-check-approval-status">
                                <p className="next-check-approval-note next-check-approval-note-success">
                                  Approved {approvalRecency ?? "recently"}.
                                </p>
                                {approvalArtifactLink ? (
                                  <a className="link" href={approvalArtifactLink} target="_blank" rel="noreferrer">
                                    View approval record
                                  </a>
                                ) : null}
                              </div>
                            )}
                            {manualAllowed && (
                              <div className="next-check-manual-actions">
                                <button
                                  type="button"
                                  className="button primary small"
                                  onClick={() => handleManualExecution(candidate, candidateKey)}
                                  disabled={executingCandidate === candidateKey}
                                >
                                  {executingCandidate === candidateKey ? "Running…" : "Run candidate"}
                                </button>
                                {executionResult ? (
                                  <p
                                    className={`next-check-execution next-check-execution-${
                                      executionResult.status === "success" ? "success" : "error"
                                    }`}
                                  >
                                    {executionResult.summary ||
                                      (executionResult.status === "success"
                                        ? "Execution recorded."
                                        : "Execution failed.")}
                                    {executionResult.artifactPath ? (
                                      <>
                                        {" "}
                                        <a
                                          className="link"
                                          href={artifactUrl(executionResult.artifactPath)}
                                          target="_blank"
                                          rel="noreferrer"
                                        >
                                          View artifact
                                        </a>
                                      </>
                                    ) : null}
                                  </p>
                                ) : null}
                              </div>
                            )}
                            {candidate.gatingReason ? (
                              <p className="plan-gating">Gating reason: {candidate.gatingReason}</p>
                            ) : null}
                            {candidate.duplicateEvidenceDescription ? (
                              <p className="plan-gating">
                                Duplicate evidence: {candidate.duplicateEvidenceDescription}
                              </p>
                            ) : null}
                          </article>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
                <div className="tab-list">
                  {[
                    { id: "findings", label: "Findings" },
                    { id: "hypotheses", label: "Hypotheses" },
                    { id: "checks", label: "Next checks" },
                  ].map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      className={`tab ${activeTab === tab.id ? "active" : ""}`}
                      onClick={() => setActiveTab(tab.id as "findings" | "hypotheses" | "checks")}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
                <article className="tab-panel">
                  {activeTab === "findings" && (
                    <div className="finding-list">
                      {clusterDetail.findings.map((finding) => (
                        <article className="finding-card" key={`${finding.label}-${finding.context}`}>
                          <header>
                            <div>
                              <strong>
                                {finding.label || "cluster"} · {finding.context || "n/a"}
                              </strong>
                              <p className="muted">
                                Triggers: {finding.triggerReasons.join(", ") || "none"}
                              </p>
                              <p className="small">
                                Warnings: {finding.warningEvents} · Non-running pods: {finding.nonRunningPods}
                              </p>
                            </div>
                            {finding.artifactPath ? (
                              <a
                                className="link"
                                href={artifactUrl(finding.artifactPath)}
                                target="_blank"
                                rel="noreferrer"
                              >
                                View raw evidence
                              </a>
                            ) : null}
                          </header>
                          <EvidenceDetails title="Summary" entries={finding.summaryEntries} />
                          <EvidenceDetails title="Patterns" entries={finding.patternDetails} />
                          {finding.rolloutStatus.length ? (
                            <p className="small">Rollout status: {finding.rolloutStatus.join(", ")}</p>
                          ) : null}
                        </article>
                      ))}
                    </div>
                  )}
                  {activeTab === "hypotheses" && (
                    <div className="finding-list">
                      {clusterDetail.hypotheses.map((hypothesis) => (
                        <article className="finding-card compact" key={hypothesis.description}>
                          <strong>{hypothesis.description}</strong>
                          <p className="small">
                            Confidence: {hypothesis.confidence} · Layer: {hypothesis.probableLayer}
                          </p>
                          <p className="small">Falsifier: {hypothesis.falsifier}</p>
                        </article>
                      ))}
                    </div>
                  )}
                  {activeTab === "checks" && (
                    <div className="finding-list">
                      {clusterDetail.nextChecks.map((check) => (
                        <article className="finding-card compact" key={check.description}>
                          <strong>{check.description}</strong>
                          <p className="small">
                            Owner: {check.owner} · Method: {check.method}
                          </p>
                          <p className="small">Evidence: {check.evidenceNeeded.join(", ") || "n/a"}</p>
                        </article>
                      ))}
                    </div>
                  )}
                </article>
                <div className="cluster-lists">
                  <div className="drilldown-summary">
                    <h3>Drilldown summary</h3>
                    <p className="small">
                      {clusterDetail.drilldownAvailability.available}/
                        {clusterDetail.drilldownAvailability.totalClusters} ready ·
                      Missing: {clusterDetail.drilldownAvailability.missingClusters.join(", ") || "none"}
                    </p>
                    <div className="drilldown-grid">
                      {clusterDetail.drilldownCoverage.map((entry) => (
                        <article
                          className={`drilldown-card ${entry.available ? "available" : "missing"}`}
                          key={entry.label}
                        >
                          <header>
                            <strong>{entry.label}</strong>
                            <span>{entry.available ? "Ready" : "Missing"}</span>
                          </header>
                          <p className="small">Context: {entry.context}</p>
                          <p className="small">Captured: {entry.timestamp || "pending"}</p>
                          {entry.artifactPath ? (
                            <a
                              className="link"
                              href={artifactUrl(entry.artifactPath)}
                              target="_blank"
                              rel="noreferrer"
                            >
                              View drilldown
                            </a>
                          ) : null}
                        </article>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h3>Related proposals</h3>
                    {clusterDetail.relatedProposals.map((proposal) => (
                      <div className="related-card" key={proposal.proposalId}>
                        <p className="eyebrow">{proposal.proposalId}</p>
                        <p className="small">{proposal.target}</p>
                        <span className={statusClass(proposal.status)}>{proposal.status}</span>
                      </div>
                    ))}
                  </div>
                  <div>
                    <h3>Related notifications</h3>
                    {clusterDetail.relatedNotifications.map((notification) => (
                      <div className="related-card" key={notification.timestamp + notification.kind}>
                        <p className="eyebrow">{notification.kind}</p>
                        <p className="small">{notification.summary}</p>
                        <span className="small">{formatTimestamp(notification.timestamp)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <p className="muted">Loading cluster evidence…</p>
            )}
          </div>
        </details>
      </section>
      <section className="panel" id="proposals">
        <div className="section-head">
          <h2>Proposal queue</h2>
          <div className="proposal-controls">
            <label>
              Status
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                {statusOptions.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Sort
              <select value={sortKey} onChange={(event) => setSortKey(event.target.value as SortKey)}>
                <option value="proposalId">Proposal ID</option>
                <option value="confidence">Confidence</option>
                <option value="status">Status</option>
              </select>
            </label>
            <label>
              Search
              <input
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
                placeholder="Target or rationale"
              />
            </label>
          </div>
        </div>
        <ProposalList
          proposals={proposals.proposals}
          filter={statusFilter}
          sortKey={sortKey}
          searchText={searchText}
          expanded={expandedProposals}
          toggle={handleToggleProposal}
        />
      </section>
      <section className="panel" id="notifications">
        <div className="section-head">
          <h2>Notification history</h2>
          <p className="small">Filtering applies to the entire retained archive.</p>
        </div>
        <NotificationHistoryTable />
      </section>
    </div>
  );
};

export default App;
