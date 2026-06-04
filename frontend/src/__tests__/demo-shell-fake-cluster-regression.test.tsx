/**
 * Demo Shell Fake Cluster Regression Tests
 *
 * Tests to verify that fake cluster names (minikube, kind-dev, prod-cluster)
 * never appear in the demo shell when launched from the main app.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import "@testing-library/jest-dom";
import App from "../App";
import { DemoShell } from "../components/DemoShell";
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

const renderDemoShell = (props = {}) => render(<DemoShell {...props} />);

describe("DemoShell Fake Cluster Regression", () => {
  beforeEach(() => {
    cleanup();
  });

  describe("Fake cluster names absent in standalone DemoShell", () => {
    it("does not contain 'minikube' in start screen", () => {
      renderDemoShell();
      const container = document.querySelector(".demo-shell-overlay");
      expect(container?.textContent).not.toMatch(/\bminikube\b/i);
    });

    it("does not contain 'kind-dev' in start screen", () => {
      renderDemoShell();
      const container = document.querySelector(".demo-shell-overlay");
      expect(container?.textContent).not.toMatch(/\bkind-dev\b/i);
    });

    it("does not contain 'prod-cluster' in start screen", () => {
      renderDemoShell();
      const container = document.querySelector(".demo-shell-overlay");
      expect(container?.textContent).not.toMatch(/\bprod-cluster\b/i);
    });

    it("does not show fake cluster selector dropdown", () => {
      renderDemoShell({ initialStep: "onboarding" });
      const contextSelect = document.getElementById("kube-context");
      expect(contextSelect).not.toBeInTheDocument();
    });
  });

  describe("Fake cluster names absent when mounted from App", () => {
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

    it("does not contain 'minikube' when opened from app", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });

      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      const demoShell = await screen.findByTestId("demo-shell");
      expect(demoShell.textContent).not.toMatch(/\bminikube\b/i);
    });

    it("does not contain 'kind-dev' when opened from app", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });

      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      const demoShell = await screen.findByTestId("demo-shell");
      expect(demoShell.textContent).not.toMatch(/\bkind-dev\b/i);
    });

    it("does not contain 'prod-cluster' when opened from app", async () => {
      vi.stubGlobal("fetch", createFetchMock(defaultPayloads));
      render(<App />);
      await screen.findByRole("heading", { name: /Fleet overview/i });

      const startDemoButton = screen.getByTestId("start-demo-button");
      fireEvent.click(startDemoButton);

      const demoShell = await screen.findByTestId("demo-shell");
      expect(demoShell.textContent).not.toMatch(/\bprod-cluster\b/i);
    });

    it("does not show fake cluster selector dropdown in onboarding", async () => {
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
  });
});
