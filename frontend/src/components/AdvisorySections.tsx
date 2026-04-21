/**
 * Advisory Section Components
 *
 * Compact, structured advisory display components for review enrichment.
 * Includes: Top concerns, evidence gaps, next checks, and focus notes.
 */

import React from "react";
import { parseNextCheckEntry } from "../App";
import type { AlertmanagerEvidenceReference } from "../types";

/**
 * Maps used_for values to human-readable labels.
 */
const USED_FOR_LABELS: Record<string, string> = {
  top_concern: "Top concern",
  next_check: "Next check",
  summary: "Summary",
  triage_order: "Triage order",
  focus_note: "Focus note",
};

/**
 * Gets a display label for the used_for field.
 */
const getUsedForLabel = (usedFor: string): string => {
  return USED_FOR_LABELS[usedFor] ?? usedFor.replace(/_/g, " ");
};

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

/**
 * Alert evidence references - provider-assisted references to Alertmanager evidence.
 * Renders bounded, inspectable references that distinguish provider-assisted
 * interpretation from raw alert evidence.
 */
export const AdvisoryAlertEvidenceSection: React.FC<{
  references: AlertmanagerEvidenceReference[];
}> = ({ references }) => {
  if (!references.length) {
    return null;
  }

  return (
    <div className="advisory-lower-section advisory-alert-evidence-section">
      <p className="advisory-lower-section-label advisory-alert-evidence-label">
        Alert evidence used in this review
      </p>
      <p className="advisory-alert-evidence-disclaimer muted tiny">
        Provider-assisted references to Alertmanager evidence
      </p>
      <ul className="advisory-alert-evidence-list">
        {references.map((ref, idx) => {
          const usedForLabel = getUsedForLabel(ref.usedFor);
          return (
            <li key={idx} className="advisory-alert-evidence-row">
              <div className="advisory-alert-evidence-header">
                <span className="advisory-alert-evidence-cluster">{ref.cluster}</span>
                <span className="advisory-alert-evidence-used-for">
                  Used for: {usedForLabel}
                </span>
              </div>
              <div className="advisory-alert-evidence-dimensions">
                {ref.matchedDimensions.map((dim) => (
                  <span key={dim} className="advisory-alert-evidence-dimension">
                    {dim}
                  </span>
                ))}
              </div>
              <p className="advisory-alert-evidence-reason muted tiny">{ref.reason}</p>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default {
  AdvisoryTopConcernsSection,
  AdvisoryEvidenceGapsSection,
  AdvisoryNextChecksSection,
  AdvisoryFocusNotesSection,
  AdvisoryAlertEvidenceSection,
};
