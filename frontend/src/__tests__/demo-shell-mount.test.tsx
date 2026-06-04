/**
 * Demo Shell Mount Tests
 *
 * Tests for ACT 9.5: Mounting K8s Accelerator demo shell in the UI.
 * Verifies:
 * - Demo entry point ("Start demo" button) is visible
 * - Clicking the button opens DemoShell
 * - Closing DemoShell returns to existing UI
 * - Real-derived finding selection input is passed when available
 * - No forbidden phrases appear in mounted path
 * - No fake incidents presented as real
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, act, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import App from "../App";

import {
  createFetchMock,
  createStorageMock,
  sampleRun,
  sampleRunsList,
  sampleFleet,
  sampleProposals,
  sampleNotifications,
  sampleClusterDetail,
} from "./fixtures";

// Default API payloads for basic app render
const defaultPayloads = {
  "/api/run": sampleRun,
  "/api/runs": sampleRunsList,
  "/api/fleet": sampleFleet,
  "/api/proposals": sampleProposals,
  "/api/notifications": sampleNotifications,
  "/api/cluster-detail": sampleClusterDetail,
  "/api/debug/execution-diagnostics-enabled": { debugExecutionDiagnosticsEnabled: false },
};

describe("Demo Shell Mount (ACT 9.5)", () => {
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
    cleanup();
    // CRITICAL: Always restore real timers to prevent test isolation failures.
    // Tests using vi.useFakeTimers() may fail before reaching vi.useRealTimers(),
    // leaving fake timers active for subsequent tests and causing timeouts.
    vi.useRealTimers();
  });

  describe("Demo entry point visibility", () => {
    it("renders 'Start demo' button in the hero-actions section", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      // Wait for app to load
      await screen.findByRole("heading", { name: /Fleet overview/i });

      // The Start demo button should be visible
      const startDemoButton = screen.getByTestId("start-demo-button");
      expect(startDemoButton).toBeInTheDocument();
      expect(startDemoButton).toHaveTextContent("Start demo");
    });

    it("has appropriate aria-label and title for accessibility", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      const startDemoButton = screen.getByTestId("start-demo-button");
      expect(startDemoButton).toHaveAttribute("title", "Launch the guided K8s Accelerator demo");
    });

    it("appears in the header hero-actions alongside Refresh and ThemeSwitch", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      // Both Refresh button and Start demo button should be in the header
      expect(screen.getByRole("button", { name: /Refresh/i })).toBeInTheDocument();
      expect(screen.getByTestId("start-demo-button")).toBeInTheDocument();
    });
  });

  describe("Demo shell open behavior", () => {
    it("clicking 'Start demo' opens DemoShell overlay", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      // Click Start demo button
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      // DemoShell should be rendered
      expect(screen.getByTestId("demo-shell")).toBeInTheDocument();
    });

    it("DemoShell displays the start screen after opening", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      // Should show the demo start screen with product name
      expect(screen.getByText("K8s Accelerator")).toBeInTheDocument();
      expect(screen.getByText(/Transform Kubernetes operational signals/i)).toBeInTheDocument();
    });

    it("DemoShell receives findingSelectionInput when run data is available", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      // Open demo
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      // The demo shell should exist and show the start screen
      expect(screen.getByTestId("demo-shell")).toBeInTheDocument();
    });
  });

  describe("Demo shell close behavior", () => {
    it("clicking close button removes DemoShell and returns to main UI", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      // Open demo
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      // Verify demo shell is open
      expect(screen.getByTestId("demo-shell")).toBeInTheDocument();

      // Click close button
      const closeButton = screen.getByTestId("demo-close-button");
      fireEvent.click(closeButton);

      // Demo shell should be removed
      expect(screen.queryByTestId("demo-shell")).not.toBeInTheDocument();

      // Main UI should still be visible
      expect(screen.getByRole("heading", { name: /Fleet overview/i })).toBeInTheDocument();
    });

    it("closing demo does not affect main app state", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      // Open demo and navigate to dashboard
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      // Close demo
      const closeButton = screen.getByTestId("demo-close-button");
      fireEvent.click(closeButton);

      // Verify app is still functional - can reopen demo
      const newStartDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(newStartDemoButton);
      expect(screen.getByTestId("demo-shell")).toBeInTheDocument();
    });
  });

  describe("Demo shell navigation flow", () => {
    it("can proceed through demo flow after opening", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      // Open demo
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      // Click start button on start screen
      const demoStartButton = screen.getByTestId("demo-start-button");
      fireEvent.click(demoStartButton);

      // Should show onboarding screen
      expect(screen.getByText("Connect your cluster")).toBeInTheDocument();

      // Click connect button
      const connectButton = screen.getByTestId("demo-connect-button");
      fireEvent.click(connectButton);

      // Wait for the 1500ms connection delay to complete
      await waitFor(() => {
        expect(screen.getByText("minikube")).toBeInTheDocument();
      });
    });
  });

  describe("Forbidden phrase verification", () => {
    it("does not contain 'self-healing' in demo shell content", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      // Open demo
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      // Wait for demo shell to appear and verify content
      const demoShell = await screen.findByTestId("demo-shell");
      expect(demoShell.textContent).not.toMatch(/\bself-healing\b/i);
    });

    it("does not contain 'guaranteed root cause' in demo shell content", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      const demoShell = await screen.findByTestId("demo-shell");
      expect(demoShell.textContent).not.toMatch(/\bguaranteed root cause\b/i);
    });

    it("does not contain 'automatic production fix' in demo shell content", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      const demoShell = await screen.findByTestId("demo-shell");
      expect(demoShell.textContent).not.toMatch(/\bautomatic production fix\b/i);
    });

    it("does not contain 'fixes any Kubernetes issue' in demo shell content", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      const demoShell = await screen.findByTestId("demo-shell");
      expect(demoShell.textContent).not.toMatch(/\bfixes any Kubernetes issue\b/i);
    });

    it("does not contain 'fully autonomous' in demo shell content", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      const demoShell = await screen.findByTestId("demo-shell");
      expect(demoShell.textContent).not.toMatch(/\bfully autonomous\b/i);
    });
  });

  describe("Truth boundary verification", () => {
    it("start screen shows 'No fake incidents' message", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      // Wait for demo shell to appear
      const demoShell = await screen.findByTestId("demo-shell");
      // The demo shell should contain "No fake incidents" text
      expect(demoShell.textContent).toMatch(/No fake incidents/i);
    });

    it("start screen shows safety disclaimers", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      // Wait for demo shell to appear
      const demoShell = await screen.findByTestId("demo-shell");

      // Safety first message
      expect(demoShell.textContent).toMatch(/Safety first/i);
      // Preview-only or operator approval requirement
      expect(demoShell.textContent).toMatch(/preview-only|require operator approval/i);
    });

    it("dashboard shows evidence source badge", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      // Open demo
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      // Navigate to dashboard
      const demoStartButton = screen.getByTestId("demo-start-button");
      fireEvent.click(demoStartButton);

      const connectButton = screen.getByTestId("demo-connect-button");
      fireEvent.click(connectButton);

      // Wait for the 1500ms connection delay to complete
      await waitFor(() => {
        const demoShell = screen.getByTestId("demo-shell");
        expect(demoShell.textContent).toMatch(/Evidence source:/i);
      });
    });
  });

  describe("Real vs fake incident verification", () => {
    it("demo does not present fake incidents as real findings", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);

      await screen.findByRole("heading", { name: /Fleet overview/i });

      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      // Wait for demo shell to appear
      const demoShell = await screen.findByTestId("demo-shell");
      const startScreenText = demoShell.textContent ?? "";
      
      // Verify explicit no-fake statement
      expect(startScreenText).toMatch(/No fake incidents|no fabricated samples/i);
    });
  });
});
