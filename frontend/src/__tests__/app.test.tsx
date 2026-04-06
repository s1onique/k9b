import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App from "../App";
import {
  sampleClusterDetail,
  sampleFleet,
  sampleNotifications,
  sampleProposals,
  sampleRun,
} from "./fixtures";

const defaultPayloads = {
  "/api/run": sampleRun,
  "/api/fleet": sampleFleet,
  "/api/proposals": sampleProposals,
  "/api/notifications": sampleNotifications,
  "/api/cluster-detail": sampleClusterDetail,
};

const createFetchMock = (payloads: Record<string, unknown>) =>
  vi.fn((input: RequestInfo) => {
    const url = typeof input === "string" ? input : input.url;
    const payload = payloads[url];
    if (!payload) {
      return Promise.reject(new Error(`Unexpected fetch ${url}`));
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      statusText: "OK",
      json: () => Promise.resolve(payload),
    });
  });

beforeEach(() => {
  vi.stubGlobal("setInterval", () => 0);
  vi.stubGlobal("clearInterval", () => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("App", () => {
  test("renders fleet overview data from the API payload", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    expect(screen.getByText(/Loading operator data/i)).toBeInTheDocument();
    await screen.findByRole("heading", { name: /Fleet overview/i });

    expect(
      screen.getByText(sampleFleet.topProblem.detail, { exact: false })
    ).toBeInTheDocument();
    expect(screen.getAllByText(sampleFleet.clusters[0].label).length).toBeGreaterThan(0);
    expect(
      screen.getByText(sampleFleet.clusters[0].topTriggerReason!, { exact: false })
    ).toBeInTheDocument();
  });

  test("switches cluster detail tabs to reveal hypotheses and checks", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Cluster detail/i });
    const findingMatches = await screen.findAllByText(sampleClusterDetail.findings[0].label!, {
      exact: false,
    });
    expect(findingMatches.length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /Hypotheses/i }));
    expect(screen.getByText(sampleClusterDetail.hypotheses[0].description)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Next checks/i }));
    expect(screen.getByText(sampleClusterDetail.nextChecks[0].description)).toBeInTheDocument();
  });

  test("shows loading and surfaces API errors", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("network boom"))));
    render(<App />);

    expect(screen.getByText(/Loading operator data/i)).toBeInTheDocument();
    await screen.findByText(/network boom/i);
  });
});
