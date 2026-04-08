import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App, { AUTOREFRESH_STORAGE_KEY } from "../App";
import type { NotificationEntry } from "../types";
import {
  sampleClusterDetail,
  sampleFleet,
  sampleNotifications,
  sampleProposals,
  sampleRun,
} from "./fixtures";

const createStorageMock = () => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => (key in store ? store[key] : null),
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
};

const defaultPayloads = {
  "/api/run": sampleRun,
  "/api/fleet": sampleFleet,
  "/api/proposals": sampleProposals,
  "/api/notifications": sampleNotifications,
  "/api/cluster-detail": sampleClusterDetail,
};

const NOTIFICATION_BASE_TIME = Date.UTC(2026, 3, 7, 0, 0, 0);

const buildNotificationEntry = (
  index: number,
  overrides: Partial<NotificationEntry> = {}
): NotificationEntry => {
  const defaultTimestamp = new Date(NOTIFICATION_BASE_TIME - index * 60000).toISOString();
  return {
    kind: overrides.kind ?? (index % 2 ? "Warning" : "Info"),
    summary: overrides.summary ?? `Notification ${index + 1}`,
    timestamp: overrides.timestamp ?? defaultTimestamp,
    runId: overrides.runId ?? `run-${(index % 3) + 1}`,
    clusterLabel: overrides.clusterLabel ?? `cluster-${(index % 2) + 1}`,
    context: overrides.context ?? "test-context",
    details: overrides.details ?? [{ label: "Pod", value: `pod-${index}` }],
    artifactPath: overrides.artifactPath ?? (index % 4 === 0 ? null : `/artifacts/n-${index}.json`),
  };
};

const buildNotificationList = (count: number) =>
  Array.from({ length: count }, (_, index) => buildNotificationEntry(index));

const createFetchMock = (payloads: Record<string, unknown>) =>
  vi.fn((input: RequestInfo) => {
    const url = typeof input === "string" ? input : input.url;
    const base = url.split("?")[0];
    const payload = payloads[url] ?? payloads[base];
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
    const summaryToggle = await screen.findByText(/Tap to expand findings/i);
    await act(async () => {
      await user.click(summaryToggle);
    });
    const findingMatches = await screen.findAllByText(sampleClusterDetail.findings[0].label!, {
      exact: false,
    });
    expect(findingMatches.length).toBeGreaterThan(0);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /Hypotheses/i }));
    });
    expect(
      await screen.findByText(sampleClusterDetail.hypotheses[0].description)
    ).toBeInTheDocument();

    await act(async () => {
      await user.click(screen.getByRole("button", { name: /Next checks/i }));
    });
    expect(
      await screen.findByText(sampleClusterDetail.nextChecks[0].description)
    ).toBeInTheDocument();
  });

  test("renders compact run stats string", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });
    expect(
      screen.getByText("Last 32s · Runs 12 · P50 24s · P95 48s · P99 1m 4s")
    ).toBeInTheDocument();
    expect(screen.getByText(/Run LLM calls:/i)).toBeInTheDocument();
    expect(screen.getByText(/Historical LLM calls:/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Providers: k8sgpt 2 \(0 failed\) · default 1 \(1 failed\)/i)
    ).toBeInTheDocument();
  });

  test("renders llm policy block with budget details", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    const heading = await screen.findByRole("heading", { name: /LLM policy/i });
    expect(heading).toBeInTheDocument();
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();
    const scoped = within(panel!);
    expect(scoped.getByText(/Provider/i)).toBeInTheDocument();
    expect(scoped.getByText(/Budget status/i)).toBeInTheDocument();
    expect(scoped.getByText(/Within budget/i)).toBeInTheDocument();
    expect(scoped.getByText(/Used this run/i)).toBeInTheDocument();
  });

  test("renders review enrichment panel status message", async () => {
    const pendingRun = {
      ...sampleRun,
      reviewEnrichment: undefined,
      reviewEnrichmentStatus: undefined,
    };
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        ...defaultPayloads,
        "/api/run": pendingRun,
      })
    );
    render(<App />);

    const heading = await screen.findByRole("heading", {
      name: /Provider-assisted advisory/i,
    });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText(/Provider-assisted advisory/i)).toBeInTheDocument();
    expect(
      await screen.findByText(/Provider-assisted review enrichment is not configured for this run/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Provider unspecified/i)).toBeInTheDocument();
  });

  test("shows review enrichment status when enrichment is disabled", async () => {
    const disabledRun = {
      ...sampleRun,
      reviewEnrichment: undefined,
      reviewEnrichmentStatus: {
        status: "policy-disabled",
        reason: "Review enrichment is disabled in the current configuration.",
        provider: null,
        policyEnabled: false,
        providerConfigured: false,
        adapterAvailable: null,
        runEnabled: false,
        runProvider: null,
      },
    };
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        ...defaultPayloads,
        "/api/run": disabledRun,
      })
    );
    render(<App />);

    const heading = await screen.findByRole("heading", {
      name: /Provider-assisted advisory/i,
    });
    expect(heading).toBeInTheDocument();
    expect(
      screen.getByText(/Review enrichment is disabled in the current configuration/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Provider unspecified/i)).toBeInTheDocument();
  });

  test("renders awaiting-next-run status when run metadata lags", async () => {
    const awaitingRun = {
      ...sampleRun,
      reviewEnrichment: undefined,
      reviewEnrichmentStatus: {
        status: "awaiting-next-run",
        reason: "Awaiting a run that has enrichment enabled.",
        provider: "k8sgpt",
        policyEnabled: true,
        providerConfigured: true,
        adapterAvailable: true,
        runEnabled: false,
        runProvider: "old-provider",
      },
    };
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        ...defaultPayloads,
        "/api/run": awaitingRun,
      })
    );
    render(<App />);

    await screen.findByRole("heading", {
      name: /Provider-assisted advisory/i,
    });
    expect(
      screen.getByText(/Awaiting a run that has enrichment enabled./i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Provider k8sgpt/i)).toBeInTheDocument();
    expect(screen.getByText(/Run configuration disabled review enrichment/i)).toBeInTheDocument();
  });

  test("shows provider name when run config enabled review enrichment", async () => {
    const providerRun = {
      ...sampleRun,
      reviewEnrichment: undefined,
      reviewEnrichmentStatus: {
        status: "not-attempted",
        reason: "Review enrichment has not yet run for this run.",
        provider: null,
        policyEnabled: true,
        providerConfigured: true,
        adapterAvailable: true,
        runEnabled: true,
        runProvider: "llamacpp",
      },
    };
    vi.stubGlobal(
      "fetch",
      createFetchMock({
        ...defaultPayloads,
        "/api/run": providerRun,
      })
    );
    render(<App />);

    await screen.findByRole("heading", {
      name: /Provider-assisted advisory/i,
    });
    expect(screen.getByText(/Provider llamacpp/i)).toBeInTheDocument();
    expect(screen.getByText(/Run configuration enabled \(llamacpp\)/i)).toBeInTheDocument();
  });

  test("renders review enrichment details when enrichment data exists", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", {
      name: /Provider-assisted advisory/i,
    });
    expect(screen.getByText(/Review enrichment reshaped the triage order/i)).toBeInTheDocument();
    expect(screen.getByText(/Provider k8sgpt/i)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /View enrichment artifact/i })
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Provider-assisted review enrichment is not configured/i)
    ).toBeNull();
    expect(screen.queryByText(/Provider unspecified/i)).toBeNull();
  });

  test("renders provider execution panel", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Provider-assisted advisory/i });
    const executionHeading = await screen.findByText(/Provider execution/i);
    const executionPanel = executionHeading.closest("section");
    const scoped = within(executionPanel!);
    expect(scoped.getByText(/Provider execution/i)).toBeInTheDocument();
    expect(scoped.getByText(/Auto drilldown/i)).toBeInTheDocument();
    expect(scoped.getByText(/eligible 2/i)).toBeInTheDocument();
    const attemptedMatches = scoped.getAllByText(/attempted 1/i);
    expect(attemptedMatches.length).toBeGreaterThanOrEqual(1);
    const reviewMatches = scoped.getAllByText(/Review enrichment/i);
    expect(reviewMatches[0]).toBeInTheDocument();
  });

  test("renders llm activity panel and filters entries", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    const panelHeading = await screen.findByRole("heading", { name: /LLM activity/i });
    const notificationMatches = await screen.findAllByText(
      sampleClusterDetail.relatedNotifications[0].summary
    );
    expect(notificationMatches.length).toBeGreaterThan(0);
    expect(screen.getByText(/Retained entries: 19/i)).toBeInTheDocument();
    const panelSection = panelHeading.closest("section");
    expect(panelSection).not.toBeNull();
    const statusSelect = within(panelSection!).getByLabelText(/Status/i);
    await act(async () => {
      await user.selectOptions(statusSelect, "failed");
    });
    expect(await within(panelSection!).findByText(/timeout/i)).toBeInTheDocument();
  });

  test("renders notification history table and pagination summary", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);
    const heading = await screen.findByRole("heading", { name: /Notification history/i });
    expect(heading).toBeInTheDocument();
    const table = screen.getByRole("table", { name: /Notification history table/i });
    expect(within(table).getByText(sampleNotifications.notifications[0].summary)).toBeInTheDocument();
    expect(within(table).getAllByTestId("notification-row")).toHaveLength(1);
    expect(screen.getByText(/Showing 1–1 of 1/i)).toBeInTheDocument();
  });

  test("sorts notifications newest first", async () => {
    const unsortedNotifications = [
      buildNotificationEntry(1, { summary: "Older", timestamp: "2026-04-06T11:00:00Z" }),
      buildNotificationEntry(0, { summary: "Newest", timestamp: "2026-04-06T12:00:00Z" }),
    ];
    const payloads = {
      ...defaultPayloads,
      "/api/notifications": { notifications: unsortedNotifications },
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);
    const table = await screen.findByRole("table", { name: /Notification history table/i });
    const rows = within(table).getAllByTestId("notification-row");
    expect(within(rows[0]).getByText("Newest")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Older")).toBeInTheDocument();
  });

  test("paginates notification history after 50 rows", async () => {
    const manyNotifications = buildNotificationList(60);
    const payloads = {
      ...defaultPayloads,
      "/api/notifications": { notifications: manyNotifications },
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);
    await screen.findByRole("heading", { name: /Notification history/i });
    const rows = await screen.findAllByTestId("notification-row");
    expect(rows).toHaveLength(50);
    expect(screen.getByText(/Showing 1–50 of 60/i)).toBeInTheDocument();
  });

  test("pagination controls advance pages", async () => {
    const manyNotifications = buildNotificationList(60);
    const payloads = {
      ...defaultPayloads,
      "/api/notifications": { notifications: manyNotifications },
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: /Notification history/i });
    const nextButton = screen.getByRole("button", { name: /Next notifications page/i });
    await act(async () => {
      await user.click(nextButton);
    });
    expect(screen.getByText(/Page 2 of 2/i)).toBeInTheDocument();
    expect(screen.getByText(/Showing 51–60 of 60/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Previous/i })).not.toBeDisabled();
    expect(nextButton).toBeDisabled();
  });

  test("filters notification history table by kind, cluster, and search", async () => {
    const customNotifications = [
      buildNotificationEntry(0, {
        kind: "Warning",
        summary: "CPU spike on alpha",
        runId: "run-alpha",
        clusterLabel: "cluster-alpha",
        details: [{ label: "Confidence", value: "High" }],
      }),
      buildNotificationEntry(1, {
        kind: "Info",
        summary: "Routine health report",
        runId: "run-beta",
        clusterLabel: "cluster-beta",
      }),
      buildNotificationEntry(2, {
        kind: "Warning",
        summary: "Memory pressure on beta",
        runId: "run-zeta",
        clusterLabel: "cluster-beta",
        details: [{ label: "Target", value: "db" }],
      }),
    ];
    const payloads = {
      ...defaultPayloads,
      "/api/notifications": { notifications: customNotifications },
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: /Notification history/i });
    expect(screen.getAllByTestId("notification-row")).toHaveLength(3);
    const kindSelect = screen.getByRole("combobox", {
      name: /Notification kind filter/i,
    });
    const clusterSelect = screen.getByRole("combobox", {
      name: /Notification cluster filter/i,
    });
    const searchInput = screen.getByRole("searchbox", {
      name: /Notification text search/i,
    });
    await act(async () => {
      await user.selectOptions(kindSelect, "Warning");
    });
    await waitFor(() => expect(screen.getAllByTestId("notification-row")).toHaveLength(2));
    await act(async () => {
      await user.selectOptions(clusterSelect, "cluster-beta");
    });
    await waitFor(() => expect(screen.getAllByTestId("notification-row")).toHaveLength(1));
    await act(async () => {
      await user.type(searchInput, "memory");
    });
    await waitFor(() => expect(screen.getAllByTestId("notification-row")).toHaveLength(1));
    expect(screen.getByText(/Showing 1–1 of 1/i)).toBeInTheDocument();
    expect(
      await screen.findByText(/Run run-zeta · Cluster cluster-beta/i)
    ).toBeInTheDocument();
  });

  test("pagination updates when filters reduce the dataset", async () => {
    const manyNotifications = buildNotificationList(60);
    const payloads = {
      ...defaultPayloads,
      "/api/notifications": { notifications: manyNotifications },
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: /Notification history/i });
    expect(screen.getByText(/Page 1 of 2/i)).toBeInTheDocument();
    const kindSelect = screen.getByRole("combobox", {
      name: /Notification kind filter/i,
    });
    const nextButton = screen.getByRole("button", { name: /Next notifications page/i });
    expect(nextButton).not.toBeDisabled();
    await act(async () => {
      await user.selectOptions(kindSelect, "Warning");
    });
    expect(screen.getByText(/Page 1 of 1/i)).toBeInTheDocument();
    expect(screen.getByText(/Showing 1–30 of 30/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Next notifications page/i })).toBeDisabled();
  });

  test("autorefresh dropdown persists selection and disables timer", async () => {
    localStorage.setItem(AUTOREFRESH_STORAGE_KEY, "30");
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });
    const select = await screen.findByLabelText(/auto refresh/i);
    expect(select).toHaveValue("30");
    expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 30000);

    await act(async () => {
      await user.selectOptions(select, "off");
    });
    await waitFor(() => expect(localStorage.getItem(AUTOREFRESH_STORAGE_KEY)).toBe("off"));
    await waitFor(() => expect(clearIntervalSpy).toHaveBeenCalled());
    await screen.findByText(/Auto refresh is off/i);
  });

  test("shows loading and surfaces API errors", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("network boom"))));
    render(<App />);

    expect(screen.getByText(/Loading operator data/i)).toBeInTheDocument();
    await screen.findByText(/network boom/i);
  });
});
