/**
 * Diagnostic Pack Review List Component
 *
 * Renders a compact list of diagnostic pack review entries with preview limit.
 * Shows up to 3 entries with "...and N more" for additional items.
 */

import React from "react";

export interface DiagnosticPackReviewListProps {
  /** Title for the list */
  title: string;
  /** Array of entry strings to display */
  entries: string[];
}

export const DiagnosticPackReviewList: React.FC<DiagnosticPackReviewListProps> = ({ title, entries }) => {
  if (!entries.length) {
    return null;
  }
  const previewLimit = 3;
  const hasMore = entries.length > previewLimit;
  const visible = entries.slice(0, previewLimit);
  return (
    <div className="diagnostic-pack-review-list">
      <p className="tiny">
        {title} · {entries.length}
      </p>
      <ul>
        {visible.map((entry) => (
          <li key={entry}>{entry}</li>
        ))}
        {hasMore && <li className="muted">…and {entries.length - previewLimit} more</li>}
      </ul>
    </div>
  );
};

export default DiagnosticPackReviewList;