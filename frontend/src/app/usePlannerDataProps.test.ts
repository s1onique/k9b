/**
 * Unit tests for usePlannerDataProps hook.
 */
import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { usePlannerDataProps } from "./usePlannerDataProps";
import type { RunPayload, ClusterDetailPayload, NextCheckPlanCandidate } from "../types";

describe("usePlannerDataProps", () => {
  // Helper to create minimal test fixtures
  const createRun = (partial: Partial<RunPayload> = {}): RunPayload =>
    ({
      runId: partial.runId ?? "run-1",
      label: partial.label ?? "Run 1",
      timestamp: partial.timestamp ?? "2026-06-01T00:00:00Z",
      collectorVersion: partial.collectorVersion ?? "1.0.0",
      clusterCount: partial.clusterCount ?? 1,
      nextCheckPlan: partial.nextCheckPlan ?? null,
      plannerAvailability: partial.plannerAvailability ?? null,
    }) as RunPayload;

  const createClusterDetail = (partial: Partial<ClusterDetailPayload> = {}): ClusterDetailPayload =>
    ({
      selectedClusterLabel: partial.selectedClusterLabel ?? null,
      selectedClusterContext: partial.selectedClusterContext ?? null,
      assessment: partial.assessment ?? null,
      findings: partial.findings ?? [],
      hypotheses: partial.hypotheses ?? [],
      nextChecks: partial.nextChecks ?? [],
      nextCheckPlan: partial.nextCheckPlan ?? [],
      nextCheckExecutionHistory: partial.nextCheckExecutionHistory ?? [],
    }) as ClusterDetailPayload;

  const createCandidate = (partial: Partial<NextCheckPlanCandidate> = {}): NextCheckPlanCandidate =>
    ({
      description: partial.description ?? "Test candidate",
      targetCluster: partial.targetCluster ?? null,
      sourceReason: partial.sourceReason ?? null,
      expectedSignal: partial.expectedSignal ?? null,
      suggestedCommandFamily: partial.suggestedCommandFamily ?? null,
      safeToAutomate: partial.safeToAutomate ?? false,
      requiresOperatorApproval: partial.requiresOperatorApproval ?? false,
      riskLevel: partial.riskLevel ?? "medium",
      estimatedCost: partial.estimatedCost ?? "low",
      confidence: partial.confidence ?? "medium",
      candidateId: partial.candidateId ?? "candidate-1",
      candidateIndex: partial.candidateIndex ?? 0,
      status: partial.status ?? "pending",
    }) as NextCheckPlanCandidate;

  describe("planCandidates derivation", () => {
    it("should return empty array when clusterDetail is null", () => {
      const { result } = renderHook(() => usePlannerDataProps({ run: null, clusterDetail: null }));
      expect(result.current.planCandidates).toEqual([]);
    });

    it("should return empty array when clusterDetail.nextCheckPlan is empty", () => {
      const run = createRun();
      const clusterDetail = createClusterDetail({ nextCheckPlan: [] });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail }));
      expect(result.current.planCandidates).toEqual([]);
    });

    it("should return cluster detail plan candidates", () => {
      const run = createRun();
      const candidates = [createCandidate({ description: "Cluster candidate" })];
      const clusterDetail = createClusterDetail({ nextCheckPlan: candidates });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail }));
      expect(result.current.planCandidates).toHaveLength(1);
      expect(result.current.planCandidates[0].description).toBe("Cluster candidate");
    });
  });

  describe("runPlan derivation", () => {
    it("should return undefined/null when run is null", () => {
      // run?.nextCheckPlan returns undefined when run is null (not null due to optional chaining)
      const { result } = renderHook(() => usePlannerDataProps({ run: null, clusterDetail: null }));
      // The actual value is undefined (not null) due to optional chaining behavior
      expect(result.current.runPlan).toBeFalsy(); // undefined or null are both falsy
    });

    it("should return run.nextCheckPlan", () => {
      const plan = {
        status: "completed",
        summary: "Test plan",
        artifactPath: null,
        reviewPath: null,
        enrichmentArtifactPath: null,
        candidateCount: 2,
        candidates: [createCandidate({ description: "Run candidate 1" }), createCandidate({ description: "Run candidate 2" })],
        orphanedApprovals: [],
        outcomeCounts: [],
        orphanedApprovalCount: 0,
      };
      const run = createRun({ nextCheckPlan: plan });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.runPlan).toBe(plan);
    });
  });

  describe("plannerAvailability derivation", () => {
    it("should return null when run is null", () => {
      const { result } = renderHook(() => usePlannerDataProps({ run: null, clusterDetail: null }));
      expect(result.current.plannerAvailability).toBeNull();
    });

    it("should return run.plannerAvailability", () => {
      const availability = {
        status: "ready",
        reason: "Provider ready",
        hint: "Consider running safe checks",
        artifactPath: "/artifacts/planner.json",
      };
      const run = createRun({ plannerAvailability: availability });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.plannerAvailability).toBe(availability);
      expect(result.current.plannerReason).toBe("Provider ready");
      expect(result.current.plannerHint).toBe("Consider running safe checks");
    });

    it("should handle null reason and hint", () => {
      const availability = { status: "ready" };
      const run = createRun({ plannerAvailability: availability as RunPayload["plannerAvailability"] });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.plannerReason).toBeUndefined();
      expect(result.current.plannerHint).toBeUndefined();
    });
  });

  describe("planSummaryText derivation", () => {
    it("should use runPlan.summary when available", () => {
      const plan = { summary: "Run plan summary" } as RunPayload["nextCheckPlan"];
      const run = createRun({ nextCheckPlan: { ...plan, status: "completed" } as RunPayload["nextCheckPlan"] });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.planSummaryText).toBe("Run plan summary");
    });

    it("should fall back to plannerReason when runPlan.summary is null", () => {
      const plan = { summary: null, status: "completed" } as RunPayload["nextCheckPlan"];
      const availability = { status: "ready", reason: "Provider reason text" };
      const run = createRun({ nextCheckPlan: plan, plannerAvailability: availability });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.planSummaryText).toBe("Provider reason text");
    });

    it("should use default text when both runPlan.summary and plannerReason are null", () => {
      const plan = { summary: null, status: "completed" } as RunPayload["nextCheckPlan"];
      const run = createRun({ nextCheckPlan: plan, plannerAvailability: null });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.planSummaryText).toBe("Provider-assisted next-check candidates are available.");
    });
  });

  describe("plannerReasonText derivation", () => {
    it("should use plannerReason when available", () => {
      const availability = { status: "ready", reason: "Specific reason" };
      const run = createRun({ plannerAvailability: availability });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.plannerReasonText).toBe("Specific reason");
    });

    it("should use fallback text when plannerReason is null", () => {
      const run = createRun({ plannerAvailability: { status: "ready" } });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.plannerReasonText).toBe("Planner data is not available for this run.");
    });
  });

  describe("planCandidateCountLabel derivation", () => {
    it("should use runPlan.candidateCount with singular", () => {
      const plan = {
        candidateCount: 1,
        candidates: [createCandidate()],
        status: "completed",
      } as RunPayload["nextCheckPlan"];
      const run = createRun({ nextCheckPlan: plan });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.planCandidateCountLabel).toBe("1 candidate");
    });

    it("should use runPlan.candidateCount with plural", () => {
      const plan = {
        candidateCount: 5,
        candidates: [createCandidate(), createCandidate()],
        status: "completed",
      } as RunPayload["nextCheckPlan"];
      const run = createRun({ nextCheckPlan: plan });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.planCandidateCountLabel).toBe("5 candidates");
    });

    it("should fall back to cluster detail planCandidates length with singular", () => {
      const candidates = [createCandidate({ description: "Only one" })];
      const clusterDetail = createClusterDetail({ nextCheckPlan: candidates });
      const run = createRun({ nextCheckPlan: { candidateCount: null, candidates: [], status: "pending" } as RunPayload["nextCheckPlan"] });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail }));
      expect(result.current.planCandidateCountLabel).toBe("1 candidate");
    });

    it("should fall back to cluster detail planCandidates length with plural", () => {
      const candidates = [createCandidate(), createCandidate(), createCandidate()];
      const clusterDetail = createClusterDetail({ nextCheckPlan: candidates });
      const run = createRun({ nextCheckPlan: { candidateCount: null, candidates: [], status: "pending" } as RunPayload["nextCheckPlan"] });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail }));
      expect(result.current.planCandidateCountLabel).toBe("3 candidates");
    });
  });

  describe("planStatusText derivation", () => {
    it("should return runPlan.status", () => {
      const plan = { status: "completed", summary: null } as RunPayload["nextCheckPlan"];
      const run = createRun({ nextCheckPlan: plan });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.planStatusText).toBe("completed");
    });

    it("should return null when runPlan.status is null", () => {
      const plan = { status: null, summary: null } as RunPayload["nextCheckPlan"];
      const run = createRun({ nextCheckPlan: plan });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.planStatusText).toBeNull();
    });
  });

  describe("runPlanCandidates derivation", () => {
    it("should return empty array when runPlan is null", () => {
      const { result } = renderHook(() => usePlannerDataProps({ run: null, clusterDetail: null }));
      expect(result.current.runPlanCandidates).toEqual([]);
    });

    it("should return runPlan.candidates", () => {
      const candidates = [
        createCandidate({ description: "Candidate 1" }),
        createCandidate({ description: "Candidate 2" }),
      ];
      const plan = {
        candidates,
        status: "completed",
        summary: null,
        candidateCount: 2,
      } as RunPayload["nextCheckPlan"];
      const run = createRun({ nextCheckPlan: plan });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.runPlanCandidates).toHaveLength(2);
      expect(result.current.runPlanCandidates[0].description).toBe("Candidate 1");
    });
  });

  describe("discoveryVariantOrder derivation", () => {
    it("should return DISCOVERY_VARIANT_ORDER constant", () => {
      const { result } = renderHook(() => usePlannerDataProps({ run: null, clusterDetail: null }));
      // Order should be: safe, approval, approved, stale, duplicate, failed, unknown
      expect(result.current.discoveryVariantOrder).toContain("safe");
      expect(result.current.discoveryVariantOrder).toContain("approval");
      expect(result.current.discoveryVariantOrder).toContain("approved");
    });
  });

  describe("discoveryVariantCounts derivation", () => {
    it("should return zero counts for empty candidates", () => {
      const { result } = renderHook(() => usePlannerDataProps({ run: null, clusterDetail: null }));
      // buildDiscoveryVariantCounts returns only: safe, approval, approved, duplicate, stale
      expect(result.current.discoveryVariantCounts).toEqual({
        safe: 0,
        approval: 0,
        approved: 0,
        duplicate: 0,
        stale: 0,
      });
    });

    it("should count candidates by variant using requiresOperatorApproval and approvalStatus", () => {
      // Safe candidates (default)
      const safeCandidates = [
        createCandidate({ requiresOperatorApproval: false }),
        createCandidate({ requiresOperatorApproval: false }),
      ];
      // Approval candidates
      const approvalCandidates = [
        createCandidate({ requiresOperatorApproval: true, approvalStatus: "pending" }),
      ];
      const plan = {
        candidates: [...safeCandidates, ...approvalCandidates],
        status: "completed",
        summary: null,
        candidateCount: 3,
      } as RunPayload["nextCheckPlan"];
      const run = createRun({ nextCheckPlan: plan });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.discoveryVariantCounts).toEqual({
        safe: 2,
        approval: 1,
        approved: 0,
        duplicate: 0,
        stale: 0,
      });
    });
  });

  describe("discoveryClusters derivation", () => {
    it("should return empty array when no candidates", () => {
      const { result } = renderHook(() => usePlannerDataProps({ run: null, clusterDetail: null }));
      expect(result.current.discoveryClusters).toEqual([]);
    });

    it("should return unique cluster labels from candidates", () => {
      const candidates = [
        createCandidate({ targetCluster: "cluster-a" }),
        createCandidate({ targetCluster: "cluster-b" }),
        createCandidate({ targetCluster: "cluster-a" }), // duplicate
        createCandidate({ targetCluster: null }), // null should be filtered
      ];
      const plan = {
        candidates,
        status: "completed",
        summary: null,
        candidateCount: 4,
      } as RunPayload["nextCheckPlan"];
      const run = createRun({ nextCheckPlan: plan });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.discoveryClusters).toHaveLength(2);
      expect(result.current.discoveryClusters).toContain("cluster-a");
      expect(result.current.discoveryClusters).toContain("cluster-b");
    });

    it("should filter out null and empty string cluster labels", () => {
      const candidates = [
        createCandidate({ targetCluster: null }),
        createCandidate({ targetCluster: "" }),
        createCandidate({ targetCluster: "valid-cluster" }),
      ];
      const plan = {
        candidates,
        status: "completed",
        summary: null,
        candidateCount: 3,
      } as RunPayload["nextCheckPlan"];
      const run = createRun({ nextCheckPlan: plan });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.discoveryClusters).toHaveLength(1);
      expect(result.current.discoveryClusters[0]).toBe("valid-cluster");
    });
  });

  describe("plannerArtifactPath derivation", () => {
    it("should use plannerAvailability.artifactPath", () => {
      const availability = { status: "ready", artifactPath: "/artifacts/availability.json" };
      const plan = { artifactPath: "/artifacts/plan.json", status: "completed", summary: null } as RunPayload["nextCheckPlan"];
      const run = createRun({ plannerAvailability: availability, nextCheckPlan: plan });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.plannerArtifactPath).toBe("/artifacts/availability.json");
    });

    it("should fall back to runPlan.artifactPath when availability artifactPath is null", () => {
      const availability = { status: "ready", artifactPath: null };
      const plan = { artifactPath: "/artifacts/plan.json", status: "completed", summary: null } as RunPayload["nextCheckPlan"];
      const run = createRun({ plannerAvailability: availability, nextCheckPlan: plan });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.plannerArtifactPath).toBe("/artifacts/plan.json");
    });

    it("should return null when both are null", () => {
      const availability = { status: "ready", artifactPath: null };
      const plan = { artifactPath: null, status: "completed", summary: null } as RunPayload["nextCheckPlan"];
      const run = createRun({ plannerAvailability: availability, nextCheckPlan: plan });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.plannerArtifactPath).toBeNull();
    });
  });

  describe("plannerArtifactUrl derivation", () => {
    it("should be null when plannerArtifactPath is null", () => {
      const { result } = renderHook(() => usePlannerDataProps({ run: null, clusterDetail: null }));
      expect(result.current.plannerArtifactUrl).toBeNull();
    });

    it("should be a valid URL when artifactPath is present", () => {
      const availability = { status: "ready", artifactPath: "/artifacts/test.json" };
      const run = createRun({ plannerAvailability: availability });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.plannerArtifactUrl).toBeTruthy();
      expect(typeof result.current.plannerArtifactUrl).toBe("string");
    });
  });

  describe("plannerNextActionHint derivation", () => {
    it("should return undefined when not set", () => {
      const availability = { status: "ready" };
      const run = createRun({ plannerAvailability: availability });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.plannerNextActionHint).toBeUndefined();
    });

    it("should return nextActionHint when set", () => {
      const availability = { status: "ready", nextActionHint: "Run the suggested checks" };
      const run = createRun({ plannerAvailability: availability });
      const { result } = renderHook(() => usePlannerDataProps({ run, clusterDetail: null }));
      expect(result.current.plannerNextActionHint).toBe("Run the suggested checks");
    });
  });
});