/**
 * AppRunSummarySection Component
 *
 * Run summary panel with conditional loading states.
 * Uses ComponentProps pattern to avoid manual prop type definition.
 * Extracted from App.tsx to reduce component size.
 */

import type { ComponentProps } from "react";
import type React from "react";
import { RunSummaryPanel } from "../components/RunsPanel";

type RunSummaryPanelProps = ComponentProps<typeof RunSummaryPanel>;

export interface AppRunSummarySectionProps {
  run: RunSummaryPanelProps["run"];
  runOwnedPanelState: RunSummaryPanelProps["runOwnedPanelState"];
  loadedProps: RunSummaryPanelProps;
  unavailableProps: RunSummaryPanelProps;
}

export function AppRunSummarySection({
  run,
  runOwnedPanelState,
  loadedProps,
  unavailableProps,
}: AppRunSummarySectionProps) {
  if (run) {
    return <RunSummaryPanel {...loadedProps} />;
  }

  if (runOwnedPanelState === "slow" || runOwnedPanelState === "failed") {
    return <RunSummaryPanel {...unavailableProps} />;
  }

  return (
    <section className="panel" id="run-detail">
      <div className="section-head">
        <h2>Run summary</h2>
        <p className="muted">Loading selected run…</p>
      </div>
    </section>
  );
}