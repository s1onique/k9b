/**
 * Advisory Section Components
 *
 * Compact, structured advisory display components for review enrichment.
 * Includes: Top concerns, evidence gaps, next checks, and focus notes.
 */

import React from "react";
import { parseNextCheckEntry } from "../App";

/** Top concerns - compact concern rows with left accent */
export const AdvisoryTopConcernsSection: React.FC<{ concerns: string[] }> = ({ concerns }) => {
  if (!concerns.length) {
    return null;
  }
  return (
    <div className="advisory-lower-section advisory-concerns-section">
      <p className="advisory-lower-section-label">Top concerns</p>
      <ul className="advisory-concerns-list">
        {concerns.map((concern) => (
          <li key={concern} className="advisory-concern-row">
            {concern}
          </li>
        ))}
      </ul>
    </div>
  );
};

/** Evidence gaps - uncertainty-oriented rows with gap marker */
export const AdvisoryEvidenceGapsSection: React.FC<{ gaps: string[] }> = ({ gaps }) => {
  if (!gaps.length) {
    return null;
  }
  return (
    <div className="advisory-lower-section advisory-gaps-section">
      <p className="advisory-lower-section-label advisory-gaps-label">Evidence gaps</p>
      <ul className="advisory-gaps-list">
        {gaps.map((gap) => (
          <li key={gap} className="advisory-gap-row">
            <span className="advisory-gap-marker" aria-hidden="true">?</span>
            <span>{gap}</span>
          </li>
        ))}
      </ul>
    </div>
  );
};

/** Next checks - action rows with parsed intent, cluster badge, and command preview */
export const AdvisoryNextChecksSection: React.FC<{ checks: string[] }> = ({ checks }) => {
  if (!checks.length) {
    return null;
  }
  const parsed = checks.map(parseNextCheckEntry);
  return (
    <div className="advisory-lower-section advisory-next-checks-section">
      <p className="advisory-lower-section-label">Next checks</p>
      <ul className="advisory-checks-list">
        {parsed.map((check, idx) => (
          <li key={checks[idx]} className="advisory-check-row">
            <span className="advisory-check-intent">{check.intent || checks[idx]}</span>
            {check.targetCluster && (
              <span className="advisory-check-cluster">{check.targetCluster}</span>
            )}
            {check.commandPreview && (
              <code className="advisory-check-cmd">{check.commandPreview}</code>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
};

/** Focus notes - demoted secondary guidance hints */
export const AdvisoryFocusNotesSection: React.FC<{ notes: string[] }> = ({ notes }) => {
  if (!notes.length) {
    return null;
  }
  return (
    <div className="advisory-lower-section advisory-focus-notes-section">
      <p className="advisory-lower-section-label advisory-focus-notes-label">Focus guidance</p>
      <ul className="advisory-focus-notes-list">
        {notes.map((note) => (
          <li key={note} className="advisory-focus-note-row muted">
            {note}
          </li>
        ))}
      </ul>
    </div>
  );
};

export default {
  AdvisoryTopConcernsSection,
  AdvisoryEvidenceGapsSection,
  AdvisoryNextChecksSection,
  AdvisoryFocusNotesSection,
};