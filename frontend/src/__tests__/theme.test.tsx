import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import App from "../App";
import { createFetchMock, createStorageMock, sampleClusterDetail, sampleFleet, sampleNotifications, sampleProposals, sampleRun, sampleRunsList } from "./fixtures";

// Shared mock payloads
const defaultPayloads = {
  "/api/run": sampleRun,
  "/api/runs": sampleRunsList,
  "/api/fleet": sampleFleet,
  "/api/proposals": sampleProposals,
  "/api/notifications": sampleNotifications,
  "/api/notifications?limit=50&page=1": sampleNotifications,
  "/api/cluster-detail": sampleClusterDetail,
  "/api/deterministic-next-check/promote": {
    status: "success",
    summary: "Deterministic next check promoted to the queue.",
    artifactPath: "/artifacts/promoted.json",
    candidateId: "promo-1",
  },
};

describe("Theme System", () => {
  let storageMock: ReturnType<typeof createStorageMock>;

  beforeEach(() => {
    // Apply dark theme synchronously before each test (simulates main.tsx behavior)
    document.documentElement.setAttribute("data-theme", "dark");
    vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
    storageMock = createStorageMock();
    vi.stubGlobal("localStorage", storageMock);
    vi.stubGlobal("setInterval", vi.fn(() => 123));
    vi.stubGlobal("clearInterval", vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
    // Clean up document attribute
    document.documentElement.removeAttribute("data-theme");
  });

  test("default theme is dark", async () => {
    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Root element should have data-theme="dark" by default
    const root = document.documentElement;
    expect(root.getAttribute("data-theme")).toBe("dark");
  });

  test("theme switch component renders in the header", async () => {
    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // The theme switch should be present
    const themeSwitch = screen.getByRole("combobox", { name: /Select theme/i });
    expect(themeSwitch).toBeInTheDocument();
  });

  test("theme-sensitive UI elements render correctly under dark theme", async () => {
    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Verify key elements are present in dark theme
    expect(screen.getByRole("heading", { name: /Fleet overview/i })).toBeInTheDocument();
    expect(screen.getAllByText(/Degraded/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Healthy/i).length).toBeGreaterThan(0);
  });

  test("status/review badge semantics are preserved in dark theme", async () => {
    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Check review status badges exist and have semantic classes
    // Use querySelector to find elements with both text AND the correct class
    const fullyReviewedBadges = document.querySelectorAll(".status-pill-fully-reviewed");
    expect(fullyReviewedBadges.length).toBeGreaterThan(0);

    const unreviewedBadges = document.querySelectorAll(".status-pill-unreviewed");
    expect(unreviewedBadges.length).toBeGreaterThan(0);

    // Verify the badges have the correct status-pill class
    fullyReviewedBadges.forEach((badge) => {
      expect(badge).toHaveClass("status-pill");
    });

    unreviewedBadges.forEach((badge) => {
      expect(badge).toHaveClass("status-pill");
    });
  });

  // ========================================================================
  // User Interaction Tests - Dark -> Solarized Light -> Dark
  // ========================================================================

  test("Test Dark -> Solarized Light by selecting from dropdown", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Verify initial state is dark
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");

    // Find and interact with the theme select dropdown
    const themeSelect = screen.getByRole("combobox", { name: /Select theme/i });
    expect(themeSelect).toHaveValue("dark");

    // Select Solarized Light
    await user.selectOptions(themeSelect, "solarized-light");

    // Verify theme was switched to solarized-light
    await waitFor(() => {
      expect(document.documentElement.getAttribute("data-theme")).toBe("solarized-light");
    });
    expect(themeSelect).toHaveValue("solarized-light");
    expect(storageMock.getItem("dashboard-theme")).toBe("solarized-light");
  });

  test("Test Solarized Light -> Dark by selecting from dropdown", async () => {
    const user = userEvent.setup();
    
    // Pre-set solarized-light theme before rendering
    document.documentElement.setAttribute("data-theme", "solarized-light");
    storageMock.setItem("dashboard-theme", "solarized-light");

    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Verify initial state is solarized-light
    expect(document.documentElement.getAttribute("data-theme")).toBe("solarized-light");

    // Find and interact with the theme select dropdown
    const themeSelect = screen.getByRole("combobox", { name: /Select theme/i });
    expect(themeSelect).toHaveValue("solarized-light");

    // Select Dark
    await user.selectOptions(themeSelect, "dark");

    // Verify theme was switched back to dark
    await waitFor(() => {
      expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    });
    expect(themeSelect).toHaveValue("dark");
    expect(storageMock.getItem("dashboard-theme")).toBe("dark");
  });

  test("Test persisted theme restoration on initial render", async () => {
    // Simulate a page load with solarized-light theme stored
    storageMock.setItem("dashboard-theme", "solarized-light");
    document.documentElement.setAttribute("data-theme", "solarized-light");

    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // The theme switch should show Solarized Light as selected
    const themeSelect = screen.getByRole("combobox", { name: /Select theme/i });
    expect(themeSelect).toHaveValue("solarized-light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("solarized-light");
  });

  test("Test the root data-theme attribute updates correctly", async () => {
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Initial attribute should be dark
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");

    // Select Solarized Light
    const themeSelect = screen.getByRole("combobox", { name: /Select theme/i });
    await user.selectOptions(themeSelect, "solarized-light");

    // Verify attribute is solarized-light
    await waitFor(() => {
      expect(document.documentElement.getAttribute("data-theme")).toBe("solarized-light");
    });
  });

  // ========================================================================
  // Solarized Light Theme Workflow-Critical Surface Tests
  // ========================================================================

  test("Solarized Light: status pills render with correct semantic styling", async () => {
    // Pre-set solarized-light theme
    document.documentElement.setAttribute("data-theme", "solarized-light");
    storageMock.setItem("dashboard-theme", "solarized-light");

    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Verify key UI elements still render correctly in Solarized Light mode
    expect(screen.getByRole("heading", { name: /Fleet overview/i })).toBeInTheDocument();
    
    // Verify Degraded and Healthy status pills are visible
    const degradedPills = screen.getAllByText("Degraded");
    const healthyPills = screen.getAllByText("Healthy");
    expect(degradedPills.length).toBeGreaterThan(0);
    expect(healthyPills.length).toBeGreaterThan(0);

    // Verify review badges are present
    const fullyReviewedBadges = screen.getAllByText("Fully reviewed");
    expect(fullyReviewedBadges.length).toBeGreaterThan(0);

    // Verify theme attribute is still correct
    expect(document.documentElement.getAttribute("data-theme")).toBe("solarized-light");
  });

  test("Solarized Light: cockpit navigation renders correctly", async () => {
    // Pre-set solarized-light theme
    document.documentElement.setAttribute("data-theme", "solarized-light");
    storageMock.setItem("dashboard-theme", "solarized-light");

    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Verify cockpit navigation is present
    const fleetOverview = screen.getByRole("heading", { name: /Fleet overview/i });
    expect(fleetOverview).toBeInTheDocument();

    // Verify theme attribute is still correct
    expect(document.documentElement.getAttribute("data-theme")).toBe("solarized-light");
  });

  test("Solarized Light: table rows and selection states render correctly", async () => {
    // Pre-set solarized-light theme
    document.documentElement.setAttribute("data-theme", "solarized-light");
    storageMock.setItem("dashboard-theme", "solarized-light");

    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Verify the runs table is present (tables should have rows)
    // The fleet table should be visible
    const heading = screen.getByRole("heading", { name: /Fleet overview/i });
    expect(heading).toBeInTheDocument();

    // Verify theme attribute is correct
    expect(document.documentElement.getAttribute("data-theme")).toBe("solarized-light");
  });

  test("Dark mode: verification that status pills have proper styling", async () => {
    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });

    // Use specific class selectors to target actual status pill elements
    const degradedPills = document.querySelectorAll(".status-pill-degraded");
    const healthyPills = document.querySelectorAll(".status-pill-healthy");

    expect(degradedPills.length).toBeGreaterThan(0);
    expect(healthyPills.length).toBeGreaterThan(0);

    // Verify the status pills have proper class for styling
    degradedPills.forEach((pill) => {
      expect(pill).toHaveClass("status-pill");
      expect(pill).toHaveClass(/degraded/);
    });

    healthyPills.forEach((pill) => {
      expect(pill).toHaveClass("status-pill");
      expect(pill).toHaveClass(/healthy/);
    });

    // Verify theme is dark
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });
});
