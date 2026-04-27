/**
 * llm-telemetry-card.test.tsx
 *
 * Tests for LLM Telemetry card components:
 * - TelemetryStatsRow: Calls/OK/Failed stat chips with label/value separation
 * - TelemetryLatencyRow: P50/P95/P99 latency cells with compact formatting
 * - TelemetryProvidersRow: Provider chips that wrap cleanly
 * - formatLatencyMs: Compact latency formatting utility
 *
 * Phase 1 - Epic: Polish LLM Telemetry UX
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import {
  TelemetryStatsRow,
  TelemetryLatencyRow,
  TelemetryProvidersRow,
  formatLatencyMs,
} from "../components/run-summary/LlmTelemetryCard";
import type { LLMProviderBreakdown } from "../types";

// ============================================================================
// formatLatencyMs tests
// ============================================================================

describe("formatLatencyMs", () => {
  test("returns '—' for null values", () => {
    expect(formatLatencyMs(null)).toBe("—");
  });

  test("returns '—' for undefined values", () => {
    expect(formatLatencyMs(undefined)).toBe("—");
  });

  test("returns '—' for non-finite values", () => {
    expect(formatLatencyMs(Infinity)).toBe("—");
    expect(formatLatencyMs(-Infinity)).toBe("—");
    expect(formatLatencyMs(NaN)).toBe("—");
  });

  test("displays milliseconds for values < 1000ms", () => {
    expect(formatLatencyMs(100)).toBe("100ms");
    expect(formatLatencyMs(153)).toBe("153ms");
    expect(formatLatencyMs(500)).toBe("500ms");
    expect(formatLatencyMs(999)).toBe("999ms");
  });

  test("displays seconds for values >= 1000ms with 1 decimal place", () => {
    expect(formatLatencyMs(1000)).toBe("1.0s");
    expect(formatLatencyMs(1530)).toBe("1.5s");
    expect(formatLatencyMs(15302)).toBe("15.3s");
    expect(formatLatencyMs(40719)).toBe("40.7s");
    expect(formatLatencyMs(60000)).toBe("60.0s");
  });

  test("handles exact boundary cases", () => {
    expect(formatLatencyMs(999)).toBe("999ms");
    expect(formatLatencyMs(1000)).toBe("1.0s");
  });
});

// ============================================================================
// TelemetryStatsRow tests
// ============================================================================

describe("TelemetryStatsRow", () => {
  test("renders Calls, OK, and Failed chips", () => {
    render(
      <TelemetryStatsRow
        totalCalls={5}
        successfulCalls={4}
        failedCalls={1}
      />
    );

    // All three chips should be present
    expect(screen.getByText("Calls")).toBeInTheDocument();
    expect(screen.getByText("OK")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  test("renders correct values in chips", () => {
    render(
      <TelemetryStatsRow
        totalCalls={5}
        successfulCalls={4}
        failedCalls={1}
      />
    );

    // Values should be in separate elements from labels
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  test("labels and values are separated (not concatenated)", () => {
    render(
      <TelemetryStatsRow
        totalCalls={5}
        successfulCalls={4}
        failedCalls={1}
      />
    );

    // Labels should NOT contain the numeric values
    const callsLabel = screen.getByText("Calls");
    expect(callsLabel.textContent).toBe("Calls");
    expect(callsLabel.textContent).not.toContain("5");

    const okLabel = screen.getByText("OK");
    expect(okLabel.textContent).toBe("OK");
    expect(okLabel.textContent).not.toContain("4");

    const failedLabel = screen.getByText("Failed");
    expect(failedLabel.textContent).toBe("Failed");
    expect(failedLabel.textContent).not.toContain("1");

    // Values should be in separate span elements
    const statsRow = screen.getByTestId("llm-telemetry-stats");
    const statChipLabels = statsRow.querySelectorAll(".stat-chip-label");
    const statChipValues = statsRow.querySelectorAll(".stat-chip-value");

    expect(statChipLabels.length).toBe(3);
    expect(statChipValues.length).toBe(3);
  });

  test("Failed chip has danger styling when > 0", () => {
    render(
      <TelemetryStatsRow
        totalCalls={5}
        successfulCalls={4}
        failedCalls={1}
      />
    );

    // Find the Failed chip and verify it has danger class
    const failedChip = screen
      .getByTestId("llm-telemetry-stats")
      .querySelector(".stat-chip--danger");
    expect(failedChip).toBeInTheDocument();
    expect(failedChip?.textContent).toContain("Failed");
  });

  test("Failed chip has neutral styling when = 0", () => {
    render(
      <TelemetryStatsRow
        totalCalls={5}
        successfulCalls={5}
        failedCalls={0}
      />
    );

    // Find the Failed chip and verify it has neutral class
    const failedChip = screen
      .getByTestId("llm-telemetry-stats")
      .querySelector(".stat-chip--neutral");
    expect(failedChip).toBeInTheDocument();
    expect(failedChip?.textContent).toContain("Failed");
  });
});

// ============================================================================
// TelemetryLatencyRow tests
// ============================================================================

describe("TelemetryLatencyRow", () => {
  test("renders P50, P95, and P99 cells", () => {
    render(
      <TelemetryLatencyRow
        p50LatencyMs={15302}
        p95LatencyMs={40719}
        p99LatencyMs={40719}
      />
    );

    expect(screen.getByText("P50")).toBeInTheDocument();
    expect(screen.getByText("P95")).toBeInTheDocument();
    expect(screen.getByText("P99")).toBeInTheDocument();
  });

  test("renders compact latency values (seconds format for >= 1000ms)", () => {
    render(
      <TelemetryLatencyRow
        p50LatencyMs={15302}
        p95LatencyMs={40719}
        p99LatencyMs={40719}
      />
    );

    // Values should be in seconds format
    expect(screen.getByText("15.3s")).toBeInTheDocument();
    // P95 and P99 both have 40.7s, so use getAllByText
    const p95p99Elements = screen.getAllByText("40.7s");
    expect(p95p99Elements).toHaveLength(2);
  });

  test("renders milliseconds for values < 1000ms", () => {
    render(
      <TelemetryLatencyRow
        p50LatencyMs={150}
        p95LatencyMs={300}
        p99LatencyMs={500}
      />
    );

    expect(screen.getByText("150ms")).toBeInTheDocument();
    expect(screen.getByText("300ms")).toBeInTheDocument();
    expect(screen.getByText("500ms")).toBeInTheDocument();
  });

  test("renders '—' for null latency values", () => {
    render(
      <TelemetryLatencyRow
        p50LatencyMs={null}
        p95LatencyMs={null}
        p99LatencyMs={null}
      />
    );

    // Should show three dash placeholders
    const dashElements = screen.getAllByText("—");
    expect(dashElements).toHaveLength(3);
  });

  test("labels and values are separated (not concatenated)", () => {
    render(
      <TelemetryLatencyRow
        p50LatencyMs={15302}
        p95LatencyMs={40719}
        p99LatencyMs={40719}
      />
    );

    // Labels should be separate from values
    const latencyRow = document.querySelector(".telemetry-latency-row");
    expect(latencyRow).toBeInTheDocument();

    const latencyLabels = latencyRow?.querySelectorAll(".latency-label");
    const latencyValues = latencyRow?.querySelectorAll(".latency-value");

    expect(latencyLabels?.length).toBe(3);
    expect(latencyValues?.length).toBe(3);

    // Labels should not contain the formatted values
    latencyLabels?.forEach((label) => {
      expect(label.textContent).not.toContain("s");
      expect(label.textContent).not.toContain("ms");
    });
  });
});

// ============================================================================
// TelemetryProvidersRow tests
// ============================================================================

describe("TelemetryProvidersRow", () => {
  const sampleProviders: LLMProviderBreakdown[] = [
    { provider: "k8sgpt", calls: 2, failedCalls: 0 },
    { provider: "default", calls: 3, failedCalls: 1 },
  ];

  test("renders provider chips for each provider", () => {
    render(<TelemetryProvidersRow providers={sampleProviders} />);

    expect(screen.getByText("k8sgpt")).toBeInTheDocument();
    expect(screen.getByText("default")).toBeInTheDocument();
  });

  test("renders call counts for each provider", () => {
    render(<TelemetryProvidersRow providers={sampleProviders} />);

    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  test("shows failed count when > 0", () => {
    render(<TelemetryProvidersRow providers={sampleProviders} />);

    // Should show "(1 failed)" for provider with failures
    expect(screen.getByText("(1 failed)")).toBeInTheDocument();
  });

  test("does not show failed count when = 0", () => {
    render(<TelemetryProvidersRow providers={sampleProviders} />);

    // Should NOT show "(0 failed)" - only providers with failures
    expect(screen.queryByText("(0 failed)")).not.toBeInTheDocument();
  });

  test("renders long provider names without breaking layout", () => {
    const longProviderName = "next-check-planner";
    const longProvider: LLMProviderBreakdown[] = [
      { provider: longProviderName, calls: 10, failedCalls: 2 },
    ];

    render(<TelemetryProvidersRow providers={longProvider} />);

    // Long provider name should be rendered
    expect(screen.getByText(longProviderName)).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("(2 failed)")).toBeInTheDocument();

    // Provider chip should exist and allow word-break
    const providerChip = screen.getByTestId(`provider-chip-${longProviderName}`);
    expect(providerChip).toBeInTheDocument();
  });

  test("renders multiple providers with varied names", () => {
    const multipleProviders: LLMProviderBreakdown[] = [
      { provider: "short", calls: 1, failedCalls: 0 },
      { provider: "medium-name", calls: 5, failedCalls: 0 },
      { provider: "very-long-provider-name-here", calls: 3, failedCalls: 1 },
    ];

    render(<TelemetryProvidersRow providers={multipleProviders} />);

    expect(screen.getByText("short")).toBeInTheDocument();
    expect(screen.getByText("medium-name")).toBeInTheDocument();
    expect(screen.getByText("very-long-provider-name-here")).toBeInTheDocument();
  });

  test("has data-testid for each provider", () => {
    render(<TelemetryProvidersRow providers={sampleProviders} />);

    expect(screen.getByTestId("provider-chip-k8sgpt")).toBeInTheDocument();
    expect(screen.getByTestId("provider-chip-default")).toBeInTheDocument();
  });
});
