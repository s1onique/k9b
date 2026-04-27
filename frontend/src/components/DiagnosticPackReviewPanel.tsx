/**
 * DiagnosticPackReviewPanel
 *
 * Displays automated review insights for diagnostic pack results including
 * provider status, confidence, summary, and categorized review lists.
 */

import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";

import type { RunPayload } from "../types";
import { DiagnosticPackReviewList } from "./DiagnosticPackReviewList";

/**
 * Get CSS class for status pill based on provider status value.
 */
const statusClass = (value: string): string => {
  if (value.toLowerCase().includes("error") || value.toLowerCase().includes("fail")) {
    return "status-pill-error";
  }
  if (value.toLowerCase().includes("success") || value.toLowerCase().includes("complete")) {
    return "status-pill-success";
  }
  if (value.toLowerCase().includes("pending") || value.toLowerCase().includes("processing")) {
    return "status-pill-warning";
  }
  return "status-pill-neutral";
};

/**
 * Format timestamp to human-readable format.
 */
const formatTimestamp = (value: string): string =>
  dayjs.utc(value).format("MMM D, YYYY HH:mm [UTC]");

/**
 * Generate artifact URL from path.
 */
const artifactUrl = (path: string | null): string | null => {
  if (!path) return null;
  const base = import.meta.env.VITE_ARTIFACT_BASE_URL || "";
  return `${base}${path}`;
};

export interface DiagnosticPackReviewPanelProps {
  review: RunPayload["diagnosticPackReview"] | undefined;
}

export const DiagnosticPackReviewPanel = ({
  review,
}: DiagnosticPackReviewPanelProps) => {
  if (!review) {
    return null;
  }
  const artifactLink = review.artifactPath ? artifactUrl(review.artifactPath) : null;
  const providerStatus = review.providerStatus || "Status unavailable";
  const hasProviderDetails = review.providerSummary || review.providerErrorSummary || review.providerSkipReason;
  return (
    <section className="panel diagnostic-pack-review" id="diagnostic-pack-review">
      <div className="section-head">
        <h2>Diagnostic pack review</h2>
        <span className={`status-pill ${statusClass(providerStatus)}`}>
          {providerStatus}
        </span>
      </div>
      <p className="muted tiny">
        {review.timestamp ? formatTimestamp(review.timestamp) : "Timestamp unavailable"}
      </p>
      {review.summary ? <p className="diagnostic-pack-summary">{review.summary}</p> : null}
      {review.confidence ? (
        <p className="muted tiny">Confidence: {review.confidence}</p>
      ) : null}
      {hasProviderDetails ? (
        <div className="diagnostic-pack-provider">
          {review.providerSummary ? (
            <p className="muted small">{review.providerSummary}</p>
          ) : null}
          {review.providerErrorSummary ? (
            <p className="muted small">Error: {review.providerErrorSummary}</p>
          ) : null}
          {review.providerSkipReason ? (
            <p className="muted small">Skipped because {review.providerSkipReason}</p>
          ) : null}
        </div>
      ) : null}
      {review.driftMisprioritized ? (
        <p className="muted tiny">
          Provider flagged suspected drift misprioritization. Review the assigned check order.
        </p>
      ) : null}
      <div className="diagnostic-pack-review-grid">
        <DiagnosticPackReviewList title="Major disagreements" entries={review.majorDisagreements} />
        <DiagnosticPackReviewList title="Missing checks" entries={review.missingChecks} />
        <DiagnosticPackReviewList title="Ranking issues" entries={review.rankingIssues} />
        <DiagnosticPackReviewList
          title="Recommended next actions"
          entries={review.recommendedNextActions}
        />
      </div>
      {artifactLink ? (
        <a className="link" href={artifactLink} target="_blank" rel="noreferrer">
          View diagnostic pack review artifact
        </a>
      ) : null}
    </section>
  );
};
