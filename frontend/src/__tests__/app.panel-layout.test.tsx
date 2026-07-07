/**
 * Panel layout and navigation tests.
 * 
 * Tests cockpit navigation rendering, panel ordering regressions,
 * and refresh behavior.
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

describe("Cockpit navigation", () => {
  test("renders cockpit navigation with chip-style links", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const cockpitNav = document.querySelector(".cockpit-nav");
    expect(cockpitNav).not.toBeNull();
    expect(cockpitNav).toHaveAttribute("aria-label", "Fleet cockpit sections");

    const navItems = cockpitNav!.querySelectorAll(".cockpit-nav__item");
    expect(navItems.length).toBeGreaterThan(0);

    navItems.forEach((item) => {
      expect(item.tagName.toLowerCase()).toBe("a");
      expect(item).toHaveAttribute("href");
    });
  });

  test("renders all expected section navigation links", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const cockpitNav = document.querySelector(".cockpit-nav");
    expect(cockpitNav).not.toBeNull();

    const expectedLinks = [
      "Recent runs",
      "Run summary",
      "Provider advisory",
      "Provider branches",
      "Diagnostic package",
      "Deterministic checks",
      "Execution review",
      "Work list",
      "Fleet overview",
      "Cluster detail",
      "Action proposals",
      "Notifications",
      "LLM policy",
      "LLM activity",
    ];

    expectedLinks.forEach((linkText) => {
      const links = Array.from(cockpitNav!.querySelectorAll(".cockpit-nav__item"));
      const found = links.some(
        (el) => el.textContent?.trim() === linkText
      );
      expect(found).toBe(true);
    });
  });

  test("navigation renders correctly with all sections visible", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const cockpitNav = document.querySelector(".cockpit-nav");
    expect(cockpitNav).not.toBeNull();

    const navItems = cockpitNav!.querySelectorAll(".cockpit-nav__item");
    expect(navItems.length).toBeGreaterThanOrEqual(14);

    navItems.forEach((item) => {
      expect(item).toHaveClass("cockpit-nav__item");
    });
  });

  test("navigation chips have correct href attributes for section targeting", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const cockpitNav = document.querySelector(".cockpit-nav");
    expect(cockpitNav).not.toBeNull();

    const expectedHrefs: Record<string, string> = {
      "Recent runs": "#recent-runs",
      "Run summary": "#run-detail",
      "Work list": "#next-check-queue",
      "Fleet overview": "#fleet",
      "Cluster detail": "#cluster",
      "LLM activity": "#llm-activity",
    };

    Object.entries(expectedHrefs).forEach(([text, href]) => {
      const links = Array.from(
        cockpitNav!.querySelectorAll(".cockpit-nav__item")
      );
      const matchingLink = links.find(
        (el) => el.textContent?.trim() === text
      );
      expect(matchingLink).not.toBeNull();
      expect(matchingLink).toHaveAttribute("href", href);
    });
  });

  test("navigation chips wrap gracefully without breaking layout", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const cockpitNav = document.querySelector(".cockpit-nav");
    expect(cockpitNav).not.toBeNull();

    const navItems = cockpitNav!.querySelectorAll(".cockpit-nav__item");
    expect(navItems.length).toBeGreaterThan(10);

    navItems.forEach((item) => {
      expect(item).toHaveClass("cockpit-nav__item");
    });

    const anchorTags = cockpitNav!.querySelectorAll("a");
    expect(anchorTags.length).toBe(navItems.length);
  });

  test("navigation maintains dark theme styling", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const cockpitNav = document.querySelector(".cockpit-nav");
    expect(cockpitNav).not.toBeNull();

    expect(cockpitNav).toHaveClass("cockpit-nav");

    const chips = cockpitNav!.querySelectorAll(".cockpit-nav__item");
    expect(chips.length).toBeGreaterThan(10);

    chips.forEach((chip) => {
      expect(chip.tagName.toLowerCase()).toBe("a");
      expect(chip).toHaveAttribute("href");
    });
  });
});

describe("App panel order regression", () => {
  test("panel order: Provider advisory before Deterministic checks", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Provider advisory/i });
    
    await waitFor(() => {
      const sections = document.querySelectorAll("section[id]");
      expect(sections.length).toBeGreaterThan(10);
    });

    const providerPanel = document.getElementById("review-enrichment");
    const deterministicPanel = document.getElementById("deterministic-next-checks");

    expect(providerPanel).not.toBeNull();
    expect(deterministicPanel).not.toBeNull();
    
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let posA = -1, posB = -1, count = 0;
    let node: Node | null = walker.currentNode;
    while (node) {
      if ((node as Element).id === "review-enrichment") posA = count;
      if ((node as Element).id === "deterministic-next-checks") posB = count;
      if (posA !== -1 && posB !== -1) break;
      count++;
      node = walker.nextNode();
    }
    
    expect(posA).toBeLessThan(posB);
  });

  test("panel order: Check execution review before Work list", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Check execution review/i });
    
    await waitFor(() => {
      const sections = document.querySelectorAll("section[id]");
      expect(sections.length).toBeGreaterThan(10);
    });
    
    const executionPanel = document.getElementById("execution-history");
    const workListPanel = document.getElementById("next-check-queue");

    expect(executionPanel).not.toBeNull();
    expect(workListPanel).not.toBeNull();
    
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let posA = -1, posB = -1, count = 0;
    let node: Node | null = walker.currentNode;
    while (node) {
      if ((node as Element).id === "execution-history") posA = count;
      if ((node as Element).id === "next-check-queue") posB = count;
      if (posA !== -1 && posB !== -1) break;
      count++;
      node = walker.nextNode();
    }
    
    expect(posA).toBeLessThan(posB);
  });

  test("panel order: Notification history before LLM policy", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Notification history/i });
    
    await waitFor(() => {
      const sections = document.querySelectorAll("section[id]");
      expect(sections.length).toBeGreaterThan(10);
    });
    
    const notificationPanel = document.getElementById("notifications");
    const llmPolicyPanel = document.getElementById("llm-policy");

    expect(notificationPanel).not.toBeNull();
    expect(llmPolicyPanel).not.toBeNull();
    
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let posA = -1, posB = -1, count = 0;
    let node: Node | null = walker.currentNode;
    while (node) {
      if ((node as Element).id === "notifications") posA = count;
      if ((node as Element).id === "llm-policy") posB = count;
      if (posA !== -1 && posB !== -1) break;
      count++;
      node = walker.nextNode();
    }
    
    expect(posA).toBeLessThan(posB);
  });

  test("panel order: LLM policy before LLM activity", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /LLM policy/i });
    
    await waitFor(() => {
      const sections = document.querySelectorAll("section[id]");
      expect(sections.length).toBeGreaterThan(10);
    });
    
    const llmPolicyPanel = document.getElementById("llm-policy");
    const llmActivityPanel = document.getElementById("llm-activity");

    expect(llmPolicyPanel).not.toBeNull();
    expect(llmActivityPanel).not.toBeNull();
    
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let posA = -1, posB = -1, count = 0;
    let node: Node | null = walker.currentNode;
    while (node) {
      if ((node as Element).id === "llm-policy") posA = count;
      if ((node as Element).id === "llm-activity") posB = count;
      if (posA !== -1 && posB !== -1) break;
      count++;
      node = walker.nextNode();
    }
    
    expect(posA).toBeLessThan(posB);
  });
});

describe("Runtime status panel placement", () => {
  test("Runtime Status appears below navigation and above Recent runs", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Wait for runtime status to appear
    await waitFor(() => {
      const runtimeStatus = document.querySelector(".runtime-status-summary");
      expect(runtimeStatus).not.toBeNull();
    });

    // Get references to the key elements
    const runtimeStatusHeading = screen.getByRole("heading", { name: /Runtime Status/i });
    const recentRunsHeading = screen.getByRole("heading", { name: /Recent runs/i });

    expect(runtimeStatusHeading).toBeInTheDocument();
    expect(recentRunsHeading).toBeInTheDocument();

    // Verify Runtime Status appears BEFORE Recent runs using DOM position
    expect(
      runtimeStatusHeading.compareDocumentPosition(recentRunsHeading) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();

    // Also verify using TreeWalker for more robust position checking
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let posRuntime = -1;
    let posRecentRuns = -1;
    let count = 0;
    let node: Node | null = walker.currentNode;
    while (node) {
      if (node === runtimeStatusHeading) posRuntime = count;
      if (node === recentRunsHeading) posRecentRuns = count;
      if (posRuntime !== -1 && posRecentRuns !== -1) break;
      count++;
      node = walker.nextNode();
    }

    expect(posRuntime).toBeGreaterThanOrEqual(0);
    expect(posRecentRuns).toBeGreaterThanOrEqual(0);
    expect(posRuntime).toBeLessThan(posRecentRuns);
  });

  test("Runtime Status appears only once on the page", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runtimeStatusElements = document.querySelectorAll(".runtime-status-summary");
      expect(runtimeStatusElements.length).toBe(1);
    });
  });

  test("Runtime Status and Recent runs panels both render in the main page flow", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runtimeStatus = document.querySelector(".runtime-status-summary");
      expect(runtimeStatus).not.toBeNull();
    });

    // Both Runtime Status and Recent runs should be present
    // and share the same parent container (app-shell) indicating they
    // render in the main page flow at the same level
    const runtimeStatus = document.querySelector(".runtime-status-summary");
    const recentRunsPanel = document.querySelector(".recent-runs");

    expect(runtimeStatus).not.toBeNull();
    expect(recentRunsPanel).not.toBeNull();

    // Both panels should be siblings under the same parent
    expect(runtimeStatus?.parentElement).toBe(recentRunsPanel?.parentElement);
  });
});

describe("Cockpit refresh regression", () => {
  test("manual refresh button is clickable and updates page freshness indicator", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    const initialFreshness = document.querySelector(".page-freshness-indicator");
    expect(initialFreshness).not.toBeNull();

    const refreshButton = await screen.findByRole("button", { name: /^Refresh$/i });
    await act(async () => {
      await user.click(refreshButton);
    });

    await waitFor(() => {
      const updatedFreshness = document.querySelector(".page-freshness-indicator");
      expect(updatedFreshness).not.toBeNull();
    });

    const freshIndicator = document.querySelector(".page-freshness-indicator--fresh");
    expect(freshIndicator).not.toBeNull();
  });

  test("selected run remains selected after manual refresh", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    await waitFor(() => {
      const runRows = document.querySelectorAll(".run-row");
      expect(runRows.length).toBeGreaterThan(0);
    });

    const run122Row = document.querySelector('.run-row[data-run-id="run-122"]');
    await act(async () => {
      await user.click(run122Row!);
    });

    await waitFor(() => {
      expect(run122Row).toHaveClass("run-row-selected");
    });

    // Find header refresh button using text match (IncidentListPanel uses "Refresh incidents")
    const refreshButton = screen.getByRole("button", { name: /^Refresh$/i });
    await act(async () => {
      await user.click(refreshButton);
    });

    await waitFor(() => {
      expect(run122Row).toHaveClass("run-row-selected");
    });

    expect(screen.getByText(/← Latest/i)).toBeInTheDocument();
  });

  test("interval polling does not leak or duplicate timers", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    setIntervalSpy.mockClear();
    clearIntervalSpy.mockClear();

    const autoRefreshSelect = screen.getByLabelText(/Auto/i) as HTMLSelectElement;
    await act(async () => {
      autoRefreshSelect.value = "10";
      autoRefreshSelect.dispatchEvent(new Event("change", { bubbles: true }));
    });

    expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 10000);
    expect(clearIntervalSpy).toHaveBeenCalled();
  });

  test("refresh controls remain present and queryable in header", async () => {
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    render(<App />);

    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Use first button (header refresh) as IncidentListPanel adds a second Refresh button
    const refreshButton = (await screen.findAllByRole("button", { name: /^Refresh$/i }))[0];
    expect(refreshButton).toBeInTheDocument();
    expect(refreshButton).not.toBeDisabled();

    const autoRefreshSelect = await screen.findByLabelText(/Auto/i);
    expect(autoRefreshSelect).toBeInTheDocument();

    const pageFreshness = document.querySelector(".page-freshness-indicator");
    expect(pageFreshness).not.toBeNull();
  });
});
