/**
 * Notifications and autorefresh tests.
 * 
 * Tests notification history table rendering, pagination, filtering,
 * and autorefresh persistence.
 * 
 * Split from app.test.tsx as part of the LLM-friendly file split.
 */

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, test, vi } from "vitest";
import App, { AUTOREFRESH_STORAGE_KEY } from "../App";

import {
  buildNotificationEntry,
  buildNotificationList,
  createFetchMock,
  createStorageMock,
  defaultPayloads,
  sampleNotifications,
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

describe("Notification history", () => {
  test("renders notification history table and pagination summary", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);
    const heading = await screen.findByRole("heading", { name: /Notification history/i });
    expect(heading).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: /Notification history table/i });
    expect(within(table).getByText(sampleNotifications.notifications[0].summary)).toBeInTheDocument();
    await screen.findAllByTestId("notification-row");
    expect(within(table).getAllByTestId("notification-row")).toHaveLength(1);
    expect(screen.getAllByText(/Showing 1–1 of 1/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/50 per page/i)).toBeInTheDocument();
  });

  test("sorts notifications newest first", async () => {
    const orderedNotifications = [
      buildNotificationEntry(0, { summary: "Newest", timestamp: "2026-04-06T12:00:00Z" }),
      buildNotificationEntry(1, { summary: "Older", timestamp: "2026-04-06T11:00:00Z" }),
    ];
    const payloads = {
      ...defaultPayloads,
      "/api/notifications": {
        notifications: orderedNotifications,
        total: orderedNotifications.length,
        page: 1,
        limit: 50,
        total_pages: 1,
      },
      "/api/notifications?limit=50&page=1": {
        notifications: orderedNotifications,
        total: orderedNotifications.length,
        page: 1,
        limit: 50,
        total_pages: 1,
      },
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
    const pageOne = {
      notifications: manyNotifications.slice(0, 50),
      total: manyNotifications.length,
      page: 1,
      limit: 50,
      total_pages: 2,
    };
    const pageTwo = {
      notifications: manyNotifications.slice(50),
      total: manyNotifications.length,
      page: 2,
      limit: 50,
      total_pages: 2,
    };
    const payloads = {
      ...defaultPayloads,
      "/api/notifications": pageOne,
      "/api/notifications?limit=50&page=1": pageOne,
      "/api/notifications?limit=50&page=2": pageTwo,
    };
    const fetchMock = createFetchMock(payloads);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: /Notification history/i });
    const notificationSection = document.getElementById("notifications");
    await waitFor(() => expect(notificationSection!.textContent).toMatch(/Page\s+1\s+of\s+2/));
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = typeof input === "string" ? input : input.url;
      return url.includes("limit=50&page=1");
    })).toBe(true);
    const nextButton = screen.getByRole("button", { name: /notifications next page/i });
    expect(nextButton).not.toBeDisabled();
    await act(async () => {
      await user.click(nextButton);
    });
    await waitFor(() => expect(notificationSection!.textContent).toMatch(/Page\s+2\s+of\s+2/));
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = typeof input === "string" ? input : input.url;
      return url.includes("/api/notifications?limit=50&page=2");
    })).toBe(true);
    const pageTwoRows = await screen.findAllByTestId("notification-row");
    expect(pageTwoRows).toHaveLength(10);
    const prevButton = screen.getByRole("button", { name: /notifications previous page/i });
    expect(prevButton).not.toBeDisabled();
    await act(async () => {
      await user.click(prevButton);
    });
    await waitFor(() => expect(notificationSection!.textContent).toMatch(/Page\s+1\s+of\s+2/));
  });

  test("pagination remains single-page when server reports only one page", async () => {
    const limitedNotifications = buildNotificationList(30);
    const payload = {
      notifications: limitedNotifications,
      total: limitedNotifications.length,
      page: 1,
      limit: 50,
      total_pages: 1,
    };
    const payloads = {
      ...defaultPayloads,
      "/api/notifications": payload,
      "/api/notifications?limit=50&page=1": payload,
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    render(<App />);
    await screen.findByRole("heading", { name: /Notification history/i });
    await screen.findAllByTestId("notification-row");
    await screen.findByRole("option", { name: /Warning/i });
    const notificationSection = document.getElementById("notifications");
    expect(notificationSection).not.toBeNull();
    expect(within(notificationSection!).getByText(/Showing 1–30 of 30/i)).toBeInTheDocument();
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
    const basePayload = {
      notifications: customNotifications,
      total: 3,
      page: 1,
      limit: 50,
      total_pages: 1,
    };
    const warningPayload = {
      notifications: customNotifications.filter((entry) => entry.kind === "Warning"),
      total: 2,
      page: 1,
      limit: 50,
      total_pages: 1,
    };
    const clusterPayload = {
      notifications: customNotifications.filter(
        (entry) => entry.clusterLabel === "cluster-beta" && entry.kind === "Warning"
      ),
      total: 1,
      page: 1,
      limit: 50,
      total_pages: 1,
    };
    const searchPayload = {
      notifications: customNotifications.filter(
        (entry) => entry.summary.includes("Memory") || entry.details.some((detail) => detail.value === "db")
      ),
      total: 1,
      page: 1,
      limit: 50,
      total_pages: 1,
    };
    const payloads = {
      ...defaultPayloads,
      "/api/notifications": basePayload,
      "/api/notifications?limit=50&page=1": basePayload,
      "/api/notifications?kind=Warning&limit=50&page=1": warningPayload,
      "/api/notifications?kind=Warning&cluster_label=cluster-beta&limit=50&page=1": clusterPayload,
      "/api/notifications?kind=Warning&cluster_label=cluster-beta&search=memory&limit=50&page=1":
        searchPayload,
    };
    const fetchMock = createFetchMock(payloads);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: /Notification history/i });
    await waitFor(() => expect(screen.getAllByTestId("notification-row")).toHaveLength(3));
    const kindSelect = screen.getByRole("combobox", {
      name: /Notification kind filter/i,
    });
    await screen.findByRole("option", { name: /Warning/i });
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
    expect(screen.getAllByText(/Showing 1–1 of 1/i).length).toBeGreaterThan(0);
    expect(
      await screen.findByText(/Run run-zeta · Cluster cluster-beta/i)
    ).toBeInTheDocument();
  });

  test("pagination summary updates when filters reduce the dataset", async () => {
    const manyNotifications = buildNotificationList(60);
    const basePayload = {
      notifications: manyNotifications.slice(0, 50),
      total: manyNotifications.length,
      page: 1,
      limit: 50,
      total_pages: 2,
    };
    const searchPayload = {
      notifications: manyNotifications.slice(0, 30),
      total: 30,
      page: 1,
      limit: 50,
      total_pages: 1,
    };
    const payloads = {
      ...defaultPayloads,
      "/api/notifications": basePayload,
      "/api/notifications?limit=50&page=1": basePayload,
      "/api/notifications?search=Entry&limit=50&page=1": searchPayload,
    };
    vi.stubGlobal("fetch", createFetchMock(payloads));
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: /Notification history/i });

    const notificationSection = document.getElementById("notifications");
    expect(notificationSection).not.toBeNull();
    await waitFor(() => {
      expect(notificationSection!.textContent).toMatch(/Page\s+1\s+of\s+2/);
    });

    expect(notificationSection!.textContent).toMatch(/Showing.*1.*50.*of.*60/);

    const searchInput = screen.getByRole("searchbox", {
      name: /Notification text search/i,
    });
    await act(async () => {
      await user.type(searchInput, "Entry");
    });
    await waitFor(() => expect(screen.getAllByTestId("notification-row")).toHaveLength(30));

    expect(notificationSection!.textContent).toMatch(/Showing.*1.*30.*of.*30/);
    expect(screen.queryByRole("button", { name: /notifications next page/i })).toBeNull();
  });
});

describe("Autorefresh", () => {
  test("autorefresh dropdown persists selection and disables timer", async () => {
    localStorage.setItem(AUTOREFRESH_STORAGE_KEY, "30");
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });
    const select = await screen.findByLabelText(/Auto/i);
    expect(select).toHaveValue("30");
    expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 30000);

    await act(async () => {
      await user.selectOptions(select, "off");
    });
    await waitFor(() => expect(localStorage.getItem(AUTOREFRESH_STORAGE_KEY)).toBe("off"));
    await waitFor(() => expect(clearIntervalSpy).toHaveBeenCalled());
  });
});
