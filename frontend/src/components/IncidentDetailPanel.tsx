/**
 * IncidentDetailPanel Component - Read-only incident detail view.
 * Redesigned with war room layout for incident-first experience.
 *
 * Hard constraints: NO remediation, mutation, LLM calls, tool invocation, persistence, or write actions.
 * Uses: latest_snapshot_bundle_id, review_packet object.
 */

import type { IncidentDetailPayload } from "../api";
import { IncidentAutomaticDiagnosisLoopCard } from "./IncidentAutomaticDiagnosisLoopCard";
import { IncidentAutomaticDiagnosisReviewPanel } from "./IncidentAutomaticDiagnosisReviewPanel";
import { IncidentDiagnosisLoopPanel } from "./IncidentDiagnosisLoopPanel";
import { IncidentOnePassDiagnosisPanel } from "./IncidentOnePassDiagnosisPanel";
import { EvidenceArtifactsSection } from "./EvidenceArtifactsSection";
import { IncidentWarRoomHeader } from "./IncidentWarRoomHeader";
import { ReviewPacketSection } from "./ReviewPacketSection";
import { SignalsSection } from "./SignalsSection";
import { EvidenceLinksSection } from "./EvidenceLinksSection";
import { TimelineSection } from "./TimelineSection";
import { EvidenceNeededSection } from "./EvidenceNeededSection";
import { SuggestedChecksSection } from "./SuggestedChecksSection";

export interface IncidentDetailPanelProps {
  incident: IncidentDetailPayload;
}

/**
 * Main IncidentDetailPanel component with war room layout.
 */
export const IncidentDetailPanel: React.FC<IncidentDetailPanelProps> = ({ incident }) => {
  return (
    <section className="panel incident-detail-panel">
      <div className="incident-war-room">
        {/* War Room Header - Top summary */}
        <IncidentWarRoomHeader incident={incident} />

        {/* Review packet state */}
        <ReviewPacketSection reviewPacket={incident.review_packet} />

        {/* Signals section */}
        <SignalsSection signals={incident.signals} />

        {/* Evidence links section */}
        <EvidenceLinksSection evidenceLinks={incident.evidence_links} />

        {/* Evidence artifacts - bounded metadata */}
        <EvidenceArtifactsSection evidenceArtifacts={incident.evidence_artifacts} />

        {/* Timeline section */}
        <TimelineSection events={incident.events} />

        {/* Evidence needed */}
        <EvidenceNeededSection evidenceNeeded={incident.evidence_needed} />

        {/* Suggested checks - read-only compatibility projection */}
        <SuggestedChecksSection suggestedChecks={incident.suggested_checks} />

        {/* Automatic diagnosis loop summary - current-state summary from timeline */}
        <IncidentAutomaticDiagnosisLoopCard
          loopSummary={incident.automatic_diagnosis_loop_summary}
        />

        {/* Manual diagnosis loop - one-pass only */}
        <IncidentDiagnosisLoopPanel
          incidentId={incident.incident_id}
          suggestedChecks={incident.suggested_checks}
        />

        {/* One-pass read-only diagnosis service - bounded manual trigger */}
        <IncidentOnePassDiagnosisPanel
          incidentId={incident.incident_id}
        />

        {/* Automatic diagnosis review - bounded summary only */}
        <IncidentAutomaticDiagnosisReviewPanel
          automaticDiagnosisReview={incident.automatic_diagnosis_review}
        />

        {/* Read-only notice */}
        <div className="incident-detail-notice">
          <p className="muted small">
            Read-only view. No remediation, mutation, or LLM actions available.
          </p>
        </div>
      </div>
    </section>
  );
};
