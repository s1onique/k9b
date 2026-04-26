/**
 * LlmTelemetryCard.tsx
 *
 * Displays LLM telemetry: current run stats, provider breakdown, and historical stats.
 * Extracted from RunSummaryPanel (E1-3b-step15).
 */

export interface LlmTelemetryCardProps {
  /** Pre-rendered stats line for current run */
  llmStatsLine: React.ReactNode;
  /** Pre-rendered stats line for historical run (or null) */
  historicalLlmStatsLine: React.ReactNode | null;
  /** Formatted provider breakdown string (or null) */
  providerBreakdown: string | null;
}

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