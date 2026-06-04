/**
 * renderLlmStatsLine - Extracts LLM stats line rendering from App.tsx
 *
 * This helper transforms LLMStats data into a JSX element for the run header.
 * It is a pure function with no state dependencies.
 */

import type { LLMStats } from "../../types";
import { getLlmScopeLabel } from "../../utils/selectors";
import { formatLatency, relativeRecency } from "../../utils";

export function renderLlmStatsLine(stats: LLMStats, modifier?: string) {
  const scopeLabel = getLlmScopeLabel(stats.scope ?? null);
  const lastCallValue = stats.lastCallTimestamp ? relativeRecency(stats.lastCallTimestamp) : "—";
  const entries = [
    { label: `${scopeLabel} calls`, value: String(stats.totalCalls) },
    { label: "OK", value: String(stats.successfulCalls) },
    { label: "Failed", value: String(stats.failedCalls) },
    { label: "P50", value: formatLatency(stats.p50LatencyMs) },
    { label: "P95", value: formatLatency(stats.p95LatencyMs) },
    { label: "P99", value: formatLatency(stats.p99LatencyMs) },
    { label: "Last call", value: lastCallValue },
  ];
  const classNames = [
    "run-header-inline-stats",
    "llm-stats-line",
    "muted",
    "small",
    modifier,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <p className={classNames}>
      {entries.map((stat) => (
        <span key={`${stat.label}-${stat.value}`}>
          <span className="run-stat-label">{stat.label}: </span>
          <strong>{stat.value}</strong>
        </span>
      ))}
    </p>
  );
}
