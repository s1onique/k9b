/**
 * Focused unit tests for selectors.ts — pure helpers extracted from App.tsx.
 * These are pure functions with deterministic inputs/outputs.
 */
import { describe, expect, it } from "vitest";
import dayjs from "dayjs";
import {
  confidenceWeight,
  priorityLabel,
  getPageFreshnessLevel,
  getRunFreshnessLevel,
  formatAgeDuration,
  parseNextCheckEntry,
  computeRunsFilterCounts,
  queuePriorityRank,
  normalizeQueuePriority,
  formatAlertmanagerPromotion,
  getAlertmanagerPromotionSubtext,
  formatAlertmanagerProvenance,
  getAlertmanagerProvenanceSubtext,
  formatFeedbackAdaptationProvenance,
  formatFeedbackSummary,
  getFeedbackAdaptationProvenanceSubtext,
  determineNextCheckStatusVariant,
  nextCheckStatusLabel,
  buildLlmStatEntries,
  buildDiscoveryVariantCounts,
} from "../selectors";
import type { NextCheckPlanCandidate } from "../../types";

// ==========================================================================
// Confidence helpers
// ==========================================================================

describe("confidenceWeight", () => {
  it("ranks critical first", () => {
    expect(confidenceWeight("critical")).toBeLessThan(confidenceWeight("high"));
    expect(confidenceWeight("critical")).toBeLessThan(confidenceWeight("medium"));
    expect(confidenceWeight("critical")).toBeLessThan(confidenceWeight("low"));
  });

  it("handles unknown tier as last", () => {
    expect(confidenceWeight("unknown")).toBeGreaterThan(confidenceWeight("low"));
  });

  it("is case-insensitive", () => {
    expect(confidenceWeight("CRITICAL")).toBe(0);
    expect(confidenceWeight("High")).toBe(1);
  });
});

describe("priorityLabel", () => {
  it("maps confidence tiers to labels", () => {
    expect(priorityLabel("critical")).toBe("critical");
    expect(priorityLabel("HIGH")).toBe("high");
    expect(priorityLabel("Medium")).toBe("medium");
    expect(priorityLabel("low")).toBe("low");
  });

  it("returns default for unknown", () => {
    expect(priorityLabel("foobar")).toBe("default");
  });
});

// ==========================================================================
// Freshness helpers
// ==========================================================================

describe("getPageFreshnessLevel", () => {
  it("returns fresh for <= 30 seconds", () => {
    const now = dayjs();
    expect(getPageFreshnessLevel(now)).toBe("fresh");
    expect(getPageFreshnessLevel(now.subtract(29, "second"))).toBe("fresh");
  });

  it("returns warning for > 30s and < 3 minutes", () => {
    expect(getPageFreshnessLevel(dayjs().subtract(31, "second"))).toBe("warning");
    expect(getPageFreshnessLevel(dayjs().subtract(179, "second"))).toBe("warning");
  });

  it("returns stale for >= 3 minutes", () => {
    expect(getPageFreshnessLevel(dayjs().subtract(180, "second"))).toBe("stale");
    expect(getPageFreshnessLevel(dayjs().subtract(10, "minute"))).toBe("stale");
  });
});

describe("getRunFreshnessLevel", () => {
  it("returns fresh for <= 15 minutes", () => {
    expect(getRunFreshnessLevel(dayjs().subtract(15, "minute").toISOString())).toBe("fresh");
  });

  it("returns warning for > 15m and <= 45m", () => {
    expect(getRunFreshnessLevel(dayjs().subtract(16, "minute").toISOString())).toBe("warning");
    expect(getRunFreshnessLevel(dayjs().subtract(45, "minute").toISOString())).toBe("warning");
  });

  it("returns stale for > 45 minutes", () => {
    expect(getRunFreshnessLevel(dayjs().subtract(46, "minute").toISOString())).toBe("stale");
  });
});

// ==========================================================================
// Duration formatting
// ==========================================================================

describe("formatAgeDuration", () => {
  it("handles negative input", () => {
    expect(formatAgeDuration(-5)).toBe("—");
  });

  it("formats under 1 hour as minutes", () => {
    expect(formatAgeDuration(0)).toBe("0 minutes");
    expect(formatAgeDuration(1)).toBe("1 minute");
    expect(formatAgeDuration(59)).toBe("59 minutes");
  });

  it("formats under 1 day as hours and minutes", () => {
    expect(formatAgeDuration(60)).toBe("1 hour");
    expect(formatAgeDuration(61)).toBe("1 hour 1 minute");
    expect(formatAgeDuration(90)).toBe("1 hour 30 minutes");
    expect(formatAgeDuration(119)).toBe("1 hour 59 minutes");
  });

  it("formats 1+ days as days, hours, minutes", () => {
    expect(formatAgeDuration(1440)).toBe("1 day");
    expect(formatAgeDuration(1441)).toBe("1 day 1 minute");
    expect(formatAgeDuration(1500)).toBe("1 day 1 hour");
    expect(formatAgeDuration(1500 + 30)).toBe("1 day 1 hour 30 minutes");
  });

  it("handles pluralization correctly", () => {
    expect(formatAgeDuration(2)).toBe("2 minutes");
    expect(formatAgeDuration(120)).toBe("2 hours");
    expect(formatAgeDuration(2880)).toBe("2 days");
  });
});

// ==========================================================================
// Next-check entry parsing
// ==========================================================================

describe("parseNextCheckEntry", () => {
  it("parses intent only", () => {
    const result = parseNextCheckEntry("Check pod status in default namespace");
    expect(result.intent).toBe("Check pod status in default namespace");
    expect(result.targetCluster).toBeNull();
    expect(result.commandPreview).toBeNull();
  });

  it("extracts cluster prefix", () => {
    const result = parseNextCheckEntry("[prod-cluster-1] Check deployment replicas");
    expect(result.targetCluster).toBe("prod-cluster-1");
    expect(result.intent).toBe("Check deployment replicas");
    expect(result.commandPreview).toBeNull();
  });

  it("extracts kubectl command preview", () => {
    const result = parseNextCheckEntry("Check pod status: kubectl get pods -n default");
    expect(result.intent).toBe("Check pod status");
    expect(result.commandPreview).toBe("kubectl get pods -n default");
  });

  it("extracts cluster prefix AND command preview", () => {
    const result = parseNextCheckEntry("[staging] Scale check: kubectl scale deployment api --replicas=3");
    expect(result.targetCluster).toBe("staging");
    expect(result.intent).toBe("Scale check");
    expect(result.commandPreview).toBe("kubectl scale deployment api --replicas=3");
  });

  it("handles k9s command", () => {
    const result = parseNextCheckEntry("View logs: k9s -n monitoring");
    expect(result.intent).toBe("View logs");
    expect(result.commandPreview).toBe("k9s -n monitoring");
  });

  it("handles pure command without prefix", () => {
    const result = parseNextCheckEntry("kubectl get pods");
    expect(result.intent).toBe("kubectl get pods");
    expect(result.commandPreview).toBeNull();
  });

  it("truncates long intents", () => {
    const longIntent = "A".repeat(150);
    const result = parseNextCheckEntry(longIntent);
    expect(result.intent.length).toBeLessThanOrEqual(120);
  });

  it("handles edge case cluster names", () => {
    const result = parseNextCheckEntry("[a] Simple check");
    expect(result.targetCluster).toBe("a");
  });

  it("handles empty input", () => {
    const result = parseNextCheckEntry("");
    expect(result.intent).toBe("");
    expect(result.targetCluster).toBeNull();
  });
});

// ==========================================================================
// Runs filter counts
// ==========================================================================

describe("computeRunsFilterCounts", () => {
  it("counts all runs", () => {
    const runs = [
      { runId: "1", reviewStatus: "unreviewed" },
      { runId: "2", reviewStatus: "fully-reviewed" },
    ] as any[];
    expect(computeRunsFilterCounts(runs).all).toBe(2);
  });

  it("counts no-executions", () => {
    const runs = [
      { runId: "1", reviewStatus: "no-executions" },
      { runId: "2", reviewStatus: "no-executions" },
    ] as any[];
    expect(computeRunsFilterCounts(runs)["no-executions"]).toBe(2);
  });

  it("counts awaiting-review", () => {
    const runs = [{ runId: "1", reviewStatus: "unreviewed" }] as any[];
    expect(computeRunsFilterCounts(runs)["awaiting-review"]).toBe(1);
  });

  it("counts partially-reviewed", () => {
    const runs = [{ runId: "1", reviewStatus: "partially-reviewed" }] as any[];
    expect(computeRunsFilterCounts(runs)["partially-reviewed"]).toBe(1);
  });

  it("counts fully-reviewed", () => {
    const runs = [{ runId: "1", reviewStatus: "fully-reviewed" }] as any[];
    expect(computeRunsFilterCounts(runs)["fully-reviewed"]).toBe(1);
  });

  it("counts needs-attention from unreviewed + partially-reviewed", () => {
    const runs = [
      { runId: "1", reviewStatus: "unreviewed" },
      { runId: "2", reviewStatus: "partially-reviewed" },
    ] as any[];
    expect(computeRunsFilterCounts(runs)["needs-attention"]).toBe(2);
  });

  it("handles empty array", () => {
    const result = computeRunsFilterCounts([]);
    expect(result.all).toBe(0);
    expect(result["awaiting-review"]).toBe(0);
  });
});

// ==========================================================================
// Queue priority helpers
// ==========================================================================

describe("normalizeQueuePriority", () => {
  it("normalizes to lowercase", () => {
    expect(normalizeQueuePriority("PRIMARY")).toBe("primary");
    expect(normalizeQueuePriority("Secondary")).toBe("secondary");
  });

  it("handles null/undefined", () => {
    expect(normalizeQueuePriority(null)).toBe("unknown");
    expect(normalizeQueuePriority(undefined)).toBe("unknown");
  });
});

describe("queuePriorityRank", () => {
  it("ranks primary < secondary < fallback", () => {
    expect(queuePriorityRank("primary")).toBeLessThan(queuePriorityRank("secondary"));
    expect(queuePriorityRank("secondary")).toBeLessThan(queuePriorityRank("fallback"));
  });

  it("ranks unknown as last", () => {
    expect(queuePriorityRank("unknown")).toBeGreaterThan(queuePriorityRank("fallback"));
  });
});

// ==========================================================================
// Next-check status helpers
// ==========================================================================

describe("determineNextCheckStatusVariant", () => {
  const makeCandidate = (overrides: Partial<NextCheckPlanCandidate> = {}): NextCheckPlanCandidate =>
    ({
      candidateId: "test-1",
      targetCluster: "test-cluster",
      suggestedCommandFamily: "kubectl-get",
      safeToAutomate: true,
      requiresOperatorApproval: false,
      duplicateOfExistingEvidence: false,
      approvalStatus: undefined,
      ...overrides,
    } as NextCheckPlanCandidate);

  it("returns 'duplicate' when duplicateOfExistingEvidence is true", () => {
    expect(determineNextCheckStatusVariant(makeCandidate({ duplicateOfExistingEvidence: true }))).toBe(
      "duplicate"
    );
  });

  it("returns 'safe' when no approval required", () => {
    expect(determineNextCheckStatusVariant(makeCandidate())).toBe("safe");
  });

  it("returns 'approved' when approved", () => {
    expect(
      determineNextCheckStatusVariant(
        makeCandidate({ requiresOperatorApproval: true, approvalStatus: "approved" })
      )
    ).toBe("approved");
  });

  it("returns 'stale' when approval is stale", () => {
    expect(
      determineNextCheckStatusVariant(
        makeCandidate({ requiresOperatorApproval: true, approvalStatus: "approval-stale" })
      )
    ).toBe("stale");
  });

  it("returns 'approval' when approval required but not approved", () => {
    expect(
      determineNextCheckStatusVariant(
        makeCandidate({ requiresOperatorApproval: true, approvalStatus: "approval-required" })
      )
    ).toBe("approval");
  });
});

describe("buildDiscoveryVariantCounts", () => {
  const makeCandidate = (overrides: Partial<NextCheckPlanCandidate> = {}): NextCheckPlanCandidate =>
    ({
      candidateId: "test-1",
      targetCluster: "test-cluster",
      suggestedCommandFamily: "kubectl-get",
      safeToAutomate: true,
      requiresOperatorApproval: false,
      duplicateOfExistingEvidence: false,
      approvalStatus: undefined,
      ...overrides,
    } as NextCheckPlanCandidate);

  it("returns zero counts for empty array", () => {
    const result = buildDiscoveryVariantCounts([]);
    expect(result).toEqual({
      safe: 0,
      approval: 0,
      approved: 0,
      duplicate: 0,
      stale: 0,
    });
  });

  it("counts safe candidates", () => {
    const candidates = [
      makeCandidate(),
      makeCandidate({ candidateId: "test-2" }),
      makeCandidate({ candidateId: "test-3" }),
    ];
    const result = buildDiscoveryVariantCounts(candidates);
    expect(result.safe).toBe(3);
  });

  it("counts approval-needed candidates", () => {
    const candidates = [
      makeCandidate({ requiresOperatorApproval: true, approvalStatus: "approval-required" }),
      makeCandidate({ requiresOperatorApproval: true, approvalStatus: "approval-required" }),
    ];
    const result = buildDiscoveryVariantCounts(candidates);
    expect(result.approval).toBe(2);
    expect(result.safe).toBe(0);
  });

  it("counts approved candidates", () => {
    const candidates = [
      makeCandidate({ requiresOperatorApproval: true, approvalStatus: "approved" }),
    ];
    const result = buildDiscoveryVariantCounts(candidates);
    expect(result.approved).toBe(1);
    expect(result.approval).toBe(0);
  });

  it("counts stale candidates", () => {
    const candidates = [
      makeCandidate({ requiresOperatorApproval: true, approvalStatus: "approval-stale" }),
    ];
    const result = buildDiscoveryVariantCounts(candidates);
    expect(result.stale).toBe(1);
  });

  it("counts duplicate candidates", () => {
    const candidates = [
      makeCandidate({ duplicateOfExistingEvidence: true }),
      makeCandidate({ duplicateOfExistingEvidence: true }),
      makeCandidate({ duplicateOfExistingEvidence: true }),
    ];
    const result = buildDiscoveryVariantCounts(candidates);
    expect(result.duplicate).toBe(3);
  });

  it("counts mixed variants correctly", () => {
    const candidates = [
      makeCandidate(), // safe
      makeCandidate({ requiresOperatorApproval: true, approvalStatus: "approval-required" }), // approval
      makeCandidate({ requiresOperatorApproval: true, approvalStatus: "approved" }), // approved
      makeCandidate({ duplicateOfExistingEvidence: true }), // duplicate
      makeCandidate({ requiresOperatorApproval: true, approvalStatus: "approval-stale" }), // stale
      makeCandidate(), // safe
    ];
    const result = buildDiscoveryVariantCounts(candidates);
    expect(result).toEqual({
      safe: 2,
      approval: 1,
      approved: 1,
      duplicate: 1,
      stale: 1,
    });
  });

  it("is deterministic - same input always gives same output", () => {
    const candidates = [
      makeCandidate({ requiresOperatorApproval: true, approvalStatus: "approval-required" }),
      makeCandidate({ duplicateOfExistingEvidence: true }),
      makeCandidate(),
    ];
    const first = buildDiscoveryVariantCounts(candidates);
    const second = buildDiscoveryVariantCounts(candidates);
    expect(first).toEqual(second);
  });
});

describe("nextCheckStatusLabel", () => {
  it("returns correct labels for each variant", () => {
    expect(nextCheckStatusLabel("safe")).toBe("Safe candidate");
    expect(nextCheckStatusLabel("approval")).toBe("Approval needed");
    expect(nextCheckStatusLabel("approved")).toBe("Approved candidate");
    expect(nextCheckStatusLabel("duplicate")).toBe("Duplicate / already covered");
    expect(nextCheckStatusLabel("stale")).toBe("Approval stale");
  });
});

// ==========================================================================
// LLM stats helpers
// ==========================================================================

describe("buildLlmStatEntries", () => {
  it("returns entries with Run LLM scope", () => {
    const stats = {
      totalCalls: 10,
      successfulCalls: 8,
      failedCalls: 2,
      p50LatencyMs: 100,
      p95LatencyMs: 200,
      p99LatencyMs: 300,
      lastCallTimestamp: "2024-01-01T00:00:00Z",
      scope: undefined,
    } as any;
    const entries = buildLlmStatEntries(stats);
    expect(entries[0].label).toBe("Run LLM calls");
    expect(entries[0].value).toBe("10");
  });

  it("returns entries with Historical LLM scope", () => {
    const stats = {
      totalCalls: 5,
      successfulCalls: 5,
      failedCalls: 0,
      p50LatencyMs: 50,
      p95LatencyMs: 100,
      p99LatencyMs: 150,
      lastCallTimestamp: null,
      scope: "retained_history",
    } as any;
    const entries = buildLlmStatEntries(stats);
    expect(entries[0].label).toBe("Historical LLM calls");
    expect(entries[6].value).toBe("—"); // Last call when null
  });
});

// ==========================================================================
// Alertmanager provenance formatters
// ==========================================================================

describe("formatAlertmanagerPromotion", () => {
  it("parses namespace match with plural (s)", () => {
    const result = formatAlertmanagerPromotion(
      "alertmanager-context:promoted:matched namespace(s): monitoring"
    );
    // The (s) is part of the dimension name, so it becomes "namespaces"
    expect(result).toBe("Matched namespaces: monitoring");
  });

  it("parses singular namespace", () => {
    const result = formatAlertmanagerPromotion(
      "alertmanager-context:promoted:matched namespace: monitoring"
    );
    expect(result).toBe("Matched namespace: monitoring");
  });

  it("parses cluster match", () => {
    const result = formatAlertmanagerPromotion(
      "alertmanager-context:promoted:matched cluster: prod-us-east"
    );
    expect(result).toBe("Matched cluster: prod-us-east");
  });

  it("handles malformed input gracefully", () => {
    expect(formatAlertmanagerPromotion("")).toBe("Promoted by Alertmanager");
    expect(formatAlertmanagerPromotion("invalid")).toBe("Promoted by Alertmanager");
  });
});

describe("getAlertmanagerPromotionSubtext", () => {
  it("returns subtext for valid match", () => {
    const result = getAlertmanagerPromotionSubtext(
      "alertmanager-context:promoted:matched namespace: monitoring"
    );
    expect(result).toBe("Ranking influenced by Alertmanager snapshot for selected run");
  });

  it("returns null for malformed input", () => {
    expect(getAlertmanagerPromotionSubtext("invalid")).toBeNull();
  });
});

describe("formatAlertmanagerProvenance", () => {
  it("formats empty provenance", () => {
    const result = formatAlertmanagerProvenance({
      matchedDimensions: [],
      matchedValues: {},
      appliedBonus: 0,
    });
    expect(result).toBe("Promoted by Alertmanager");
  });

  it("formats single dimension", () => {
    const result = formatAlertmanagerProvenance({
      matchedDimensions: ["namespace"],
      matchedValues: { namespace: ["monitoring", "logging"] },
      appliedBonus: 5,
    });
    expect(result).toBe("Matched namespace: monitoring, logging (+5)");
  });

  it("formats multiple dimensions", () => {
    const result = formatAlertmanagerProvenance({
      matchedDimensions: ["namespace", "cluster"],
      matchedValues: { namespace: ["monitoring"], cluster: ["us-east-1"] },
      appliedBonus: 0,
    });
    expect(result).toBe("Matched namespace: monitoring, cluster: us-east-1");
  });
});

describe("getAlertmanagerProvenanceSubtext", () => {
  it("returns empty string for minimal provenance", () => {
    const result = getAlertmanagerProvenanceSubtext({
      matchedDimensions: [],
      matchedValues: {},
      appliedBonus: 0,
      baseBonus: 0,
      severitySummary: {},
      signalStatus: undefined,
    });
    expect(result).toBe("Ranking influenced by Alertmanager snapshot");
  });

  it("includes bonus when applied", () => {
    const result = getAlertmanagerProvenanceSubtext({
      matchedDimensions: ["namespace"],
      matchedValues: { namespace: ["monitoring"] },
      appliedBonus: 5,
      baseBonus: 5,
      severitySummary: {},
      signalStatus: undefined,
    });
    expect(result).toContain("Bonus: 5");
  });

  it("includes severity when present", () => {
    const result = getAlertmanagerProvenanceSubtext({
      matchedDimensions: ["namespace"],
      matchedValues: { namespace: ["monitoring"] },
      appliedBonus: 0,
      baseBonus: 0,
      severitySummary: { critical: 2, warning: 5 },
      signalStatus: "firing",
    });
    expect(result).toContain("Severity");
    expect(result).toContain("Signal");
  });
});

// ==========================================================================
// Feedback provenance formatters
// ==========================================================================

describe("formatFeedbackAdaptationProvenance", () => {
  it("returns 'No feedback adaptation' when feedbackAdaptation is false", () => {
    expect(formatFeedbackAdaptationProvenance({ feedbackAdaptation: false } as any)).toBe(
      "No feedback adaptation"
    );
  });

  it("includes adaptation reason when present", () => {
    const result = formatFeedbackAdaptationProvenance({
      feedbackAdaptation: true,
      adaptationReason: "Based on recent run",
      suppressedBonus: 0,
      penaltyApplied: 0,
    });
    expect(result).toContain("Based on recent run");
  });

  it("includes suppressed bonus", () => {
    const result = formatFeedbackAdaptationProvenance({
      feedbackAdaptation: true,
      adaptationReason: null,
      suppressedBonus: 10,
      penaltyApplied: 0,
    });
    expect(result).toContain("Suppressed: 10");
  });
});

describe("formatFeedbackSummary", () => {
  it("handles legacy string fallback", () => {
    const result = formatFeedbackSummary({ summaryText: "Legacy feedback text" } as any);
    expect(result).toBe("Legacy feedback text");
  });

  it("formats structured feedback", () => {
    const result = formatFeedbackSummary({
      summaryText: undefined,
      totalEntries: 5,
      namespacesWithFeedback: ["ns1", "ns2"],
      clustersWithFeedback: ["cluster1"],
      servicesWithFeedback: [],
    });
    expect(result).toContain("5 entries");
    expect(result).toContain("2 ns");
    expect(result).toContain("1 cluster(s)");
  });

  it("returns 'No feedback' for empty summary", () => {
    const result = formatFeedbackSummary({
      summaryText: undefined,
      totalEntries: 0,
      namespacesWithFeedback: [],
      clustersWithFeedback: [],
      servicesWithFeedback: [],
    });
    expect(result).toBe("No feedback");
  });
});

describe("getFeedbackAdaptationProvenanceSubtext", () => {
  it("returns default text for minimal provenance", () => {
    const result = getFeedbackAdaptationProvenanceSubtext({
      feedbackAdaptation: false,
      adaptationReason: null,
      suppressedBonus: 0,
      penaltyApplied: 0,
      originalBonus: 0,
      explanation: null,
      feedbackSummary: null,
    });
    expect(result).toBe("Feedback adaptation applied");
  });

  it("includes original bonus", () => {
    const result = getFeedbackAdaptationProvenanceSubtext({
      feedbackAdaptation: true,
      adaptationReason: null,
      suppressedBonus: 5,
      penaltyApplied: 0,
      originalBonus: 10,
      explanation: null,
      feedbackSummary: null,
    });
    expect(result).toContain("Original bonus: 10");
    expect(result).toContain("Suppressed: 5");
  });

  it("includes explanation when present", () => {
    const result = getFeedbackAdaptationProvenanceSubtext({
      feedbackAdaptation: true,
      adaptationReason: null,
      suppressedBonus: 0,
      penaltyApplied: 0,
      originalBonus: 0,
      explanation: "Used for scaling decisions",
      feedbackSummary: null,
    });
    expect(result).toContain("Explanation: Used for scaling decisions");
  });
});