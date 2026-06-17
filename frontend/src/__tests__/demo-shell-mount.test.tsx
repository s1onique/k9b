/**
 * Demo Shell Mount Tests
 *
 * Tests for ACT 9.5: Mounting K8s Accelerator demo shell in the UI.
 * Verifies:
 * - Demo entry point ("Start demo" button) is visible
 * - Clicking the button opens DemoShell
 * - Closing DemoShell returns to existing UI
 * - Real context metadata is passed to DemoShell
 * - Button copy is correct
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
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
    vi.useRealTimers();
  });

  describe("Demo entry point visibility", () => {
    it("renders 'Start demo' button in the hero-actions section", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
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
      expect(screen.getByRole("button", { name: /^Refresh$/i })).toBeInTheDocument();
      expect(screen.getByTestId("start-demo-button")).toBeInTheDocument();
    });
  });

  describe("Demo shell open behavior", () => {
    it("clicking 'Start demo' opens DemoShell overlay", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      expect(screen.getByTestId("demo-shell")).toBeInTheDocument();
    });

    it("DemoShell displays the start screen after opening", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      expect(screen.getByText("K8s Accelerator")).toBeInTheDocument();
      expect(screen.getByText(/Transform Kubernetes operational signals/i)).toBeInTheDocument();
    });

    it("DemoShell receives findingSelectionInput when run data is available", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      expect(screen.getByTestId("demo-shell")).toBeInTheDocument();
    });
  });

  describe("Demo shell close behavior", () => {
    it("clicking close button removes DemoShell and returns to main UI", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      expect(screen.getByTestId("demo-shell")).toBeInTheDocument();
      const closeButton = screen.getByTestId("demo-close-button");
      fireEvent.click(closeButton);
      expect(screen.queryByTestId("demo-shell")).not.toBeInTheDocument();
      expect(screen.getByRole("heading", { name: /Fleet overview/i })).toBeInTheDocument();
    });

    it("closing demo does not affect main app state", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      const closeButton = screen.getByTestId("demo-close-button");
      fireEvent.click(closeButton);
      const newStartDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(newStartDemoButton);
      expect(screen.getByTestId("demo-shell")).toBeInTheDocument();
    });
  });

  describe("Demo shell navigation flow with real context", () => {
    it("can proceed through demo flow after opening", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      const demoStartButton = screen.getByTestId("demo-start-button");
      expect(demoStartButton).toHaveTextContent("Use selected real run");
      fireEvent.click(demoStartButton);
      expect(screen.getByText("Selected real run")).toBeInTheDocument();
      const continueButton = screen.getByTestId("demo-connect-button");
      expect(continueButton).toHaveTextContent("Continue with selected run");
      fireEvent.click(continueButton);
      await waitFor(() => {
        expect(screen.getByTestId("demo-shell")).toHaveAttribute("data-demo-step", "dashboard");
      });
    });

    it("shows real context on onboarding screen when launched from app", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      const demoStartButton = screen.getByTestId("demo-start-button");
      fireEvent.click(demoStartButton);
      expect(screen.getByTestId("demo-context-run-id")).toBeInTheDocument();
      expect(screen.getByTestId("demo-context-freshness")).toBeInTheDocument();
    });
  });

  describe("Button copy verification", () => {
    it("start button says 'Use selected real run' not 'Start real-cluster demo'", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      const demoStartButton = screen.getByTestId("demo-start-button");
      expect(demoStartButton).toHaveTextContent("Use selected real run");
    });

    it("continue button says 'Continue with selected run' not 'Connect in read-only mode'", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      const demoStartButton = screen.getByTestId("demo-start-button");
      fireEvent.click(demoStartButton);
      const continueButton = screen.getByTestId("demo-connect-button");
      expect(continueButton).toHaveTextContent("Continue with selected run");
    });
  });
});