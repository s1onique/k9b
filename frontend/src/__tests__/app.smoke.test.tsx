/**
 * App smoke and bootstrap tests.
 * 
 * Tests App component rendering, initial load, cluster detail tabs,
 * and the "shows loading and surfaces API errors" test.
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
  sampleFleet,
  sampleClusterDetail,
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

describe("App smoke", () => {
  test("renders fleet overview data from the API payload", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    expect(screen.getByText(/Loading operator data/i)).toBeInTheDocument();
    await screen.findByRole("heading", { name: /Fleet overview/i });

    expect(
      screen.getByText(sampleFleet.topProblem.detail, { exact: false })
    ).toBeInTheDocument();
    expect(screen.getAllByText(sampleFleet.clusters[0].label).length).toBeGreaterThan(0);
    const triggerMatches = screen.getAllByText(sampleFleet.clusters[0].topTriggerReason!, {
      exact: false,
    });
    expect(triggerMatches.length).toBeGreaterThan(0);
  });

  test("switches cluster detail tabs to reveal hypotheses and checks", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Cluster detail/i });
    const summaryToggle = await screen.findByText(/Tap to expand findings/i);
    await act(async () => {
      await user.click(summaryToggle);
    });
    const findingMatches = await screen.findAllByText(sampleClusterDetail.findings[0].label!, {
      exact: false,
    });
    expect(findingMatches.length).toBeGreaterThan(0);

    const tabList = screen.getByRole("tablist", { name: /Cluster detail tabs/i });
    await act(async () => {
      await user.click(within(tabList).getByRole("button", { name: /Hypotheses/i }));
    });
    expect(
      await screen.findByText(sampleClusterDetail.hypotheses[0].description)
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(within(tabList).getByRole("button", { name: /Next checks/i }));
    });
    expect(
      await screen.findByText(sampleClusterDetail.nextChecks[0].description)
    ).toBeInTheDocument();
  });

  test("cluster detail summary highlights health cues and recommended artifacts", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Cluster detail/i });
    expect(await screen.findByText(/Control plane saturation/i)).toBeInTheDocument();
    expect(await screen.findByText(/gRPC queues are growing/i)).toBeInTheDocument();
    expect(screen.getAllByText(/High CPU/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Recommended artifacts/i)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /diagnostic bundle/i }).length).toBeGreaterThan(0);
  });

  test("shows loading and surfaces API errors", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("network boom"))));
    render(<App />);

    expect(screen.getByText(/Loading operator data/i)).toBeInTheDocument();
    // Error handling now produces descriptive messages for API failures
    await screen.findByText(/Expected JSON|text\/html|SPA index|network boom/i);
  });
});
