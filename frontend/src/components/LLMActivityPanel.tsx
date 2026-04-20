/**
 * LLMActivityPanel component.
 * Displays a table of LLM activity entries with filtering capabilities.
 * Shows retained LLM activity from artifacts with provider-assisted provenance.
 */

import React, { useMemo, useState } from "react";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import utc from "dayjs/plugin/utc";
import type { RunPayload } from "../types";

dayjs.extend(relativeTime);
dayjs.extend(utc);

// ==========================================================================
// Helper functions (duplicated from App.tsx for component portability)
// ==========================================================================

/**
 * Normalize a filter value, returning "unknown" for empty/null values.
 */
const normalizeFilterValue = (value: string | null | undefined) =>
  value && value.trim() ? value : "unknown";

const truncateText = (value: string, length = 160) => {
  if (value.length <= length) {
    return value;
  }
  return `${value.slice(0, length).trim()}…`;
};

const relativeRecency = (timestamp: string) => dayjs(timestamp).fromNow();

const statusClass = (value: string) => {
  const normalized = value.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  return `status-pill status-pill-${normalized}`;
};

const formatTimestamp = (value: string) => dayjs.utc(value).format("MMM D, YYYY HH:mm [UTC]");

const formatLatency = (value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) {
    return "—";
  }
  return `${Math.round(value)}ms`;
};

const artifactUrl = (path: string | null) => {
  if (!path) {
    return null;
  }
  return `/artifact?path=${encodeURIComponent(path)}`;
};

export interface LLMActivityPanelProps {
  activity: RunPayload["llmActivity"] | undefined;
}

/**
 * LLMActivityPanel displays LLM activity entries in a filterable table.
 */
export const LLMActivityPanel = ({
  activity,
}: LLMActivityPanelProps) => {
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
    <section className="panel llm-activity-panel" id="llm-activity">
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
    </section>
  );
};
