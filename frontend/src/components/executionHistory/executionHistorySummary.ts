/**
 * executionHistorySummary.ts
 *
 * Summary types and computation for ExecutionHistory components.
 */

import type { NextCheckExecutionHistoryEntry } from "../../types";

// =============================================================================
// Summary types
// =============================================================================

export type RepeatedFailureGroup = {
  failurePattern: string;
  count: number;
  entries: NextCheckExecutionHistoryEntry[];
  label: string;
};

export type ExecutionHistorySummary = {
  usefulChecks: NextCheckExecutionHistoryEntry[];
  noisyEmptyChecks: NextCheckExecutionHistoryEntry[];
  repeatedFailures: RepeatedFailureGroup[];
};

// =============================================================================
// Summary computation
// =============================================================================

/**
 * Detect repeated failure patterns using a simple deterministic heuristic.
 */
const detectRepeatedFailures = (entries: NextCheckExecutionHistoryEntry[]): RepeatedFailureGroup[] => {
  // Only consider failed or timed-out entries
  const failureEntries = entries.filter((e) => {
    const isFailure = e.status === "failed" || e.status === "error";
    const isTimeout = e.timedOut === true;
    const hasFailureClass = Boolean(e.failureClass);
    return isFailure || isTimeout || hasFailureClass;
  });

  if (failureEntries.length === 0) {
    return [];
  }

  // Build a key for grouping similar failures
  const getFailureKey = (entry: NextCheckExecutionHistoryEntry): string => {
    if (entry.failureClass) {
      return `class:${entry.failureClass}`;
    }
    if (entry.timedOut) {
      return entry.commandFamily ? `timeout:${entry.commandFamily}` : "timeout:generic";
    }
    if (entry.status === "failed" || entry.status === "error") {
      return entry.commandFamily ? `failed:${entry.commandFamily}` : "failed:generic";
    }
    const prefix = (entry.candidateDescription || "").slice(0, 30).toLowerCase().trim();
    return `desc:${prefix}`;
  };

  const getFailureLabel = (entry: NextCheckExecutionHistoryEntry, key: string): string => {
    if (key.startsWith("class:")) {
      const failureClass = key.slice(6);
      const labels: Record<string, string> = {
        "timed-out": "Timed out",
        "command-unavailable": "Command unavailable",
        "context-unavailable": "Context unavailable",
        "command-failed": "Command failed",
        "blocked-by-gating": "Blocked",
        "approval-missing-or-stale": "Approval needed",
        "unknown-failure": "Unknown failure",
      };
      return labels[failureClass] || failureClass.replace(/-/g, " ");
    }
    if (key.startsWith("timeout:")) {
      const cmd = key.slice(8);
      return cmd === "generic" ? "Timed out" : `${cmd} timed out`;
    }
    if (key.startsWith("failed:")) {
      const cmd = key.slice(7);
      return cmd === "generic" ? "Command failed" : `${cmd} failed`;
    }
    return "Similar failures";
  };

  // Group entries by failure key
  const groups = new Map<string, NextCheckExecutionHistoryEntry[]>();
  failureEntries.forEach((entry) => {
    const key = getFailureKey(entry);
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key)!.push(entry);
  });

  // Only include groups with 2+ entries (repeated)
  const repeated: RepeatedFailureGroup[] = [];
  groups.forEach((groupEntries, key) => {
    if (groupEntries.length >= 2) {
      repeated.push({
        failurePattern: key,
        count: groupEntries.length,
        entries: groupEntries,
        label: getFailureLabel(groupEntries[0], key),
      });
    }
  });

  // Sort by count descending, then by label
  repeated.sort((a, b) => {
    if (b.count !== a.count) {
      return b.count - a.count;
    }
    return a.label.localeCompare(b.label);
  });

  return repeated;
};

/**
 * Compute a run-scoped summary of execution history entries.
 */
export const computeExecutionHistorySummary = (
  entries: NextCheckExecutionHistoryEntry[]
): ExecutionHistorySummary => {
  // Most useful checks: entries with usefulnessClass = "useful"
  const usefulChecks = entries.filter((e) => e.usefulnessClass === "useful");

  // Noisy/empty checks: entries with usefulnessClass in ["noisy", "empty"]
  const noisyEmptyChecks = entries.filter((e) => e.usefulnessClass === "noisy" || e.usefulnessClass === "empty");

  // Repeated failures: detect patterns of repeated failures in the current run
  const repeatedFailures = detectRepeatedFailures(entries);

  return { usefulChecks, noisyEmptyChecks, repeatedFailures };
};
