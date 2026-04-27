/**
 * LlmTelemetryCard.tsx
 *
 * Displays LLM telemetry: current run stats, provider breakdown, and historical stats.
 * Extracted from RunSummaryPanel (E1-3b-step15).
 * 
 * Layout:
 * - Header: icon, title, compact status/recency
 * - Calls row: Calls / OK / Failed as grouped stat chips
 * - Latency row: P50 / P95 / P99 as grouped latency cells
 * - Providers row: provider chips that wrap cleanly
 * - Footer: "View telemetry →" as a secondary action
 */

import type { LLMProviderBreakdown } from "../../types";

export interface LlmTelemetryCardProps {
  /** Pre-rendered stats line for current run */
  llmStatsLine: React.ReactNode;
  /** Pre-rendered stats line for historical run (or null) */
  historicalLlmStatsLine: React.ReactNode | null;
  /** Formatted provider breakdown string (or null) */
  providerBreakdown: string | null;
}

// ============================================================================
// Utility functions for compact formatting
// ============================================================================

/**
 * Formats a latency value for compact display.
 * - null/undefined/non-finite returns "—"
 * - >= 1000ms displays as seconds (e.g., "15.3s")
 * - < 1000ms displays as milliseconds (e.g., "153ms")
 */
export const formatLatencyMs = (value: number | null | undefined): string => {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}s`;
  }
  return `${Math.round(value)}ms`;
};

/**
 * Returns CSS class for failed count based on value.
 * - 0: neutral styling
 * - > 0: attention/danger styling
 */
const getFailedCountClass = (failed: number): string => {
  return failed > 0 ? "stat-chip stat-chip--danger" : "stat-chip stat-chip--neutral";
};

// ============================================================================
// Structured telemetry row components
// ============================================================================

/**
 * Calls row: Calls / OK / Failed as grouped stat chips
 */
interface TelemetryStatsRowProps {
  totalCalls: number;
  successfulCalls: number;
  failedCalls: number;
}

export const TelemetryStatsRow = ({ totalCalls, successfulCalls, failedCalls }: TelemetryStatsRowProps) => (
  <div className="telemetry-stats-row" data-testid="llm-telemetry-stats">
    <div className="stat-chip">
      <span className="stat-chip-label">Calls</span>
      <span className="stat-chip-value">{totalCalls}</span>
    </div>
    <div className="stat-chip">
      <span className="stat-chip-label">OK</span>
      <span className="stat-chip-value">{successfulCalls}</span>
    </div>
    <div className={getFailedCountClass(failedCalls)}>
      <span className="stat-chip-label">Failed</span>
      <span className="stat-chip-value">{failedCalls}</span>
    </div>
  </div>
);

/**
 * Latency row: P50 / P95 / P99 as grouped latency cells
 */
interface TelemetryLatencyRowProps {
  p50LatencyMs: number | null;
  p95LatencyMs: number | null;
  p99LatencyMs: number | null;
}

export const TelemetryLatencyRow = ({ p50LatencyMs, p95LatencyMs, p99LatencyMs }: TelemetryLatencyRowProps) => (
  <div className="telemetry-latency-row">
    <div className="latency-cell">
      <span className="latency-label">P50</span>
      <span className="latency-value">{formatLatencyMs(p50LatencyMs)}</span>
    </div>
    <div className="latency-cell">
      <span className="latency-label">P95</span>
      <span className="latency-value">{formatLatencyMs(p95LatencyMs)}</span>
    </div>
    <div className="latency-cell">
      <span className="latency-label">P99</span>
      <span className="latency-value">{formatLatencyMs(p99LatencyMs)}</span>
    </div>
  </div>
);

/**
 * Providers row: provider chips that wrap cleanly
 */
interface TelemetryProvidersRowProps {
  providers: LLMProviderBreakdown[];
}

export const TelemetryProvidersRow = ({ providers }: TelemetryProvidersRowProps) => (
  <div className="telemetry-providers-row">
    {providers.map((provider) => (
      <span
        key={provider.provider}
        className="provider-chip"
        data-testid={`provider-chip-${provider.provider}`}
      >
        <span className="provider-chip-name">{provider.provider}</span>
        <span className="provider-chip-count">{provider.calls}</span>
        {provider.failedCalls > 0 && (
          <span className="provider-chip-failed">({provider.failedCalls} failed)</span>
        )}
      </span>
    ))}
  </div>
);

// ============================================================================
// Main component
// ============================================================================

export const LlmTelemetryCard = ({
  llmStatsLine,
  historicalLlmStatsLine,
  providerBreakdown,
}: LlmTelemetryCardProps) => {
  return (
    <div className="run-summary-llm">
      <div className="run-summary-llm-heading">
        <p className="eyebrow">LLM telemetry</p>
        <span className="muted tiny">Provider call metrics from artifacts</span>
      </div>
      <div className="llm-current-line">
        {llmStatsLine}
        {providerBreakdown && (
          <p className="llm-provider-breakdown muted tiny">Providers: {providerBreakdown}</p>
        )}
      </div>
      {historicalLlmStatsLine && (
        <details className="llm-historical">
          <summary>Retained history stats</summary>
          {historicalLlmStatsLine}
        </details>
      )}
    </div>
  );
};
