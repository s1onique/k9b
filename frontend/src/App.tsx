import { useCallback, useEffect, useMemo, useState } from "react";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import utc from "dayjs/plugin/utc";
import {
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
  NotificationDetail,
  NotificationEntry,
  NotificationsPayload,
  ProposalEntry,
  ProposalsPayload,
  RunPayload,
  LLMStats,
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

const priorityLabel = (confidence: string) => {
  const normalized = confidence.toLowerCase();
  if (normalized.includes("critical")) return "critical";
  if (normalized.includes("high")) return "high";
  if (normalized.includes("medium")) return "medium";
  if (normalized.includes("low")) return "low";
  return "default";
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

const NotificationCard = ({ entry }: { entry: NotificationEntry }) => (
  <article className="notification-card">
    <header>
      <span className={statusClass(entry.kind)}>{entry.kind}</span>
      <p className="eyebrow">{entry.summary}</p>
      <span className="small">{formatTimestamp(entry.timestamp)}</span>
    </header>
    <div className="notification-body">
      <p className="small">Run: {entry.runId || "-"} · Cluster: {entry.clusterLabel || "-"}</p>
      <ul>
        {entry.details.map((detail) => (
          <li key={detail.label}>
            <strong>{detail.label}:</strong> {detail.value}
          </li>
        ))}
      </ul>
      {entry.artifactPath ? (
        <a className="link" href={artifactUrl(entry.artifactPath)!} target="_blank" rel="noreferrer">
          View artifact
        </a>
      ) : null}
    </div>
  </article>
);

const App = () => {
  const [run, setRun] = useState<RunPayload | null>(null);
  const [fleet, setFleet] = useState<FleetPayload | null>(null);
  const [proposals, setProposals] = useState<ProposalsPayload | null>(null);
  const [notifications, setNotifications] = useState<NotificationsPayload | null>(null);
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

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const [runPayload, fleetPayload, proposalsPayload, notificationsPayload] = await Promise.all([
        fetchRun(),
        fetchFleet(),
        fetchProposals(),
        fetchNotifications(),
      ]);
      setRun(runPayload);
      setFleet(fleetPayload);
      setProposals(proposalsPayload);
      setNotifications(notificationsPayload);
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

  if (!run || !fleet || !proposals || !notifications) {
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
          <div className="hero-meta">
            <span className="muted small">Run {run.label} · {run.runId}</span>
            <span className={`freshness-pill ${runFresh ? "fresh" : "stale"}`}>
              {runFresh ? "Fresh data" : "Stale data"} · {runRecency}
            </span>
          </div>
          <p className="run-header-inline-stats muted small">{runStatsSummary}</p>
          {runLlmStatsLine}
          {providerBreakdown && (
            <p className="llm-provider-breakdown muted tiny">Providers: {providerBreakdown}</p>
          )}
          {historicalLlmStatsLine}
          <p className="muted">Collector {run.collectorVersion}</p>
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
        <a href="#notifications">Notifications</a>
      </nav>
      {error && <div className="alert">{error}</div>}
      <section className="panel run-summary" id="run-detail">
        <div className="run-summary-head">
          <div>
            <p className="eyebrow">Run summary</p>
            <h2>{run.label}</h2>
          </div>
          <div className="run-summary-freshness">
            <span className={`freshness-pill ${runFresh ? "fresh" : "stale"}`}>
              Last run {runRecency}
            </span>
            <p className="muted small">{formatTimestamp(run.timestamp)}</p>
          </div>
        </div>
        <div className="run-summary-stats">
          {runSummaryStats.map((stat) => (
            <span className="run-stat-pill" key={stat.label} aria-label={`${stat.label}: ${stat.value}`}>
              <span className="run-stat-label">{stat.label}: </span>
              <strong>{stat.value}</strong>
            </span>
          ))}
        </div>
        <div className="artifact-strip run-artifacts">
          {run.artifacts.map((artifact) => {
            const url = artifactUrl(artifact.path);
            return (
              url && (
                <a key={artifact.label} className="artifact-link" href={url} target="_blank" rel="noreferrer">
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
            <p className="small muted">Tap to expand findings, hypotheses, and next checks</p>
          </summary>
          <div className="cluster-detail-body">
            {clusterDetail ? (
              <>
                <div className="cluster-assessment">
                  <div>
                    <p className="eyebrow">Selected cluster</p>
                    <h3>{clusterDetail.selectedClusterLabel || "Cluster"}</h3>
                    {clusterDetail.selectedClusterContext ? (
                      <p className="small">{clusterDetail.selectedClusterContext}</p>
                    ) : null}
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
          <p className="small">Showing {notifications.notifications.length} entries</p>
        </div>
        <div className="notification-grid">
          {notifications.notifications.map((entry) => (
            <NotificationCard entry={entry} key={`${entry.kind}-${entry.timestamp}`} />
          ))}
        </div>
      </section>
    </div>
  );
};

export default App;
