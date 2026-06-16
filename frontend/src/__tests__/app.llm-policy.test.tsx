/**
 * LLM activity and policy tests.
 * 
 * Tests LLM policy block rendering, LLM activity panel,
 * and run stats display.
 * 
 * Split from app.test.tsx as part of the LLM-friendly file split.
 */

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App from "../App";

import {
  createFetchMock,
  createStorageMock,
  defaultPayloads,
  minsAgo,
  sampleRun,
  sampleRunsList,
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

describe("LLM policy block", () => {
  test("renders llm policy block with budget details", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await waitFor(() => {
      const panel = document.getElementById("llm-policy");
      expect(panel).toBeInTheDocument();
      expect(within(panel!).getByText(/Provider/i)).toBeInTheDocument();
    }, { timeout: 5000 });

    const panel = document.getElementById("llm-policy");
    expect(panel).not.toBeNull();

    const scoped = within(panel!);
    expect(scoped.getByRole("heading", { name: /LLM policy/i })).toBeInTheDocument();
    expect(scoped.getByText(/Provider/i)).toBeInTheDocument();
    expect(scoped.getByText(/Budget status/i)).toBeInTheDocument();
    expect(scoped.getByText(/Within budget/i)).toBeInTheDocument();
    expect(scoped.getByText(/Used this run/i)).toBeInTheDocument();
  });
});

describe("LLM activity panel", () => {
  test("renders llm activity panel and filters entries", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await waitFor(() => {
      const panel = document.getElementById("llm-activity");
      expect(panel).toBeInTheDocument();
      expect(within(panel!).getByText(/Retained entries: 19/i)).toBeInTheDocument();
    }, { timeout: 5000 });

    const panel = document.getElementById("llm-activity")!;
    const statusSelect = within(panel).getByLabelText(/Status/i);
    await act(async () => {
      await user.selectOptions(statusSelect, "failed");
    });
    expect(await within(panel).findByText(/timeout/i)).toBeInTheDocument();
  });
});

describe("Run stats and LLM telemetry", () => {
  test("renders compact run stats string", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const el = document.querySelector(".run-duration-summary");
      expect(el).not.toBeNull();
    });
    const durationSummary = document.querySelector(".run-duration-summary")!;
    expect(durationSummary!.textContent).toMatch(/Last 32s/);
    expect(durationSummary!.textContent).toMatch(/Runs 12/);
    expect(durationSummary!.textContent).toMatch(/P50 24s/);
    expect(durationSummary!.textContent).toMatch(/P95 48s/);
    expect(durationSummary!.textContent).toMatch(/P99/);

    expect(screen.getByText(/^Selected run$/i, { selector: ".hero-run-label" })).toBeInTheDocument();
    expect(screen.getByText(/^Latest$/i, { selector: ".run-badge" })).toBeInTheDocument();
    expect(screen.getAllByText(/ID run-123/i).length).toBeGreaterThan(0);
    expect(
      screen.getByText(/(Fresh|Aging|Stale)$/i, { selector: ".freshness-indicator__label" })
    ).toBeInTheDocument();
    expect(screen.getByText(/Collector collector:v1.2.0/i)).toBeInTheDocument();

    const summaryPanel = document.getElementById("run-detail");
    expect(summaryPanel).not.toBeNull();
    const summaryScoped = within(summaryPanel!);
    const telemetryTab = await summaryScoped.findByRole("tab", { name: /Telemetry/i });
    await act(async () => {
      telemetryTab.click();
    });
    expect(summaryScoped.getByText(/Run LLM calls:/i)).toBeInTheDocument();
    expect(summaryScoped.getByText(/Historical LLM calls:/i)).toBeInTheDocument();
    expect(
      summaryScoped.getByText(/Providers: k8sgpt 2 \(0 failed\) · default 1 \(1 failed\)/i)
    ).toBeInTheDocument();
    expect(summaryScoped.getByText(/Retained history stats/i)).toBeInTheDocument();
    expect(summaryScoped.getByText(/LLM telemetry/i)).toBeInTheDocument();
  });
});
