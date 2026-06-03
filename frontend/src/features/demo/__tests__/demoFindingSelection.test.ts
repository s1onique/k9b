/**
 * Demo Finding Selection Tests
 *
 * Tests for the finding selection helper following priority:
 * live critical → live warning → historical real → clean fallback.
 */

import { describe, it, expect } from "vitest";
import {
  selectDemoFindings,
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
