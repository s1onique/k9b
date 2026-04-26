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

import type { NextCheckStatusVariant, RunArtifact } from "../../types";
import { RunKpiStrip } from "./RunKpiStrip";

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
    <div className="attention-now-card" data-testid="attention-now-card">
      <h3>What needs attention now</h3>
      <div className="attention-now-content">
        {/* Affected cluster badges */}
        <div className="attention-now-section">
          <p className="muted tiny">Affected clusters:</p>
          <div className="attention-now-clusters">
            {discoveryClusters.map((cluster) => (
              <button
                type="button"
                className="cluster-badge"
                key={cluster}
                onClick={() => onFocusClusterForNextChecks(cluster)}
                data-testid={`cluster-badge-${cluster}`}
              >
                {cluster}
              </button>
            ))}
          </div>
        </div>
      </div>
      {/* CTA to open Next checks tab */}
      <button
        type="button"
        className="link"
        onClick={onViewNextChecks}
        data-testid="view-next-checks-from-attention"
      >
        View next checks →
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
    <div className="next-checks-preview-card" data-testid="next-checks-preview-card">
      <h3>Next checks</h3>
      <div className="next-checks-preview-content">
        {runPlan ? (
          <>
            <p className="muted tiny">
              {planStatusText ? `Planner: ${planStatusText} · ` : ""}
              {planCandidateCountLabel}
            </p>
          </>
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

// Compact LLM telemetry preview section
interface LlmTelemetryPreviewCardProps {
  llmStatsLine: React.ReactNode;
  providerBreakdown: string | null;
  onViewTelemetry: () => void;
}

const LlmTelemetryPreviewCard = ({
  llmStatsLine,
  providerBreakdown,
  onViewTelemetry,
}: LlmTelemetryPreviewCardProps) => {
  return (
    <div className="llm-telemetry-preview-card" data-testid="llm-telemetry-preview-card">
      <h3>LLM telemetry</h3>
      <div className="llm-telemetry-preview-content">
        <div className="llm-stats-line">{llmStatsLine}</div>
        {providerBreakdown && (
          <p className="muted tiny">Providers: {providerBreakdown}</p>
        )}
      </div>
      {/* CTA */}
      <button
        type="button"
        className="link"
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
    <div className="artifacts-preview-card" data-testid="artifacts-preview-card">
      <h3>Artifacts</h3>
      <div className="artifacts-preview-content">
        <p className="muted tiny">
          {totalCount > 0 ? (
            <>
              <strong>{totalCount}</strong> artifact{totalCount !== 1 ? "s" : ""} available
              {previewLabels.length > 0 && (
                <>
                  {" "}· {previewLabels.join(", ")}
                  {totalCount > 3 && "…"}
                </>
              )}
            </>
          ) : (
            "No artifacts available for this run."
          )}
        </p>
      </div>
      {/* CTA */}
      {totalCount > 0 && (
        <button
          type="button"
          className="link"
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
  runPlan,
  planStatusText,
  planCandidateCountLabel,
  discoveryVariantCounts,
  discoveryClusters,
  onFocusClusterForNextChecks,
  artifacts,
  onTabChange,
}: RunOverviewDashboardProps) => {
  return (
    <div className="run-overview-dashboard" data-testid="run-overview-dashboard">
      {/* KPI strip at top */}
      <RunKpiStrip stats={runSummaryStats} durationSummary={runStatsSummary} />

      {/* "What needs attention now" section */}
      <AttentionNowCard
        discoveryClusters={discoveryClusters}
        onFocusClusterForNextChecks={onFocusClusterForNextChecks}
        onViewNextChecks={() => onTabChange("next-checks")}
      />

      {/* Next checks preview */}
      <NextChecksPreviewCard
        runPlan={runPlan}
        planStatusText={planStatusText}
        planCandidateCountLabel={planCandidateCountLabel}
        onViewNextChecks={() => onTabChange("next-checks")}
      />

      {/* Compact LLM telemetry preview */}
      <LlmTelemetryPreviewCard
        llmStatsLine={runLlmStatsLine}
        providerBreakdown={providerBreakdown}
        onViewTelemetry={() => onTabChange("telemetry")}
      />

      {/* Artifacts preview */}
      <ArtifactsPreviewCard
        artifacts={artifacts}
        onViewArtifacts={() => onTabChange("artifacts")}
      />
    </div>
  );
};
