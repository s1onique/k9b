/**
 * Diagnostic pack review panel tests.
 *
 * Tests the rendering and behavior of the diagnostic pack review panel
 * including download links, error states, and skip states.
 *
 * Part of app.review-enrichment.test.tsx split for LLM-friendly file sizes.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App from "../App";

import {
  createFetchMock,
  createStorageMock,
  defaultPayloads,
  makeDiagnosticPackReview,
  sampleRun,
} from "./app.test-fixtures";

let setIntervalSpy: ReturnType<typeof vi.fn>;
let clearIntervalSpy: ReturnType<typeof vi.fn>;
let storageMock: ReturnType<typeof createStorageMock>;

beforeEach(() => {
  setIntervalSpy = vi.fn(() => 123);
  clearIntervalSpy = vi.fn();
  vi.stubGlobal("setInterval", setIntervalSpy);
  vi.stubGlobal("clearInterval", clearIntervalSpy);
  storageMock = createStorageMock();
  vi.stubGlobal("localStorage", storageMock);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Diagnostic pack review panel", () => {
  test("renders diagnostic pack review panel when data exists", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const heading = await screen.findByRole("heading", {
      name: /Diagnostic pack review/i,
    });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText(/Review detected ranking mismatches/i)).toBeInTheDocument();
    expect(screen.getByText(/Major disagreements · 2/i)).toBeInTheDocument();
    expect(screen.getByText(/Missing checks · 2/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Provider k8sgpt validated the review and provided metadata./i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Provider flagged suspected drift misprioritization/i)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /View diagnostic pack review artifact/i })
    ).toBeInTheDocument();
  });

  test("renders run diagnostic pack download link when run artifact is present", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const heading = await screen.findByRole("heading", {
      name: /Run diagnostic package/i,
    });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText(/Run 123 pack/i)).toBeInTheDocument();
    expect(screen.getByText(/Apr 6, 2026 12:01 UTC/i)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Download diagnostic pack/i })
    ).toHaveAttribute("href", expect.stringContaining("run-123-diagnostic-pack.zip"));
  });

  test("diagnostic pack review panel surfaces provider error details", async () => {
    const runWithError = {
      ...sampleRun,
      diagnosticPackReview: makeDiagnosticPackReview({
        providerErrorSummary: "Timeout contacting adapter",
        providerStatus: "error",
        majorDisagreements: ["Erroring provider"],
      }),
    };
    const payloads = { ...defaultPayloads, "/api/run": runWithError };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    const heading = await screen.findByRole("heading", {
      name: /Diagnostic pack review/i,
    });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText(/Timeout contacting adapter/i)).toBeInTheDocument();
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();
    expect(within(panel!).getByText(/^error$/i)).toHaveClass("status-pill");
    expect(screen.getByText(/Major disagreements · 1/i)).toBeInTheDocument();
  });

  test("diagnostic pack review panel handles skip-state with empty lists", async () => {
    const runWithSkip = {
      ...sampleRun,
      diagnosticPackReview: makeDiagnosticPackReview({
        majorDisagreements: [],
        missingChecks: [],
        rankingIssues: [],
        recommendedNextActions: [],
        providerStatus: null,
        providerSkipReason: "Provider intentionally skipped for this run",
        providerSummary: null,
        providerErrorSummary: null,
      }),
    };
    const payloads = { ...defaultPayloads, "/api/run": runWithSkip };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    const heading = await screen.findByRole("heading", {
      name: /Diagnostic pack review/i,
    });
    expect(heading).toBeInTheDocument();
    expect(screen.queryByText(/Provider unspecified/i)).toBeNull();
    expect(screen.getByText(/Provider intentionally skipped for this run/i)).toBeInTheDocument();
    expect(screen.queryByText(/Major disagreements ·/i)).toBeNull();
    expect(screen.queryByText(/Missing checks ·/i)).toBeNull();
    expect(screen.queryByText(/Recommended next actions/i)).toBeNull();
  });

  test("hides diagnostic pack review panel when the payload is missing", async () => {
    const payloads = {
      ...defaultPayloads,
      "/api/run": {
        ...sampleRun,
        diagnosticPackReview: null,
      },
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Provider advisory/i });
    expect(screen.queryByText(/Diagnostic pack review/i)).toBeNull();
    expect(screen.queryByText(/Major disagreements/i)).toBeNull();
  });
});
