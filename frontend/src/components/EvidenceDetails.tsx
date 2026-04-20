/**
 * Evidence Details Component
 *
 * Renders a collapsible details element showing evidence entries with label/value pairs.
 * Shows count and returns null for empty entries.
 */

import React from "react";
import type { NotificationDetail } from "../types";

export interface EvidenceDetailsProps {
  /** Title for the summary header */
  title: string;
  /** Array of label/value evidence entries to display */
  entries: NotificationDetail[];
}

export const EvidenceDetails: React.FC<EvidenceDetailsProps> = ({ title, entries }) => {
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

export default EvidenceDetails;