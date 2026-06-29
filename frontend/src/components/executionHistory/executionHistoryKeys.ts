/**
 * executionHistoryKeys.ts
 *
 * Key building utilities for ExecutionHistory components.
 */

import type { NextCheckExecutionHistoryEntry, NextCheckQueueItem } from "../../types";

/**
 * Build a unique key for an execution history entry
 */
export const buildExecutionEntryKey = (entry: NextCheckExecutionHistoryEntry) =>
  `${entry.clusterLabel ?? "global"}::${entry.candidateDescription ?? ""}::${entry.timestamp ?? ""}::${
    entry.artifactPath ?? ""
  }`;

/**
 * Build a unique key for a queue candidate
 */
export const buildCandidateKey = (candidate: NextCheckQueueItem, index: number) =>
  `next-check-${candidate.candidateId ?? candidate.candidateIndex ?? index}-${index}`;
