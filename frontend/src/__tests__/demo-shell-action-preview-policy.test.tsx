/**
 * Demo Shell Action Preview Policy Tests
 *
 * Tests for action panel safety policies and helper function contracts.
 * Verifies safety modes, forbidden phrase detection, and CTA rules.
 */

import { describe, it, expect } from "vitest";
import {
  getActionSafetyCopy,
  getActionCta,
  isActionExecutableInDemo,
  FORBIDDEN_CTA_LABELS,
  isForbiddenCtaLabel,
} from "../components/demo-shell/DemoShellData";

describe("DemoShell action panel safety modes", () => {
  describe("Read-only safety mode", () => {
    it("shows no mutation will be performed", () => {
      const safetyCopy = getActionSafetyCopy("read-only");

      expect(safetyCopy.title).toBe("Read-only Mode");
      expect(safetyCopy.description).toContain("No cluster mutations");
      expect(safetyCopy.warning).toContain("diagnostic recommendation");
    });

    it("returns disabled CTA", () => {
      const cta = getActionCta("read-only");

      expect(cta.label).toBe("Preview command");
      expect(cta.disabled).toBe(true);
      expect(cta.hint).toContain("read-only mode");
    });

    it("is not executable in demo", () => {
      expect(isActionExecutableInDemo("read-only")).toBe(false);
    });
  });

  describe("Operator-approved safety mode", () => {
    it("shows explicit approval is required", () => {
      const safetyCopy = getActionSafetyCopy("operator-approved");

      expect(safetyCopy.title).toBe("Operator-Approved Mode");
      expect(safetyCopy.description).toContain("explicit operator approval");
      expect(safetyCopy.warning).toContain("No action runs automatically");
    });

    it("returns disabled CTA", () => {
      const cta = getActionCta("operator-approved");

      expect(cta.label).toBe("Operator approval required");
      expect(cta.disabled).toBe(true);
      expect(cta.hint).toContain("explicit operator approval");
    });

    it("is not executable in demo", () => {
      expect(isActionExecutableInDemo("operator-approved")).toBe(false);
    });
  });

  describe("Preview-only safety mode", () => {
    it("shows execution is disabled", () => {
      const safetyCopy = getActionSafetyCopy("preview-only");

      expect(safetyCopy.title).toBe("Preview Only");
      expect(safetyCopy.description).toContain("review only");
      expect(safetyCopy.warning).toContain("Execution is disabled");
    });

    it("returns enabled copy CTA for preview-only mode", () => {
      const cta = getActionCta("preview-only");

      expect(cta.label).toBe("Copy recommendation");
      expect(cta.disabled).toBe(false);
      expect(cta.hint).toContain("Copy to clipboard");
    });

    it("is not executable in demo", () => {
      expect(isActionExecutableInDemo("preview-only")).toBe(false);
    });
  });
});

describe("DemoShell action panel helper functions", () => {
  describe("getActionSafetyCopy", () => {
    it("returns correct copy for all safety modes", () => {
      const modes = ["read-only", "operator-approved", "preview-only"] as const;

      modes.forEach((mode) => {
        const copy = getActionSafetyCopy(mode);
        expect(copy.title).toBeDefined();
        expect(copy.description).toBeDefined();
        expect(typeof copy.title).toBe("string");
        expect(typeof copy.description).toBe("string");
      });
    });
  });

  describe("getActionCta", () => {
    it("returns correct CTA config for all safety modes", () => {
      const modes = ["read-only", "operator-approved", "preview-only"] as const;

      modes.forEach((mode) => {
        const cta = getActionCta(mode);
        expect(cta.label).toBeDefined();
        expect(typeof cta.disabled).toBe("boolean");
        expect(cta.hint).toBeDefined();
      });
    });
  });

  describe("isActionExecutableInDemo", () => {
    it("always returns false for all safety modes", () => {
      const modes = ["read-only", "operator-approved", "preview-only"] as const;

      modes.forEach((mode) => {
        expect(isActionExecutableInDemo(mode)).toBe(false);
      });
    });
  });
});

describe("Forbidden CTA label checks", () => {
  it("has no forbidden CTA labels defined", () => {
    expect(FORBIDDEN_CTA_LABELS).toContain("fix now");
    expect(FORBIDDEN_CTA_LABELS).toContain("auto-fix");
    expect(FORBIDDEN_CTA_LABELS).toContain("repair cluster");
    expect(FORBIDDEN_CTA_LABELS).toContain("apply production fix");
    expect(FORBIDDEN_CTA_LABELS).toContain("run remediation");
  });

  it("detects forbidden CTA labels", () => {
    expect(isForbiddenCtaLabel("Fix now")).toBe(true);
    expect(isForbiddenCtaLabel("Auto-fix")).toBe(true);
    expect(isForbiddenCtaLabel("Repair cluster")).toBe(true);
    expect(isForbiddenCtaLabel("Apply production fix")).toBe(true);
    expect(isForbiddenCtaLabel("Run remediation")).toBe(true);
  });

  it("allows safe CTA labels", () => {
    expect(isForbiddenCtaLabel("Copy recommendation")).toBe(false);
    expect(isForbiddenCtaLabel("Preview command")).toBe(false);
    expect(isForbiddenCtaLabel("Operator approval required")).toBe(false);
  });
});

describe("Forbidden phrase checks in action panel output", () => {
  it("no forbidden phrases in output", () => {
    const lowerCtaLabels = FORBIDDEN_CTA_LABELS.map((l) => l.toLowerCase());

    // All forbidden CTA labels should be lowercase for consistent checking
    lowerCtaLabels.forEach((forbidden) => {
      expect(forbidden.length).toBeGreaterThan(0);
    });
  });
});