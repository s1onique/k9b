/**
 * useRunHeaderModel - Extracts run header display derivation from App.tsx
 *
 * This hook computes the values used by the top run header / hero area.
 * Pure derivation only: no side effects, no state management.
 *
 * ACT 1B: Extract run header display model from App shell
 */

import { useMemo } from "react";

import type { RunPayload, RunsListEntry } from "../../types";
import { formatDuration } from "../ExecutionHistoryPanel";
import { relativeRecency } from "../../utils";

export interface RunHeaderModel {
  headerRunId: string;
  headerRunLabel: string;
  runRecency: string;
  latestRunTimestamp: string | null;
  latestRunRecency: string;
  headerStats: Array<{ label: string; value: string }>;
}

export interface UseRunHeaderModelArgs {
  run: RunPayload | null;
  runsList: RunsListEntry[];
  selectedRunId: string | null;
  latestRunId: string | null;
}

/**
 * Derives run header display values from the selected run and runs list.
 *
 * Extracts only the pure header display derivations needed by the hero area:
 * - headerRunId: Run identifier for display
 * - headerRunLabel: Human-readable run label
 * - runRecency: Relative time string for the selected run
 * - latestRunTimestamp: Timestamp of the latest run
 * - latestRunRecency: Relative time string for the latest run
 * - headerStats: Run duration statistics for display
 */
export function useRunHeaderModel({
  run,
  runsList,
  selectedRunId,
  latestRunId,
}: UseRunHeaderModelArgs): RunHeaderModel {
  return useMemo(() => {
    // Find the selected run in the runs list for timestamp/label
    const selectedRunListEntry = runsList.find((r) => r.runId === selectedRunId) ?? null;

    // Derive header timestamp from list entry or run payload
    const headerRunTimestamp = selectedRunListEntry?.timestamp ?? run?.timestamp ?? "";

    // Header run identity
    const headerRunId = selectedRunListEntry?.runId ?? run?.runId ?? "—";
    const headerRunLabel = selectedRunListEntry?.runLabel ?? run?.label ?? "—";

    // Recency strings
    const runRecency = headerRunTimestamp ? relativeRecency(headerRunTimestamp) : "—";

    // Latest run timestamp and recency
    const latestRunTimestamp = latestRunId
      ? runsList.find((r) => r.runId === latestRunId)?.timestamp ?? headerRunTimestamp
      : headerRunTimestamp;
    const latestRunRecency = latestRunTimestamp ? relativeRecency(latestRunTimestamp) : "—";

    // Run duration stats
    const headerStats = run
      ? [
          { label: "Last", value: formatDuration(run.runStats.lastRunDurationSeconds) },
          { label: "Runs", value: String(run.runStats.totalRuns) },
          { label: "P50", value: formatDuration(run.runStats.p50RunDurationSeconds) },
          { label: "P95", value: formatDuration(run.runStats.p95RunDurationSeconds) },
          { label: "P99", value: formatDuration(run.runStats.p99RunDurationSeconds) },
        ]
      : [];

    return {
      headerRunId,
      headerRunLabel,
      runRecency,
      latestRunTimestamp,
      latestRunRecency,
      headerStats,
    };
  }, [run, runsList, selectedRunId, latestRunId]);
}
