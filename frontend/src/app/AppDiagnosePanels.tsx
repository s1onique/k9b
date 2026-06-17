/**
 * AppDiagnosePanels Component
 *
 * Grouped panels for the "Diagnose" workflow lane.
 * Extracted from App.tsx to reduce component size.
 */

import type { Run } from "../types";
import { ReviewEnrichmentPanel } from "../components/ReviewEnrichmentPanel";
import { ProviderExecutionPanel } from "../components/ProviderExecutionComponents";
import { RunDiagnosticPackPanel } from "../components/RunDiagnosticPackPanel";
import { DiagnosticPackReviewPanel } from "../components/DiagnosticPackReviewPanel";
import { AlertmanagerSnapshotPanel } from "../components/AlertmanagerPanel";
import { AlertmanagerSourcesPanel } from "../components/AlertmanagerPanel";
import { DeterministicNextChecksPanel } from "../components/DeterministicNextChecksPanel";
import { IncidentListPanel } from "../components/IncidentListPanel";
import type { DeterministicNextCheckSummary } from "../types";

export interface AppDiagnosePanelsProps {
  run: Run | null | undefined;
  selectedClusterLabel: string | null;
  onRefresh: () => void;
  onNavigateToQueue: () => void;
  onFocusQueueReview: () => void;
  onPromoteCheck: (clusterLabel: string, checkIndex: number) => void;
  onToggleIncidentExpansion: (label: string) => void;
  onFocusClusterForNextChecks: (clusterLabel?: string | null) => void;
  onSetQueueStatusFilter: (status: string) => void;
  onSetQueueClusterFilter: (cluster: string) => void;
  onScrollToSection: (section: string) => void;
  artifactUrl: (path: string) => string;
  hasDegradedClusters: boolean;
  hookPromotionStatus: unknown;
  incidentExpandedClusters: Record<string, boolean>;
  deterministicChecks?: DeterministicNextCheckSummary[];
  deterministicSummary?: string;
}

export function AppDiagnosePanels({
  run,
  selectedClusterLabel,
  onRefresh,
  onNavigateToQueue,
  onFocusQueueReview,
  onPromoteCheck,
  onToggleIncidentExpansion,
  onFocusClusterForNextChecks,
  onSetQueueStatusFilter,
  onSetQueueClusterFilter,
  onScrollToSection,
  artifactUrl,
  hasDegradedClusters,
  hookPromotionStatus,
  incidentExpandedClusters,
  deterministicChecks,
  deterministicSummary,
}: AppDiagnosePanelsProps) {
  return (
    <>
      {run ? (
        <ReviewEnrichmentPanel
          reviewEnrichment={run.reviewEnrichment}
          reviewEnrichmentStatus={run.reviewEnrichmentStatus}
          nextCheckPlan={run.nextCheckPlan}
          onNavigateToQueue={onNavigateToQueue}
          onFocusQueueReview={onFocusQueueReview}
        />
      ) : (
        <section className="panel" id="review-enrichment">
          <p className="muted">Provider advisory — Loading selected run…</p>
        </section>
      )}
      {run ? (
        <ProviderExecutionPanel execution={run.providerExecution} />
      ) : (
        <section className="panel" id="provider-execution">
          <p className="muted">Provider branches — Loading selected run…</p>
        </section>
      )}
      {run ? (
        <RunDiagnosticPackPanel diagnosticPack={run.diagnosticPack} />
      ) : (
        <section className="panel" id="diagnostic-pack-download">
          <p className="muted">Diagnostic package — Loading selected run…</p>
        </section>
      )}
      {run?.diagnosticPackReview && (
        <DiagnosticPackReviewPanel review={run.diagnosticPackReview} />
      )}
      {run ? (
        <AlertmanagerSnapshotPanel compact={run.alertmanagerCompact} clusterLabel={selectedClusterLabel} />
      ) : (
        <section className="panel" id="alertmanager-snapshot">
          <p className="muted">Alertmanager snapshot — Loading selected run…</p>
        </section>
      )}
      {run?.alertmanagerSources && (
        <AlertmanagerSourcesPanel
          sources={run.alertmanagerSources}
          runId={run.runId}
          clusterLabel={selectedClusterLabel}
          onRefresh={onRefresh}
        />
      )}
      {run ? (
        <DeterministicNextChecksPanel
          deterministicChecks={deterministicChecks}
          deterministicSummary={deterministicSummary}
          hookPromotionStatus={hookPromotionStatus}
          incidentExpandedClusters={incidentExpandedClusters}
          onPromoteCheck={onPromoteCheck}
          onToggleIncidentExpansion={onToggleIncidentExpansion}
          onFocusClusterForNextChecks={onFocusClusterForNextChecks}
          onSetQueueStatusFilter={onSetQueueStatusFilter}
          onSetQueueClusterFilter={onSetQueueClusterFilter}
          onScrollToSection={onScrollToSection}
          artifactUrl={artifactUrl}
          hasDegradedClusters={hasDegradedClusters}
        />
      ) : (
        <section className="panel deterministic-next-checks-panel" id="deterministic-next-checks">
          <div className="section-head">
            <h2>Deterministic checks</h2>
            <p className="muted">Loading selected run…</p>
          </div>
        </section>
      )}
      {/* Incident list panel - read-only view of promoted incidents */}
      <IncidentListPanel />
    </>
  );
}
