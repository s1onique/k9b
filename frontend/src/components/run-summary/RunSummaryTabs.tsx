/**
 * RunSummaryTabs.tsx
 *
 * Tabbed interface for RunSummaryPanel content organization.
 * Extracted from RunSummaryPanel (Phase 2 - Run Summary UX Redesign).
 *
 * Tabs:
 * - Overview: shows combined summary content (RunKpiStrip)
 * - Next checks: shows NextChecksSummaryCard
 * - Telemetry: shows LlmTelemetryCard
 * - Artifacts: shows the artifacts strip
 *
 * PastRunNotice must remain outside tabs (rendered separately in RunSummaryPanel).
 */

import type {
  NextCheckPlanCandidate,
  NextCheckStatusVariant,
  RunArtifact,
} from "../../types";
import { artifactUrl } from "../../utils";
import { LlmTelemetryCard } from "./LlmTelemetryCard";
import { NextChecksSummaryCard } from "./NextChecksSummaryCard";
import { RunKpiStrip } from "./RunKpiStrip";

// Tab definitions
export type RunSummaryTabId = "overview" | "next-checks" | "telemetry" | "artifacts";

const RUN_SUMMARY_TABS: { id: RunSummaryTabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "next-checks", label: "Next checks" },
  { id: "telemetry", label: "Telemetry" },
  { id: "artifacts", label: "Artifacts" },
];

export interface RunSummaryTabsProps {
  /** Active tab id */
  activeTab: RunSummaryTabId;
  /** Callback when tab is selected */
  onTabChange: (tab: RunSummaryTabId) => void;
  // Overview tab content
  runSummaryStats: { label: string; value: string | number }[];
  runStatsSummary: string;
  // Telemetry tab content
  runLlmStatsLine: React.ReactNode;
  historicalLlmStatsLine: React.ReactNode | null;
  providerBreakdown: string | null;
  // Next checks tab content
  runPlan: {
    summary: string | null;
    artifactPath: string | null;
    status: string;
    candidateCount?: number;
  } | null;
  runPlanCandidates: NextCheckPlanCandidate[];
  planSummaryText: string;
  planStatusText: string | null;
  plannerReasonText: string;
  plannerHint: string | null;
  plannerNextActionHint: string | null;
  plannerArtifactUrl: string | null;
  planCandidateCountLabel: string;
  discoveryVariantOrder: NextCheckStatusVariant[];
  discoveryVariantCounts: Record<NextCheckStatusVariant, number>;
  discoveryClusters: string[];
  onReviewNextChecks: () => void;
  onFocusClusterForNextChecks: (clusterLabel: string) => void;
  // Artifacts tab content
  artifacts: RunArtifact[];
}

export const RunSummaryTabs = ({
  activeTab,
  onTabChange,
  runSummaryStats,
  runStatsSummary,
  runLlmStatsLine,
  historicalLlmStatsLine,
  providerBreakdown,
  runPlan,
  runPlanCandidates,
  planSummaryText,
  planStatusText,
  plannerReasonText,
  plannerHint,
  plannerNextActionHint,
  plannerArtifactUrl,
  planCandidateCountLabel,
  discoveryVariantOrder,
  discoveryVariantCounts,
  discoveryClusters,
  onReviewNextChecks,
  onFocusClusterForNextChecks,
  artifacts,
}: RunSummaryTabsProps) => {
  // Stable IDs for each tab and panel
  const TAB_IDS: Record<RunSummaryTabId, string> = {
    overview: "tab-overview",
    "next-checks": "tab-next-checks",
    telemetry: "tab-telemetry",
    artifacts: "tab-artifacts",
  };

  const PANEL_IDS: Record<RunSummaryTabId, string> = {
    overview: "panel-overview",
    "next-checks": "panel-next-checks",
    telemetry: "panel-telemetry",
    artifacts: "panel-artifacts",
  };

  return (
    <div className="run-summary-tabs" data-testid="run-summary-tabs">
      {/* Tab list with ARIA roles */}
      <div className="tab-list" role="tablist" aria-label="Run summary sections">
        {RUN_SUMMARY_TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          const tabId = TAB_IDS[tab.id];
          const panelId = PANEL_IDS[tab.id];
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={tabId}
              aria-selected={isActive}
              aria-controls={panelId}
              className={`tab ${isActive ? "active" : ""}`}
              onClick={() => onTabChange(tab.id)}
              data-testid={`tab-${tab.id}`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab panels with ARIA roles */}
      <div className="run-summary-tab-panels">
        {/* Overview tab */}
        <div
          role="tabpanel"
          id="panel-overview"
          aria-labelledby="tab-overview"
          hidden={activeTab !== "overview"}
          data-testid="panel-overview"
        >
          {activeTab === "overview" && (
            <RunKpiStrip
              stats={runSummaryStats}
              durationSummary={runStatsSummary}
            />
          )}
        </div>

        {/* Next checks tab */}
        <div
          role="tabpanel"
          id="panel-next-checks"
          aria-labelledby="tab-next-checks"
          hidden={activeTab !== "next-checks"}
          data-testid="panel-next-checks"
        >
          {activeTab === "next-checks" && (
            <NextChecksSummaryCard
              runPlan={runPlan}
              runPlanCandidates={runPlanCandidates}
              planSummaryText={planSummaryText}
              planStatusText={planStatusText}
              plannerReasonText={plannerReasonText}
              plannerHint={plannerHint}
              plannerNextActionHint={plannerNextActionHint}
              plannerArtifactUrl={plannerArtifactUrl}
              planCandidateCountLabel={planCandidateCountLabel}
              discoveryVariantOrder={discoveryVariantOrder}
              discoveryVariantCounts={discoveryVariantCounts}
              discoveryClusters={discoveryClusters}
              onReviewNextChecks={onReviewNextChecks}
              onFocusClusterForNextChecks={onFocusClusterForNextChecks}
            />
          )}
        </div>

        {/* Telemetry tab */}
        <div
          role="tabpanel"
          id="panel-telemetry"
          aria-labelledby="tab-telemetry"
          hidden={activeTab !== "telemetry"}
          data-testid="panel-telemetry"
        >
          {activeTab === "telemetry" && (
            <LlmTelemetryCard
              llmStatsLine={runLlmStatsLine}
              historicalLlmStatsLine={historicalLlmStatsLine}
              providerBreakdown={providerBreakdown}
            />
          )}
        </div>

        {/* Artifacts tab */}
        <div
          role="tabpanel"
          id="panel-artifacts"
          aria-labelledby="tab-artifacts"
          hidden={activeTab !== "artifacts"}
          data-testid="panel-artifacts"
        >
          {activeTab === "artifacts" && (
            <div className="artifact-strip run-artifacts" data-testid="artifacts-list">
              {artifacts.length > 0 ? (
                artifacts.map((artifact) => {
                  const url = artifactUrl(artifact.path);
                  return (
                    url && (
                      <a
                        key={artifact.label}
                        className="artifact-link run-artifact-link"
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                        data-testid={`artifact-${artifact.label.toLowerCase().replace(/\s+/g, "-")}`}
                      >
                        {artifact.label}
                      </a>
                    )
                  );
                })
              ) : (
                <p className="muted small">No artifacts available for this run.</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
