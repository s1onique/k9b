/**
 * RunOverviewDashboard.tsx
 *
 * Operator-first Overview dashboard for RunSummaryTabs.
 * Summarizes the most important run information and provides clear paths into detailed tabs.
 *
 * Phase 3 - Run Summary UX Redesign: Overview dashboard content.
 *
 * Layout:
 * - KPI strip (RunKpiStrip) at top
 * - "What needs attention now" section
 * - Next checks preview with CTA
 * - Compact LLM telemetry preview with CTA
 * - Artifacts/provenance teaser with CTA
 *
 * Detailed tabs remain the full views:
 * - Next checks tab: full NextChecksSummaryCard
 * - Telemetry tab: full LlmTelemetryCard
 * - Artifacts tab: full artifact list
 */

import type {
  IncidentReportPayload,
  LLMProviderBreakdown,
  NextCheckStatusVariant,
  OperatorWorklistPayload,
  RunArtifact,
} from "../../types";
import { RunKpiStrip } from "./RunKpiStrip";
import {
  TelemetryStatsRow,
  TelemetryLatencyRow,
  TelemetryProvidersRow,
} from "./LlmTelemetryCard";
import { IncidentReportCard } from "./IncidentReportCard";
import { OperatorWorklistCard } from "./OperatorWorklistCard";

// ============================================================================
// Props
// ============================================================================

export interface RunOverviewDashboardProps {
  // KPI strip content
  runSummaryStats: { label: string; value: string | number }[];
  runStatsSummary: string;

  // Telemetry preview content
  runLlmStatsLine: React.ReactNode;
  providerBreakdown: string | null;
  /** Structured telemetry data for LlmTelemetryPreviewCard (optional for backward compatibility) */
  telemetryData?: LlmTelemetryPreviewData;

  // Next checks preview content
  runPlan: {
    summary: string | null;
    artifactPath: string | null;
    status: string;
    candidateCount?: number;
  } | null;
  planStatusText: string | null;
  planCandidateCountLabel: string;
  discoveryVariantCounts: Record<NextCheckStatusVariant, number>;
  discoveryClusters: string[];
  onFocusClusterForNextChecks: (clusterLabel: string) => void;

  // Artifacts preview content
  artifacts: RunArtifact[];

  // Phase 2: Canonical incident surface
  /** Incident report projection for the selected run */
  incidentReport?: IncidentReportPayload | null;
  /** Operator worklist projection for the selected run */
  operatorWorklist?: OperatorWorklistPayload | null;

  // Tab change callback for CTAs
  onTabChange: (tab: "next-checks" | "telemetry" | "artifacts") => void;
}

// ============================================================================
// Local subcomponents
// ============================================================================

// "What needs attention now" section
// Note: Only shows affected clusters. Does not derive degraded health findings
// from discoveryVariantCounts which is for next-check workflow statuses.
interface AttentionNowCardProps {
  discoveryClusters: string[];
  onFocusClusterForNextChecks: (clusterLabel: string) => void;
  onViewNextChecks: () => void;
}

const AttentionNowCard = ({
  discoveryClusters,
  onFocusClusterForNextChecks,
  onViewNextChecks,
}: AttentionNowCardProps) => {
  const hasAffectedClusters = discoveryClusters.length > 0;

  // Only render if there's something that needs attention
  if (!hasAffectedClusters) {
    return null;
  }

  return (
    <div className="run-overview-card attention-now-card" data-testid="attention-now-card">
      <div className="attention-card-header">
        <span className="attention-icon" aria-hidden="true">⚠</span>
        <h3>What needs attention now</h3>
      </div>
      <div className="attention-now-content">
        {/* Affected cluster rows */}
        <div className="attention-now-section">
          <p className="muted tiny attention-subtitle">Affected clusters need review</p>
          <div className="attention-cluster-rows">
            {discoveryClusters.map((cluster) => (
              <div className="attention-cluster-row" key={cluster}>
                <span className="cluster-name">{cluster}</span>
                <button
                  type="button"
                  className="run-summary-cta-secondary attention-cta"
                  onClick={() => onFocusClusterForNextChecks(cluster)}
                  data-testid={`cluster-badge-${cluster}`}
                >
                  View checks →
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
      {/* Footer CTA to open Next checks tab */}
      <button
        type="button"
        className="run-summary-cta-secondary"
        onClick={onViewNextChecks}
        data-testid="view-next-checks-from-attention"
      >
        View all next checks →
      </button>
    </div>
  );
};

// Next checks preview section
interface NextChecksPreviewCardProps {
  runPlan: {
    summary: string | null;
    artifactPath: string | null;
    status: string;
    candidateCount?: number;
  } | null;
  planStatusText: string | null;
  planCandidateCountLabel: string;
  onViewNextChecks: () => void;
}

const NextChecksPreviewCard = ({
  runPlan,
  planStatusText,
  planCandidateCountLabel,
  onViewNextChecks,
}: NextChecksPreviewCardProps) => {
  return (
    <div className="run-overview-card next-checks-preview-card" data-testid="next-checks-preview-card">
      <div className="preview-card-header">
        <span className="preview-card-icon" aria-hidden="true">→</span>
        <h3>Next checks</h3>
      </div>
      <div className="next-checks-preview-content">
        {runPlan ? (
          <div className="next-checks-metrics">
            {planStatusText && (
              <div className="metric-cell">
                <span className="metric-label">Planner</span>
                <span className="metric-value">{planStatusText}</span>
              </div>
            )}
            <div className="metric-cell">
              <span className="metric-label">Candidates</span>
              <span className="metric-value">{planCandidateCountLabel}</span>
            </div>
          </div>
        ) : (
          <p className="muted tiny">No next checks generated for this run.</p>
        )}
      </div>
      {/* Primary CTA */}
      <button
        type="button"
        className="run-summary-cta"
        onClick={onViewNextChecks}
        data-testid="review-next-checks-cta"
      >
        Review next checks
      </button>
    </div>
  );
};

// ============================================================================
// LLM Telemetry Preview Card
// ============================================================================

/**
 * Structured LLM telemetry data for the preview card.
 * This allows the card to render structured layout instead of dense inline strings.
 */
export interface LlmTelemetryPreviewData {
  totalCalls: number;
  successfulCalls: number;
  failedCalls: number;
  lastCallRecency: string | null;
  p50LatencyMs: number | null;
  p95LatencyMs: number | null;
  p99LatencyMs: number | null;
  providers: LLMProviderBreakdown[];
}

interface LlmTelemetryPreviewCardProps {
  /** Structured telemetry data (preferred) */
  telemetryData?: LlmTelemetryPreviewData | null;
  /** Fallback: pre-rendered stats line (for backward compatibility) */
  llmStatsLine?: React.ReactNode;
  /** Fallback: pre-rendered provider breakdown string */
  providerBreakdown?: string | null;
  onViewTelemetry: () => void;
}

/**
 * Compact LLM telemetry preview card.
 * Renders structured layout with:
 * - Header: icon, title, compact recency
 * - Calls row: Calls / OK / Failed as grouped stat chips
 * - Latency row: P50 / P95 / P99 as grouped latency cells
 * - Providers row: provider chips that wrap cleanly
 */
const LlmTelemetryPreviewCard = ({
  telemetryData,
  llmStatsLine,
  providerBreakdown,
  onViewTelemetry,
}: LlmTelemetryPreviewCardProps) => {
  // Render structured layout when telemetry data is available
  if (telemetryData) {
    const {
      totalCalls,
      successfulCalls,
      failedCalls,
      lastCallRecency,
      p50LatencyMs,
      p95LatencyMs,
      p99LatencyMs,
      providers,
    } = telemetryData;

    return (
      <div className="run-overview-card llm-telemetry-preview-card" data-testid="llm-telemetry-preview-card">
        {/* Header: icon + title + recency */}
        <div className="preview-card-header">
          <span className="preview-card-icon" aria-hidden="true">◈</span>
          <h3>LLM telemetry</h3>
          {lastCallRecency && (
            <span className="telemetry-recency muted tiny">Last {lastCallRecency}</span>
          )}
        </div>

        {/* Calls row: Calls / OK / Failed as stat chips */}
        <TelemetryStatsRow
          totalCalls={totalCalls}
          successfulCalls={successfulCalls}
          failedCalls={failedCalls}
        />

        {/* Latency row: P50 / P95 / P99 as latency cells */}
        <TelemetryLatencyRow
          p50LatencyMs={p50LatencyMs}
          p95LatencyMs={p95LatencyMs}
          p99LatencyMs={p99LatencyMs}
        />

        {/* Providers row: provider chips that wrap cleanly */}
        {providers.length > 0 && (
          <TelemetryProvidersRow providers={providers} />
        )}

        {/* Footer CTA */}
        <button
          type="button"
          className="run-summary-cta-secondary"
          onClick={onViewTelemetry}
          data-testid="view-telemetry-cta"
        >
          View telemetry →
        </button>
      </div>
    );
  }

  // Fallback: render pre-rendered content (backward compatibility)
  return (
    <div className="run-overview-card llm-telemetry-preview-card" data-testid="llm-telemetry-preview-card">
      <div className="preview-card-header">
        <span className="preview-card-icon" aria-hidden="true">◈</span>
        <h3>LLM telemetry</h3>
      </div>
      <div className="llm-telemetry-preview-content">
        <div className="llm-stats-line">{llmStatsLine}</div>
        {providerBreakdown && (
          <p className="muted tiny llm-provider-preview">Providers: {providerBreakdown}</p>
        )}
      </div>
      {/* CTA */}
      <button
        type="button"
        className="run-summary-cta-secondary"
        onClick={onViewTelemetry}
        data-testid="view-telemetry-cta"
      >
        View telemetry →
      </button>
    </div>
  );
};

// Artifacts/provenance teaser section
interface ArtifactsPreviewCardProps {
  artifacts: RunArtifact[];
  onViewArtifacts: () => void;
}

const ArtifactsPreviewCard = ({
  artifacts,
  onViewArtifacts,
}: ArtifactsPreviewCardProps) => {
  const totalCount = artifacts.length;
  const previewLabels = artifacts.slice(0, 3).map((a) => a.label);

  return (
    <div className="run-overview-card artifacts-preview-card" data-testid="artifacts-preview-card">
      <div className="preview-card-header">
        <span className="preview-card-icon" aria-hidden="true">▣</span>
        <h3>Artifacts</h3>
      </div>
      <div className="artifacts-preview-content">
        {totalCount > 0 ? (
          <>
            <div className="artifacts-count">
              <strong>{totalCount}</strong>
              <span className="artifacts-count-label">artifact{totalCount !== 1 ? "s" : ""}</span>
            </div>
            {previewLabels.length > 0 && (
              <div className="artifacts-labels">
                {previewLabels.map((label) => (
                  <span key={label} className="artifact-label-chip">{label}</span>
                ))}
                {totalCount > 3 && <span className="artifacts-more muted tiny">+{totalCount - 3} more</span>}
              </div>
            )}
          </>
        ) : (
          <p className="muted tiny">No artifacts available for this run.</p>
        )}
      </div>
      {/* CTA */}
      {totalCount > 0 && (
        <button
          type="button"
          className="run-summary-cta-secondary"
          onClick={onViewArtifacts}
          data-testid="view-artifacts-cta"
        >
          View artifacts →
        </button>
      )}
    </div>
  );
};

// ============================================================================
// Main component
// ============================================================================

export const RunOverviewDashboard = ({
  runSummaryStats,
  runStatsSummary,
  runLlmStatsLine,
  providerBreakdown,
  telemetryData,
  runPlan,
  planStatusText,
  planCandidateCountLabel,
  discoveryVariantCounts: _discoveryVariantCounts,
  discoveryClusters,
  onFocusClusterForNextChecks,
  artifacts,
  incidentReport,
  operatorWorklist,
  onTabChange,
}: RunOverviewDashboardProps) => {
  return (
    <div className="run-overview-dashboard" data-testid="run-overview-dashboard">
      {/* KPI strip at top */}
      <RunKpiStrip stats={runSummaryStats} durationSummary={runStatsSummary} />

      {/* Preview cards in a 2-column responsive grid */}
      <div className="run-overview-grid">
        {/* Row 1, Col 1: "What needs attention now" - compact left-column operational card */}
        <AttentionNowCard
          discoveryClusters={discoveryClusters}
          onFocusClusterForNextChecks={onFocusClusterForNextChecks}
          onViewNextChecks={() => onTabChange("next-checks")}
        />

        {/* Row 1, Col 2: LLM telemetry - compact right-column peer card */}
        <LlmTelemetryPreviewCard
          telemetryData={telemetryData}
          llmStatsLine={runLlmStatsLine}
          providerBreakdown={providerBreakdown}
          onViewTelemetry={() => onTabChange("telemetry")}
        />

        {/* Row 2, Col 1: Next checks - prominent left-column primary action */}
        <NextChecksPreviewCard
          runPlan={runPlan}
          planStatusText={planStatusText}
          planCandidateCountLabel={planCandidateCountLabel}
          onViewNextChecks={() => onTabChange("next-checks")}
        />

        {/* Row 2, Col 2: Artifacts - secondary right-column supporting card */}
        <ArtifactsPreviewCard
          artifacts={artifacts}
          onViewArtifacts={() => onTabChange("artifacts")}
        />
      </div>

      {/* Phase 2: Canonical incident surface - below the 2-column grid */}
      {/* These are the primary surfaces for incident story + operator action list */}
      {/* Layout: Operator worklist left (62%), Incident report right (38%) */}
      <div className="run-overview-incident-surfaces" data-testid="run-overview-incident-surfaces">
        {/* Operator worklist: Ranked action items with commands (left, primary action surface) */}
        <OperatorWorklistCard operatorWorklist={operatorWorklist} />

        {/* Incident report: Facts, Inferences, Unknowns, Stale evidence (right, informational) */}
        <IncidentReportCard incidentReport={incidentReport} />
      </div>
    </div>
  );
};
