/**
 * findExecutionHistoryEntry — pure utility for matching queue items to execution history.
 *
 * Extracted from App.tsx as part of the App.tsx size reduction initiative.
 *
 * Matching priority:
 * 1. Artifact path match (exact)
 * 2. Cluster + description match (context-sensitive)
 * 3. Description-only match (fallback)
 *
 * @module app
 */
import type { NextCheckQueueItem, NextCheckExecutionHistoryEntry } from "../types";

/**
 * Find the execution history entry that corresponds to a queue item.
 *
 * @param candidate - The queue item to match
 * @param executionHistory - The execution history entries to search
 * @returns The matching execution history entry, or null if no match found
 */
export function findExecutionHistoryEntry(
  candidate: NextCheckQueueItem,
  executionHistory: NextCheckExecutionHistoryEntry[] | undefined | null
): NextCheckExecutionHistoryEntry | null {
  if (!executionHistory || !executionHistory.length) {
    return null;
  }

  // Priority 1: Match by artifact path (exact match)
  if (candidate.latestArtifactPath) {
    const artifactMatch = executionHistory.find(
      (entry) => entry.artifactPath === candidate.latestArtifactPath
    );
    if (artifactMatch) {
      return artifactMatch;
    }
  }

  // Priority 2: Match by cluster + description (context-sensitive)
  const normalizedDescription = candidate.description?.trim();
  if (candidate.targetCluster && normalizedDescription) {
    const contextMatch = executionHistory.find(
      (entry) =>
        entry.clusterLabel === candidate.targetCluster &&
        entry.candidateDescription === normalizedDescription
    );
    if (contextMatch) {
      return contextMatch;
    }
  }

  // Priority 3: Match by description only (fallback)
  if (normalizedDescription) {
    const descriptionMatch = executionHistory.find(
      (entry) => entry.candidateDescription === normalizedDescription
    );
    if (descriptionMatch) {
      return descriptionMatch;
    }
  }

  return null;
}