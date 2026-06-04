/**
 * Unit tests for findExecutionHistoryEntry utility function.
 */
import { describe, it, expect } from "vitest";
import { findExecutionHistoryEntry } from "./findExecutionHistoryEntry";
import type { NextCheckQueueItem, NextCheckExecutionHistoryEntry } from "../types";

describe("findExecutionHistoryEntry", () => {
  const createHistoryEntry = (
    partial: Partial<NextCheckExecutionHistoryEntry>
  ): NextCheckExecutionHistoryEntry => ({
    artifactPath: partial.artifactPath ?? "",
    clusterLabel: partial.clusterLabel ?? "",
    candidateDescription: partial.candidateDescription ?? "",
    status: partial.status ?? "unknown",
    timestamp: partial.timestamp ?? "",
    durationSeconds: partial.durationSeconds ?? 0,
    errorMessage: partial.errorMessage ?? null,
    executionDetails: partial.executionDetails ?? null,
  });

  const createQueueItem = (
    partial: Partial<NextCheckQueueItem>
  ): NextCheckQueueItem => ({
    id: partial.id ?? "queue-item-1",
    description: partial.description ?? "",
    targetCluster: partial.targetCluster ?? null,
    latestArtifactPath: partial.latestArtifactPath ?? null,
    status: partial.status ?? "pending",
    priority: partial.priority ?? 0,
    command: partial.command ?? null,
    promotedBy: partial.promotedBy ?? null,
    promotedAt: partial.promotedAt ?? null,
    promotedByArtifact: partial.promotedByArtifact ?? null,
    promotedFromEntryId: partial.promotedFromEntryId ?? null,
    promotionReason: partial.promotionReason ?? null,
    promotionTimestamp: partial.promotionTimestamp ?? null,
    provenance: partial.provenance ?? null,
    latestArtifactTimestamp: partial.latestArtifactTimestamp ?? null,
    vmalertSource: partial.vmalertSource ?? null,
    workstream: partial.workstream ?? null,
    commandFamily: partial.commandFamily ?? null,
    runnableCheck: partial.runnableCheck ?? null,
    promotionCheck: partial.promotionCheck ?? null,
    feedback: partial.feedback ?? null,
    alertmanagerRelevance: partial.alertmanagerRelevance ?? null,
  });

  describe("empty history", () => {
    it("should return null when execution history is empty", () => {
      const candidate = createQueueItem({ description: "Test check" });
      const result = findExecutionHistoryEntry(candidate, []);
      expect(result).toBeNull();
    });

    it("should return null when execution history is undefined", () => {
      const candidate = createQueueItem({ description: "Test check" });
      // @ts-ignore - testing runtime behavior
      const result = findExecutionHistoryEntry(candidate, undefined);
      expect(result).toBeNull();
    });
  });

  describe("artifact path matching (priority 1)", () => {
    it("should match by exact artifact path", () => {
      const candidate = createQueueItem({
        latestArtifactPath: "/artifacts/run-123/execution-result.json",
      });
      const history: NextCheckExecutionHistoryEntry[] = [
        createHistoryEntry({
          artifactPath: "/artifacts/run-123/execution-result.json",
          candidateDescription: "Different description",
          clusterLabel: "cluster-a",
        }),
      ];

      const result = findExecutionHistoryEntry(candidate, history);
      expect(result).toEqual(history[0]);
    });

    it("should not match if artifact path does not match", () => {
      const candidate = createQueueItem({
        latestArtifactPath: "/artifacts/run-123/other-result.json",
      });
      const history: NextCheckExecutionHistoryEntry[] = [
        createHistoryEntry({
          artifactPath: "/artifacts/run-123/execution-result.json",
          candidateDescription: "Test description",
        }),
      ];

      const result = findExecutionHistoryEntry(candidate, history);
      expect(result).toBeNull();
    });

    it("should return null when candidate has no artifact path but history has artifact matches", () => {
      const candidate = createQueueItem({ latestArtifactPath: null });
      const history: NextCheckExecutionHistoryEntry[] = [
        createHistoryEntry({
          artifactPath: "/artifacts/run-123/execution-result.json",
        }),
      ];

      const result = findExecutionHistoryEntry(candidate, history);
      expect(result).toBeNull();
    });
  });

  describe("cluster + description matching (priority 2)", () => {
    it("should match by cluster label and description", () => {
      const candidate = createQueueItem({
        targetCluster: "cluster-a",
        description: "Check CPU usage",
      });
      const history: NextCheckExecutionHistoryEntry[] = [
        createHistoryEntry({
          artifactPath: "/different/path.json",
          clusterLabel: "cluster-a",
          candidateDescription: "Check CPU usage",
        }),
      ];

      const result = findExecutionHistoryEntry(candidate, history);
      expect(result).toEqual(history[0]);
    });

    it("should fall through to description-only match when cluster does not match", () => {
      const candidate = createQueueItem({
        targetCluster: "cluster-b",
        description: "Check CPU usage",
      });
      const history: NextCheckExecutionHistoryEntry[] = [
        createHistoryEntry({
          clusterLabel: "cluster-a",
          candidateDescription: "Check CPU usage",
        }),
      ];

      // Priority 2 (cluster+description) fails, but priority 3 (description-only) succeeds
      const result = findExecutionHistoryEntry(candidate, history);
      expect(result).toEqual(history[0]);
    });

    it("should not match if description does not match", () => {
      const candidate = createQueueItem({
        targetCluster: "cluster-a",
        description: "Check memory usage",
      });
      const history: NextCheckExecutionHistoryEntry[] = [
        createHistoryEntry({
          clusterLabel: "cluster-a",
          candidateDescription: "Check CPU usage",
        }),
      ];

      const result = findExecutionHistoryEntry(candidate, history);
      expect(result).toBeNull();
    });

    it("should trim whitespace from description for matching", () => {
      const candidate = createQueueItem({
        targetCluster: "cluster-a",
        description: "  Check CPU usage  ",
      });
      const history: NextCheckExecutionHistoryEntry[] = [
        createHistoryEntry({
          clusterLabel: "cluster-a",
          candidateDescription: "Check CPU usage",
        }),
      ];

      const result = findExecutionHistoryEntry(candidate, history);
      expect(result).toEqual(history[0]);
    });

    it("should fall through to description-only match when candidate has no target cluster", () => {
      const candidate = createQueueItem({
        targetCluster: null,
        description: "Check CPU usage",
      });
      const history: NextCheckExecutionHistoryEntry[] = [
        createHistoryEntry({
          clusterLabel: "cluster-a",
          candidateDescription: "Check CPU usage",
        }),
      ];

      // Priority 2 is skipped (no targetCluster), but priority 3 succeeds
      const result = findExecutionHistoryEntry(candidate, history);
      expect(result).toEqual(history[0]);
    });
  });

  describe("description-only matching (priority 3)", () => {
    it("should match by description only as fallback", () => {
      const candidate = createQueueItem({
        description: "Check disk space",
        targetCluster: null,
        latestArtifactPath: null,
      });
      const history: NextCheckExecutionHistoryEntry[] = [
        createHistoryEntry({
          clusterLabel: "cluster-x",
          candidateDescription: "Check disk space",
          artifactPath: "/other/path.json",
        }),
      ];

      const result = findExecutionHistoryEntry(candidate, history);
      expect(result).toEqual(history[0]);
    });

    it("should not match if no description in candidate", () => {
      const candidate = createQueueItem({
        description: "",
        targetCluster: null,
        latestArtifactPath: null,
      });
      const history: NextCheckExecutionHistoryEntry[] = [
        createHistoryEntry({
          candidateDescription: "Check disk space",
        }),
      ];

      const result = findExecutionHistoryEntry(candidate, history);
      expect(result).toBeNull();
    });
  });

  describe("matching priority", () => {
    it("should prefer artifact path match over cluster+description match", () => {
      const candidate = createQueueItem({
        latestArtifactPath: "/artifacts/first.json",
        targetCluster: "cluster-a",
        description: "Description A",
      });
      const history: NextCheckExecutionHistoryEntry[] = [
        createHistoryEntry({
          artifactPath: "/artifacts/first.json",
          clusterLabel: "cluster-a",
          candidateDescription: "Description A",
        }),
        createHistoryEntry({
          artifactPath: "/artifacts/second.json",
          clusterLabel: "cluster-a",
          candidateDescription: "Description A",
        }),
      ];

      const result = findExecutionHistoryEntry(candidate, history);
      expect(result?.artifactPath).toBe("/artifacts/first.json");
    });

    it("should prefer cluster+description match over description-only match", () => {
      const candidate = createQueueItem({
        targetCluster: "cluster-a",
        description: "Shared description",
        latestArtifactPath: null,
      });
      const history: NextCheckExecutionHistoryEntry[] = [
        createHistoryEntry({
          artifactPath: "/artifacts/second.json",
          clusterLabel: "cluster-b",
          candidateDescription: "Shared description",
        }),
        createHistoryEntry({
          artifactPath: "/artifacts/first.json",
          clusterLabel: "cluster-a",
          candidateDescription: "Shared description",
        }),
      ];

      const result = findExecutionHistoryEntry(candidate, history);
      expect(result?.artifactPath).toBe("/artifacts/first.json");
    });

    it("should return first match when multiple entries match", () => {
      const candidate = createQueueItem({
        description: "Common check",
        targetCluster: null,
        latestArtifactPath: null,
      });
      const history: NextCheckExecutionHistoryEntry[] = [
        createHistoryEntry({
          artifactPath: "/artifacts/first.json",
          candidateDescription: "Common check",
        }),
        createHistoryEntry({
          artifactPath: "/artifacts/second.json",
          candidateDescription: "Common check",
        }),
      ];

      const result = findExecutionHistoryEntry(candidate, history);
      expect(result?.artifactPath).toBe("/artifacts/first.json");
    });
  });

  describe("edge cases", () => {
    it("should handle empty description strings", () => {
      const candidate = createQueueItem({ description: "" });
      const history: NextCheckExecutionHistoryEntry[] = [
        createHistoryEntry({
          candidateDescription: "",
        }),
      ];

      const result = findExecutionHistoryEntry(candidate, history);
      // Empty strings should not match (trimmed description would be "")
      expect(result).toBeNull();
    });

    it("should handle null vs undefined descriptions", () => {
      const candidate = createQueueItem({ description: null as any });
      const history: NextCheckExecutionHistoryEntry[] = [
        createHistoryEntry({
          candidateDescription: "Test",
        }),
      ];

      const result = findExecutionHistoryEntry(candidate, history);
      expect(result).toBeNull();
    });
  });
});