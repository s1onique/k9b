/**
 * NotificationHistoryTable component.
 * Displays a paginated, filterable table of notification history entries.
 * Supports filtering by kind, cluster, and text search.
 */

import React, { useEffect, useMemo, useState } from "react";
import { artifactUrl, formatTimestamp, relativeRecency, truncateText } from "../utils";
import { fetchNotifications } from "../api";
import type { NotificationEntry } from "../types";
import Pagination from "./Pagination";

// Items per page for notification pagination
const NOTIFICATIONS_PER_PAGE = 50;

// Detail preference keys for notification detail text extraction
const detailPreferenceKeys = ["confidence", "target"];

/**
 * Extracts a human-readable detail text from a notification entry.
 * Prioritizes details with labels containing "confidence" or "target".
 */
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

/**
 * Returns a CSS-friendly class name based on notification kind.
 */
const statusClass = (value: string) => {
  const normalized = value.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  return `status-${normalized}`;
};

/**
 * NotificationHistoryTable displays a filterable, paginated table of notifications.
 */
export const NotificationHistoryTable = () => {
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
    entries.forEach((entry) => {
      const value = entry.kind;
      values.add(value && value.trim() ? value : "unknown");
    });
    return ["all", ...Array.from(values)];
  }, [entries]);
  const clusterOptions = useMemo(() => {
    const values = new Set<string>();
    entries.forEach((entry) => {
      const value = entry.clusterLabel;
      values.add(value && value.trim() ? value : "unknown");
    });
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
      <Pagination
        currentPage={page}
        totalPages={totalPages}
        totalItems={totalResults}
        pageSize={perPage}
        onPageChange={setPage}
        label="Notifications"
      />
    </>
  );
};
