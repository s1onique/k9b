/**
 * IncidentReportCard.tsx
 *
 * Phase 2: Canonical Incident Report Surface
 *
 * Renders the incident report as a first-class selected-run UI surface.
 * Visual design follows the review bar:
 * - Facts (deterministic/evidence-backed)
 * - Inferences (provider-assisted, explicitly labeled)
 * - Unknowns (missing evidence, acknowledged gaps)
 * - Stale evidence warnings
 * - Recommended actions as descriptions
 *
 * Rules enforced:
 * - Facts, inferences, and unknowns are visually distinct.
 * - Stale warnings are prominent but consistent with Solarized Light warning styles.
 * - Provider-assisted inference must not look like deterministic fact.
 * - Null sourceArtifactRefs do not render broken artifact links.
 * - Empty states are honest: "No incident report is available for this run."
 */

import type { IncidentReportPayload, ArtifactLinkRef } from "../../types";
import { artifactUrl } from "../../utils";

// ============================================================================
// Props
// ============================================================================

export interface IncidentReportCardProps {
  /** The incident report payload from the selected run */
  incidentReport: IncidentReportPayload | null | undefined;
}

// ============================================================================
// Helper subcomponents
// ============================================================================

/** Renders a single artifact link as a clickable link */
const ArtifactLinkItem = ({ artifactRef }: { artifactRef: ArtifactLinkRef }) => {
  if (!artifactRef?.path) {
    // Empty sourceArtifactRefs do not render broken links
    return null;
  }
  const url = artifactUrl(artifactRef.path);
  if (!url) {
    return null;
  }
  return (
    <a
      key={artifactRef.path}
      className="artifact-link incident-artifact-link"
      href={url}
      target="_blank"
      rel="noreferrer"
      title={artifactRef.path}
    >
      {artifactRef.label}
    </a>
  );
};

/** Section for facts - deterministic/evidence-backed statements */
const FactsSection = ({ facts }: { facts: IncidentReportPayload["facts"] }) => {
  if (facts.length === 0) {
    return null;
  }
  return (
    <div className="incident-section incident-facts" data-testid="incident-facts">
      <h4 className="incident-section-title">
        <span className="incident-section-icon fact-icon" aria-hidden="true">◆</span>
        Facts
      </h4>
      <ul className="incident-list">
        {facts.map((fact, idx) => (
          <li key={idx} className="incident-item incident-fact-item">
            <span className="incident-statement">{fact.statement}</span>
            <span className="incident-confidence muted tiny">confidence: {fact.confidence}</span>
            {fact.sourceArtifactRefs.length > 0 && (
              <div className="incident-artifacts">
                {fact.sourceArtifactRefs.map((artifactRef) => (
                  <ArtifactLinkItem key={artifactRef.path} artifactRef={artifactRef} />
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
};

/** Section for inferences - provider-assisted, explicitly labeled */
const InferencesSection = ({ inferences }: { inferences: IncidentReportPayload["inferences"] }) => {
  if (inferences.length === 0) {
    return null;
  }
  return (
    <div className="incident-section incident-inferences" data-testid="incident-inferences">
      <h4 className="incident-section-title inference-title">
        <span className="incident-section-icon inference-icon" aria-hidden="true">◇</span>
        Inferences
      </h4>
      <ul className="incident-list">
        {inferences.map((inference, idx) => (
          <li key={idx} className="incident-item incident-inference-item">
            <span className="incident-statement">{inference.statement}</span>
            <div className="inference-basis muted tiny">
              basis: {inference.basis.join(", ")}
              {/* Show provider-assisted badge only when basis includes review-enrichment */}
              {inference.basis.includes("review-enrichment") && (
                <span className="inference-badge">provider-assisted</span>
              )}
            </div>
            <span className="incident-confidence muted tiny">confidence: {inference.confidence}</span>
            {inference.sourceArtifactRefs.length > 0 && (
              <div className="incident-artifacts">
                {inference.sourceArtifactRefs.map((artifactRef) => (
                  <ArtifactLinkItem key={artifactRef.path} artifactRef={artifactRef} />
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
};

/** Section for unknowns - missing evidence, acknowledged gaps */
const UnknownsSection = ({ unknowns }: { unknowns: IncidentReportPayload["unknowns"] }) => {
  if (unknowns.length === 0) {
    return null;
  }
  return (
    <div className="incident-section incident-unknowns" data-testid="incident-unknowns">
      <h4 className="incident-section-title unknown-title">
        <span className="incident-section-icon unknown-icon" aria-hidden="true">?</span>
        Unknowns
      </h4>
      <ul className="incident-list">
        {unknowns.map((unknown, idx) => (
          <li key={idx} className="incident-item incident-unknown-item">
            <span className="incident-statement">{unknown.statement}</span>
            {unknown.whyMissing && (
              <div className="unknown-reason muted tiny">
                why missing: {unknown.whyMissing}
              </div>
            )}
            {unknown.sourceArtifactRefs.length > 0 && (
              <div className="incident-artifacts">
                {unknown.sourceArtifactRefs.map((artifactRef) => (
                  <ArtifactLinkItem key={artifactRef.path} artifactRef={artifactRef} />
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
};

/** Stale evidence warnings - prominent but consistent with Solarized Light warning styles */
const StaleWarnings = ({ warnings }: { warnings: string[] }) => {
  if (warnings.length === 0) {
    return null;
  }
  return (
    <div className="incident-stale-warnings" data-testid="incident-stale-warnings">
      {warnings.map((warning, idx) => (
        <div key={idx} className="incident-stale-warning">
          <span className="stale-warning-icon" aria-hidden="true">⚠</span>
          <span className="stale-warning-text">{warning}</span>
        </div>
      ))}
    </div>
  );
};

/** Recommended actions as descriptions (not links/IDs) */
const RecommendedActions = ({ actions }: { actions: string[] }) => {
  if (actions.length === 0) {
    return null;
  }
  return (
    <div className="incident-recommended-actions" data-testid="incident-recommended-actions">
      <h4 className="incident-section-title">
        <span className="incident-section-icon action-icon" aria-hidden="true">→</span>
        Recommended Actions
      </h4>
      <ul className="incident-action-list">
        {actions.map((action, idx) => (
          <li key={idx} className="incident-action-item">
            {action}
          </li>
        ))}
      </ul>
    </div>
  );
};

// ============================================================================
// Main component
// ============================================================================

export const IncidentReportCard = ({ incidentReport }: IncidentReportCardProps) => {
  // Empty state: honest message when no incident report is available
  if (!incidentReport) {
    return (
      <div className="run-overview-card incident-report-card" data-testid="incident-report-card">
        <div className="preview-card-header">
          <span className="preview-card-icon" aria-hidden="true">⚡</span>
          <h3>Incident report</h3>
        </div>
        <p className="muted tiny">No incident report is available for this run.</p>
      </div>
    );
  }

  const hasContent =
    incidentReport.facts.length > 0 ||
    incidentReport.inferences.length > 0 ||
    incidentReport.unknowns.length > 0 ||
    incidentReport.staleEvidenceWarnings.length > 0 ||
    incidentReport.recommendedActions.length > 0;

  return (
    <div className="run-overview-card incident-report-card" data-testid="incident-report-card">
      {/* Header: icon + title */}
      <div className="preview-card-header">
        <span className="preview-card-icon" aria-hidden="true">⚡</span>
        <h3>Incident report</h3>
        {incidentReport.affectedScope && (
          <span className="incident-affected-scope muted tiny">
            {incidentReport.affectedScope}
          </span>
        )}
      </div>

      {/* Status badge */}
      <div className="incident-status-row">
        <span
          className={`incident-status-badge incident-status-${incidentReport.status}`}
          data-testid="incident-status"
        >
          {incidentReport.status}
        </span>
        {incidentReport.confidence && (
          <span className="incident-confidence-badge muted tiny">
            confidence: {incidentReport.confidence}
          </span>
        )}
      </div>

      {/* Stale evidence warnings - prominent */}
      <StaleWarnings warnings={incidentReport.staleEvidenceWarnings} />

      {/* Main content sections */}
      {hasContent ? (
        <div className="incident-content">
          <FactsSection facts={incidentReport.facts} />
          <InferencesSection inferences={incidentReport.inferences} />
          <UnknownsSection unknowns={incidentReport.unknowns} />
          <RecommendedActions actions={incidentReport.recommendedActions} />
        </div>
      ) : (
        <p className="muted tiny">No incident data available.</p>
      )}

      {/* Source artifact links at bottom if available */}
      {incidentReport.sourceArtifactRefs.length > 0 && (
        <div className="incident-source-links">
          <span className="incident-source-label muted tiny">Sources:</span>
          {incidentReport.sourceArtifactRefs.map((artifactRef) => (
            <ArtifactLinkItem key={artifactRef.path} artifactRef={artifactRef} />
          ))}
        </div>
      )}
    </div>
  );
};
