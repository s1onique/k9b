/**
 * Demo Shell Mount Context Tests
 *
 * Tests for ACT 9.5: Mounting K8s Accelerator demo shell in the UI.
 * Verifies:
 * - Forbidden phrase verification
 * - Fake cluster name regression verification
 * - Truth boundary verification
 * - Real vs fake incident verification
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

describe("Demo Shell Mount Context (ACT 9.5)", () => {
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

  describe("Forbidden phrase verification", () => {
    it("does not contain 'self-healing' in demo shell content", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
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

  describe("Fake cluster name regression verification", () => {
    it("does not contain fake cluster name 'minikube' when opened from app", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      const demoShell = await screen.findByTestId("demo-shell");
      expect(demoShell.textContent).not.toMatch(/\bminikube\b/i);
    });

    it("does not contain fake cluster name 'kind-dev' when opened from app", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      const demoShell = await screen.findByTestId("demo-shell");
      expect(demoShell.textContent).not.toMatch(/\bkind-dev\b/i);
    });

    it("does not contain fake cluster name 'prod-cluster' when opened from app", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      const demoShell = await screen.findByTestId("demo-shell");
      expect(demoShell.textContent).not.toMatch(/\bprod-cluster\b/i);
    });

    it("does not show fake cluster selector dropdown", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      const demoStartButton = screen.getByTestId("demo-start-button");
      fireEvent.click(demoStartButton);
      const contextSelect = document.getElementById("kube-context");
      expect(contextSelect).not.toBeInTheDocument();
    });

    it("shows real cluster context when available in dashboard", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      const demoStartButton = screen.getByTestId("demo-start-button");
      fireEvent.click(demoStartButton);
      const continueButton = screen.getByTestId("demo-connect-button");
      fireEvent.click(continueButton);
      await waitFor(() => {
        expect(screen.getByTestId("demo-shell")).toHaveAttribute("data-demo-step", "dashboard");
      });
      const demoShell = screen.getByTestId("demo-shell");
      expect(demoShell.textContent).toMatch(/Real run evidence/i);
    });
  });

  describe("Truth boundary verification", () => {
    it("start screen shows 'No fake incidents' message", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      const demoShell = await screen.findByTestId("demo-shell");
      expect(demoShell.textContent).toMatch(/No fake incidents/i);
    });

    it("start screen shows safety disclaimers", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      const demoShell = await screen.findByTestId("demo-shell");
      expect(demoShell.textContent).toMatch(/Safety first/i);
      expect(demoShell.textContent).toMatch(/preview-only|require operator approval/i);
    });

    it("dashboard shows evidence source badge", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });
      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);
      const demoStartButton = screen.getByTestId("demo-start-button");
      fireEvent.click(demoStartButton);
      const continueButton = screen.getByTestId("demo-connect-button");
      fireEvent.click(continueButton);
      await waitFor(() => {
        const demoShell = screen.getByTestId("demo-shell");
        expect(demoShell.textContent).toMatch(/Evidence source:|Real run evidence/i);
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
      const demoShell = await screen.findByTestId("demo-shell");
      const startScreenText = demoShell.textContent ?? "";
      expect(startScreenText).toMatch(/No fake incidents|no fabricated samples/i);
    });
  });
});