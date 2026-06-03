/**
 * Demo Finding Selection Tests
 *
 * Tests for the finding selection helper following priority:
 * live critical → live warning → historical real → clean fallback.
 */

import { describe, it, expect } from "vitest";
import {
  selectDemoFindings,
  selectHistoricalFindings,
  getCleanClusterFallback,
  containsForbiddenPhrase,
  validateFindings,
} from "../demoFindingSelection";
import type { DemoFinding, SeverityLevel } from "../../../components/demo-shell/DemoShellTypes";

describe("selectDemoFindings", () => {
  describe("Clean cluster fallback", () => {
    it("returns clean cluster when input has no findings", () => {
      const result = selectDemoFindings({});

      expect(result.findings).toHaveLength(0);
      expect(result.source).toBe("none");
      expect(result.cleanCluster).toBe(true);
      expect(result.explanation).toContain("No critical or warning findings");
    });

    it("returns clean cluster when incident report is healthy", () => {
      const result = selectDemoFindings({
        incidentReport: {
          status: "healthy",
          resource: "default/nginx-pod",
        },
      });

      expect(result.findings).toHaveLength(0);
      expect(result.cleanCluster).toBe(true);
    });
  });

  describe("Live critical finding selection", () => {
    it("selects live critical finding from incident report", () => {
      const result = selectDemoFindings({
        incidentReport: {
          status: "critical",
          resource: "default/nginx-pod",
          findingType: "CrashLoopBackOff",
        },
      });

      expect(result.findings).toHaveLength(1);
      expect(result.findings[0].severity).toBe("critical");
      expect(result.findings[0].evidenceSource).toBe("live");
      expect(result.source).toBe("live");
    });

    it("selects live critical finding from degraded status", () => {
      const result = selectDemoFindings({
        incidentReport: {
          status: "degraded",
          resource: "kube-system/kube-proxy",
        },
      });

      expect(result.findings).toHaveLength(1);
      expect(result.findings[0].severity).toBe("critical");
    });

    it("maps CrashLoopBackOff to critical severity", () => {
      const result = selectDemoFindings({
        incidentReport: {
          findingType: "CrashLoopBackOff",
          resource: "production/api-pod",
        },
      });

      expect(result.findings[0].severity).toBe("critical");
    });

    it("maps ImagePullBackOff to critical severity", () => {
      const result = selectDemoFindings({
        incidentReport: {
          findingType: "ImagePullBackOff",
          resource: "staging/web-pod",
        },
      });

      expect(result.findings[0].severity).toBe("critical");
    });

    it("maps OOMKilled to critical severity", () => {
      const result = selectDemoFindings({
        incidentReport: {
          findingType: "OOMKilled",
          resource: "data/worker-pod",
        },
      });

      expect(result.findings[0].severity).toBe("critical");
    });

    it("maps FailedScheduling to critical severity", () => {
      const result = selectDemoFindings({
        incidentReport: {
          findingType: "FailedScheduling",
          resource: "app/job-pod",
        },
      });

      expect(result.findings[0].severity).toBe("critical");
    });
  });

  describe("Live warning finding selection", () => {
    it("selects live warning finding from incident report", () => {
      const result = selectDemoFindings({
        incidentReport: {
          status: "warning",
          resource: "monitoring/prometheus-pod",
        },
      });

      expect(result.findings).toHaveLength(1);
      expect(result.findings[0].severity).toBe("warning");
    });

    it("selects from operator worklist warning items", () => {
      const result = selectDemoFindings({
        operatorWorklist: [
          {
            severity: "warning",
            resource: "logging/elasticsearch-pod",
            status: "Pending",
            message: "Pod pending scheduling",
          },
        ],
      });

      expect(result.findings).toHaveLength(1);
      expect(result.findings[0].severity).toBe("warning");
    });
  });

  describe("Priority order", () => {
    it("prefers critical over warning in same input", () => {
      const result = selectDemoFindings({
        operatorWorklist: [
          {
            severity: "warning",
            resource: "app/warning-pod",
            message: "Warning state",
          },
          {
            severity: "critical",
            resource: "app/critical-pod",
            message: "Critical state",
          },
        ],
      });

      // Should be sorted by severity priority
      expect(result.findings[0].severity).toBe("critical");
      expect(result.findings[1].severity).toBe("warning");
    });
  });

  describe("Stale evidence handling", () => {
    it("marks findings as stale when freshness is stale", () => {
      const result = selectDemoFindings({
        incidentReport: {
          status: "critical",
          resource: "default/pod",
          findingType: "CrashLoopBackOff",
        },
        freshness: {
          isStale: true,
        },
      });

      expect(result.findings[0].evidenceSource).toBe("stale");
      expect(result.source).toBe("stale");
    });

    it("marks findings as stale when freshness age exceeds threshold", () => {
      const result = selectDemoFindings({
        incidentReport: {
          status: "critical",
          resource: "default/pod",
        },
        freshness: {
          age: 600, // 10 minutes, over 5 minute threshold
        },
      });

      expect(result.findings[0].evidenceSource).toBe("stale");
    });

    it("marks findings as live when freshness is fresh", () => {
      const result = selectDemoFindings({
        incidentReport: {
          status: "warning",
          resource: "default/pod",
        },
        freshness: {
          age: 60, // 1 minute, under threshold
        },
      });

      expect(result.findings[0].evidenceSource).toBe("live");
    });
  });

  describe("No fabricated findings", () => {
    it("does not create findings when input is empty", () => {
      const result = selectDemoFindings({});

      expect(result.findings).toHaveLength(0);
    });

    it("does not create findings from healthy status only", () => {
      const result = selectDemoFindings({
        incidentReport: {
          status: "healthy",
        },
      });

      expect(result.findings).toHaveLength(0);
      expect(result.cleanCluster).toBe(true);
    });
  });

  describe("Evidence source labels", () => {
    it("returns 'live' source for fresh findings", () => {
      const result = selectDemoFindings({
        incidentReport: {
          status: "critical",
          resource: "default/pod",
        },
      });

      expect(result.source).toBe("live");
    });

    it("returns 'stale' source for stale findings", () => {
      const result = selectDemoFindings({
        incidentReport: {
          status: "warning",
          resource: "default/pod",
        },
        freshness: {
          isStale: true,
        },
      });

      expect(result.source).toBe("stale");
    });

    it("returns 'none' source for no findings", () => {
      const result = selectDemoFindings({});

      expect(result.source).toBe("none");
    });
  });
});

describe("selectHistoricalFindings", () => {
  const mockHistoricalFindings: DemoFinding[] = [
    {
      id: "hist-1",
      title: "Critical: CrashLoopBackOff",
      severity: "critical",
      affectedResource: "default/nginx-pod",
      evidenceSource: "live",
      probableCause: "Container failing to start",
      diagnosticEvidence: "Container restart count exceeded",
      recommendedAction: "Review container configuration",
      safetyMode: "preview-only",
    },
    {
      id: "hist-2",
      title: "Warning: Pending",
      severity: "warning",
      affectedResource: "monitoring/prometheus-pod",
      evidenceSource: "live",
      probableCause: "Pod pending scheduling",
      diagnosticEvidence: "Insufficient cluster resources",
      recommendedAction: "Check resource quotas",
      safetyMode: "preview-only",
    },
  ];

  it("returns historical findings with 'historical' source label", () => {
    const result = selectHistoricalFindings(mockHistoricalFindings);

    expect(result.source).toBe("historical");
    expect(result.findings).toHaveLength(2);
  });

  it("filters to critical and warning only", () => {
    const withInfo: DemoFinding[] = [
      ...mockHistoricalFindings,
      {
        id: "info-1",
        title: "Info: Clean scan",
        severity: "info",
        affectedResource: "default/pod",
        evidenceSource: "live",
        probableCause: "No issues",
        diagnosticEvidence: "All systems operational",
        recommendedAction: "Continue monitoring",
        safetyMode: "read-only",
      },
    ];

    const result = selectHistoricalFindings(withInfo);

    expect(result.findings).toHaveLength(2);
    expect(result.findings.every((f) => f.severity === "critical" || f.severity === "warning")).toBe(true);
  });

  it("sorts findings by severity priority", () => {
    const result = selectHistoricalFindings(mockHistoricalFindings);

    expect(result.findings[0].severity).toBe("critical");
    expect(result.findings[1].severity).toBe("warning");
  });

  it("returns empty result for empty historical findings", () => {
    const result = selectHistoricalFindings([]);

    expect(result.findings).toHaveLength(0);
    expect(result.source).toBe("none");
    expect(result.cleanCluster).toBe(true);
  });
});

describe("getCleanClusterFallback", () => {
  it("returns clean cluster result with no findings", () => {
    const result = getCleanClusterFallback();

    expect(result.findings).toHaveLength(0);
    expect(result.source).toBe("none");
    expect(result.cleanCluster).toBe(true);
  });

  it("includes explanation about no critical issues", () => {
    const result = getCleanClusterFallback();

    expect(result.explanation).toContain("No critical issues");
  });

  it("mentions historical evidence when available", () => {
    const result = getCleanClusterFallback({
      hasHistoricalEvidence: true,
    });

    expect(result.explanation).toContain("Historical evidence available");
  });

  it("says healthy when no historical evidence", () => {
    const result = getCleanClusterFallback({
      hasHistoricalEvidence: false,
    });

    expect(result.explanation).toContain("Cluster appears healthy");
  });
});

describe("containsForbiddenPhrase", () => {
  it("detects 'self-healing'", () => {
    expect(containsForbiddenPhrase("Cluster has self-healing capabilities")).toBe(true);
  });

  it("detects 'guaranteed root cause'", () => {
    expect(containsForbiddenPhrase("Guaranteed root cause analysis")).toBe(true);
  });

  it("detects 'automatic production fix'", () => {
    expect(containsForbiddenPhrase("Automatic production fix will be applied")).toBe(true);
  });

  it("detects 'fixes any Kubernetes issue'", () => {
    expect(containsForbiddenPhrase("Fixes any Kubernetes issue automatically")).toBe(true);
  });

  it("detects 'fully autonomous'", () => {
    expect(containsForbiddenPhrase("Fully autonomous remediation")).toBe(true);
  });

  it("is case-insensitive", () => {
    expect(containsForbiddenPhrase("SELF-HEALING")).toBe(true);
    expect(containsForbiddenPhrase("Guaranteed Root Cause")).toBe(true);
  });

  it("returns false for safe content", () => {
    expect(containsForbiddenPhrase("Review diagnostic evidence")).toBe(false);
    expect(containsForbiddenPhrase("Recommended next check")).toBe(false);
    expect(containsForbiddenPhrase("Operator approval required")).toBe(false);
  });
});

describe("validateFindings", () => {
  it("returns true for safe findings", () => {
    const safeFindings: DemoFinding[] = [
      {
        id: "1",
        title: "Critical: CrashLoopBackOff",
        severity: "critical",
        affectedResource: "default/pod",
        evidenceSource: "live",
        probableCause: "Container failing to start",
        diagnosticEvidence: "Multiple restart attempts",
        recommendedAction: "Review diagnostic evidence and run recommended check",
        safetyMode: "preview-only",
      },
    ];

    expect(validateFindings(safeFindings)).toBe(true);
  });

  it("returns false for findings with forbidden phrases", () => {
    const unsafeFindings: DemoFinding[] = [
      {
        id: "1",
        title: "Critical: Self-healing activated",
        severity: "critical",
        affectedResource: "default/pod",
        evidenceSource: "live",
        probableCause: "Container failing",
        diagnosticEvidence: "Multiple restarts",
        recommendedAction: "Review evidence",
        safetyMode: "preview-only",
      },
    ];

    expect(validateFindings(unsafeFindings)).toBe(false);
  });

  it("returns false for findings with forbidden recommended actions", () => {
    const unsafeFindings: DemoFinding[] = [
      {
        id: "1",
        title: "Critical: CrashLoopBackOff",
        severity: "critical",
        affectedResource: "default/pod",
        evidenceSource: "live",
        probableCause: "Container failing",
        diagnosticEvidence: "Multiple restarts",
        recommendedAction: "Automatic production fix will be applied",
        safetyMode: "preview-only",
      },
    ];

    expect(validateFindings(unsafeFindings)).toBe(false);
  });
});

describe("No fake incidents", () => {
  it("does not use fake/sample incident language in finding titles", () => {
    // Test that real finding types are used
    const result = selectDemoFindings({
      incidentReport: {
        findingType: "CrashLoopBackOff",
        resource: "default/production-pod",
      },
    });

    const title = result.findings[0]?.title ?? "";
    expect(title).not.toMatch(/demo/i);
    expect(title).not.toMatch(/fake/i);
    expect(title).not.toMatch(/sample/i);
    expect(title).not.toMatch(/simulated/i);
  });

  it("does not present fabricated findings as real", () => {
    // Empty input should not produce fabricated findings
    const result = selectDemoFindings({});

    expect(result.findings).toHaveLength(0);
    expect(result.cleanCluster).toBe(true);
  });

  it("preserves provenance labels for historical evidence", () => {
    const historicalResult = selectHistoricalFindings([
      {
        id: "hist-1",
        title: "Critical: FailedScheduling",
        severity: "critical",
        affectedResource: "app/pod",
        evidenceSource: "live",
        probableCause: "Insufficient resources",
        diagnosticEvidence: "Node capacity exceeded",
        recommendedAction: "Review resource requests",
        safetyMode: "preview-only",
      },
    ]);

    expect(historicalResult.source).toBe("historical");
    expect(historicalResult.findings[0].evidenceSource).toBe("historical");
  });
});