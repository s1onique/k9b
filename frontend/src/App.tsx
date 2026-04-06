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
  ClusterDetailPayload,
  FleetPayload,
  NotificationEntry,
  NotificationsPayload,
  ProposalEntry,
  ProposalsPayload,
  RunPayload,
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

const statusClass = (value: string) => {
  const normalized = value.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  return `status-pill status-pill-${normalized}`;
};

const formatTimestamp = (value: string) => dayjs(value).format("MMM D, YYYY HH:mm [UTC]");

const artifactUrl = (path: string | null) => {
  if (!path) {
    return null;
  }
  return `/artifact?path=${encodeURIComponent(path)}`;
};

const ProposalList = ({
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
    <div className="proposal-rail">
      {visible.map((proposal) => {
        const expandedEntry = expanded.has(proposal.proposalId);
        const rationale = expandedEntry
          ? proposal.rationale
          : truncateText(proposal.rationale);
        return (
          <article className="proposal-card" key={proposal.proposalId}>
            <header>
              <div>
                <p className="eyebrow">{proposal.target}</p>
                <h3>{proposal.proposalId}</h3>
              </div>
              <div className="proposal-meta">
                <span className={statusClass(proposal.status)}>{proposal.status}</span>
                <span className="small">Confidence: {proposal.confidence}</span>
              </div>
            </header>
            <p className="proposal-rationale">{rationale}</p>
            <div className="lifecycle-row">
              {proposal.lifecycle.map((step) => (
                <span className="lifecycle-chip" key={`${step.status}-${step.timestamp}`}>
                  {step.status}
                </span>
              ))}
            </div>
            <div className="proposal-actions">
              <p className="small">Benefit: {proposal.expectedBenefit}</p>
              <p className="small">Run: {proposal.sourceRunId}</p>
            </div>
            <div className="proposal-footer">
              {proposal.artifacts.map((artifact) => {
                const url = artifactUrl(artifact.path);
                return url ? (
                  <a key={artifact.label} className="link" href={url} target="_blank" rel="noreferrer">
                    {artifact.label}
                  </a>
                ) : null;
              })}
              <button
                type="button"
                className="text-button"
                onClick={() => toggle(proposal.proposalId)}
              >
                {expandedEntry ? "Show less" : "Expand rationale"}
              </button>
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

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const [runPayload, fleetPayload, proposalsPayload, notificationsPayload, detailPayload] =
        await Promise.all([
          fetchRun(),
          fetchFleet(),
          fetchProposals(),
          fetchNotifications(),
          fetchClusterDetail(),
        ]);
      setRun(runPayload);
      setFleet(fleetPayload);
      setProposals(proposalsPayload);
      setNotifications(notificationsPayload);
      setClusterDetail(detailPayload);
      setLastRefresh(dayjs());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 30_000);
    return () => clearInterval(timer);
  }, [refresh]);

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

  if (!run || !fleet || !proposals || !notifications || !clusterDetail) {
    return <div className="app-shell loading">Loading operator data…</div>;
  }

  const runRecency = dayjs(run.timestamp).fromNow();

  return (
    <div className="app-shell">
      <header className="panel hero">
        <div>
          <p className="eyebrow">Operator console</p>
          <h1>Fleet triage cockpit</h1>
          <p className="muted">Run {run.label} · {run.runId}</p>
          <p className="muted">Last detected {runRecency}</p>
        </div>
        <div className="hero-actions">
          <button type="button" onClick={refresh}>
            Refresh data
          </button>
          <span className="small">Updated {dayjs(lastRefresh).fromNow()}</span>
        </div>
      </header>
      <nav className="floating-nav">
        <a href="#fleet">Fleet overview</a>
        <a href="#cluster">Cluster detail</a>
        <a href="#proposals">Proposal queue</a>
        <a href="#run-detail">Run detail</a>
        <a href="#notifications">Notifications</a>
      </nav>
      {error && <div className="alert">{error}</div>}
      <section className="panel" id="run-detail">
        <div className="section-head">
          <h2>Run summary</h2>
        </div>
        <div className="run-grid">
          <article className="metric-card">
            <p className="eyebrow">Clusters</p>
            <strong>{run.clusterCount}</strong>
          </article>
          <article className="metric-card">
            <p className="eyebrow">Proposals</p>
            <strong>{run.proposalCount}</strong>
          </article>
          <article className="metric-card">
            <p className="eyebrow">Notifications</p>
            <strong>{run.notificationCount}</strong>
          </article>
          <article className="metric-card">
            <p className="eyebrow">Drilldowns</p>
            <strong>{run.drilldownCount}</strong>
          </article>
        </div>
        <div className="artifact-strip">
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
                <th>Class / Role</th>
                <th>Cohort</th>
                <th>Rating</th>
                <th>Latest run</th>
                <th>Top trigger</th>
                <th>Drilldown</th>
              </tr>
            </thead>
            <tbody>
              {fleet.clusters.map((cluster) => (
                <tr key={cluster.label}>
                  <td>
                    <strong>{cluster.label}</strong>
                    <p className="small">{cluster.context}</p>
                  </td>
                  <td>
                    {cluster.clusterClass} / {cluster.clusterRole}
                  </td>
                  <td>{cluster.baselineCohort}</td>
                  <td>
                    <span className={statusClass(cluster.healthRating)}>{cluster.healthRating}</span>
                  </td>
                  <td>{formatTimestamp(cluster.latestRunTimestamp)}</td>
                  <td>{cluster.topTriggerReason || "Awaiting trigger"}</td>
                  <td>
                    <span className="small">
                      {cluster.drilldownAvailable ? "Ready" : "Missing"}
                    </span>
                    <p className="small">{cluster.drilldownTimestamp || "pending"}</p>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel" id="cluster">
        <div className="section-head">
          <h2>Cluster detail</h2>
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
        </div>
        <article className="tab-panel">
          {activeTab === "findings" && (
            <ul>
              {clusterDetail.findings.map((finding) => (
                <li key={`${finding.label}-${finding.context}`}>
                  <strong>
                    {finding.label || "cluster"} · {finding.context || "n/a"}
                  </strong>
                  <p className="small">Triggers: {finding.triggerReasons.join(", ") || "none"}</p>
                  <p className="small">
                    Warnings: {finding.warningEvents} · Non-running pods: {finding.nonRunningPods}
                  </p>
                  <div className="detail-grid">
                    <div>
                      <p className="small">Summary</p>
                      <ul>
                        {finding.summaryEntries.map((entry) => (
                          <li key={`${entry.label}-${entry.value}`}>
                            <strong>{entry.label}:</strong> {entry.value}
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <p className="small">Patterns</p>
                      <ul>
                        {finding.patternDetails.map((entry) => (
                          <li key={`${entry.label}-${entry.value}`}>
                            <strong>{entry.label}:</strong> {entry.value}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {activeTab === "hypotheses" && (
            <ul>
              {clusterDetail.hypotheses.map((hypothesis) => (
                <li key={hypothesis.description}>
                  <strong>{hypothesis.description}</strong>
                  <p className="small">
                    Confidence: {hypothesis.confidence} · Layer: {hypothesis.probableLayer}
                  </p>
                  <p className="small">Falsifier: {hypothesis.falsifier}</p>
                </li>
              ))}
            </ul>
          )}
          {activeTab === "checks" && (
            <ul>
              {clusterDetail.nextChecks.map((check) => (
                <li key={check.description}>
                  <strong>{check.description}</strong>
                  <p className="small">
                    Owner: {check.owner} · Method: {check.method}
                  </p>
                  <p className="small">Evidence: {check.evidenceNeeded.join(", ") || "n/a"}</p>
                </li>
              ))}
            </ul>
          )}
        </article>
        <div className="cluster-lists">
          <div className="drilldown-summary">
            <h3>Drilldown summary</h3>
            <p className="small">
              {clusterDetail.drilldownAvailability.available}/{clusterDetail.drilldownAvailability.totalClusters} ready ·
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
                    <a className="link" href={artifactUrl(entry.artifactPath)} target="_blank" rel="noreferrer">
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
