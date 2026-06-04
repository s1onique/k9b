/**
 * Demo Shell Operator Worklist Shape Regression Tests
 *
 * Bug: TypeError: dt.map is not a function
 * 
 * Root cause: The findingSelectionInput useMemo in App.tsx assumed
 * run.operatorWorklist was a direct array. In reality, the backend returns
 * an OperatorWorklistPayload object: { items: [...], totalItems, etc. }
 * 
 * Fix: Normalize the payload shape before calling .map():
 * - Check if it's an array directly
 * - Check if it has an items array
 * - Check if it has a candidates array
 * - Fall back to empty array
 * 
 * Also guards OperatorWorklistCard against objects without items array.
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

describe("Regression: operatorWorklist non-array shape handling (ACT 9.5 patch)", () => {
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

  const runWithWorklistAsObjectWithItems = {
    ...defaultPayloads["/api/run"],
    operatorWorklist: {
      items: [
        {
          id: "wl-1", rank: 1, workstream: "incident", title: "CrashLoopBackOff detected",
          description: "Pod in crash loop", command: "kubectl logs", targetCluster: "cluster-a",
          targetContext: "cluster-a · default namespace", reason: "CrashLoopBackOff",
          expectedEvidence: "pod logs showing crash", safetyNote: "Read-only diagnostic",
          itemState: "queued", approvalState: null, executionState: null, feedbackState: null,
          sourceArtifactRefs: [],
        },
        {
          id: "wl-2", rank: 2, workstream: "evidence", title: "Check pod resources",
          description: null, command: null, targetCluster: "cluster-b", targetContext: null,
          reason: "High memory usage", expectedEvidence: null, safetyNote: null,
          itemState: "advisory", approvalState: null, executionState: null, feedbackState: null,
          sourceArtifactRefs: [],
        },
      ],
      totalItems: 2, completedItems: 0, pendingItems: 2, blockedItems: 0,
    },
  };

  const runWithWorklistAsObjectWithCandidates = {
    ...defaultPayloads["/api/run"],
    operatorWorklist: {
      candidates: [{ severity: "critical", resource: "cluster-a", status: "CrashLoopBackOff", message: "Pod crash" }],
    },
  };

  const runWithWorklistAsUnrelatedObject = {
    ...defaultPayloads["/api/run"],
    operatorWorklist: { status: "some_status", total: 7, pending: 7 },
  };

  const runWithWorklistAsDirectArray = {
    ...defaultPayloads["/api/run"],
    operatorWorklist: [{ severity: "critical", resource: "cluster-a", status: "Failed", message: "Pod failed" }],
  };

  const runWithWorklistNull = { ...defaultPayloads["/api/run"], operatorWorklist: null };
  const runWithWorklistUndefined = { ...defaultPayloads["/api/run"], operatorWorklist: undefined };

  it("App renders without crash when operatorWorklist is an object with items array", async () => {
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": runWithWorklistAsObjectWithItems }));
    expect(() => render(<App />)).not.toThrow();
    await screen.findByRole("heading", { name: /Fleet overview/i });
    expect(screen.getByTestId("start-demo-button")).toBeInTheDocument();
  });

  it("App renders without crash when operatorWorklist is an object with candidates array", async () => {
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": runWithWorklistAsObjectWithCandidates }));
    expect(() => render(<App />)).not.toThrow();
    await screen.findByRole("heading", { name: /Fleet overview/i });
    expect(screen.getByTestId("start-demo-button")).toBeInTheDocument();
  });

  it("App renders without crash when operatorWorklist is an unrelated object", async () => {
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": runWithWorklistAsUnrelatedObject }));
    expect(() => render(<App />)).not.toThrow();
    await screen.findByRole("heading", { name: /Fleet overview/i });
    expect(screen.getByTestId("start-demo-button")).toBeInTheDocument();
  });

  it("App renders without crash when operatorWorklist is a direct array", async () => {
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": runWithWorklistAsDirectArray }));
    expect(() => render(<App />)).not.toThrow();
    await screen.findByRole("heading", { name: /Fleet overview/i });
    expect(screen.getByTestId("start-demo-button")).toBeInTheDocument();
  });

  it("App renders without crash when operatorWorklist is null", async () => {
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": runWithWorklistNull }));
    expect(() => render(<App />)).not.toThrow();
    await screen.findByRole("heading", { name: /Fleet overview/i });
    expect(screen.getByTestId("start-demo-button")).toBeInTheDocument();
  });

  it("App renders without crash when operatorWorklist is undefined", async () => {
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": runWithWorklistUndefined }));
    expect(() => render(<App />)).not.toThrow();
    await screen.findByRole("heading", { name: /Fleet overview/i });
    expect(screen.getByTestId("start-demo-button")).toBeInTheDocument();
  });

  it("DemoShell opens successfully with object-style operatorWorklist", async () => {
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": runWithWorklistAsObjectWithItems }));
    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });
    const startDemoButton = screen.getByTestId("start-demo-button");
    fireEvent.click(startDemoButton);
    expect(screen.getByTestId("demo-shell")).toBeInTheDocument();
  });

  it("No fake findings are created from invalid operatorWorklist shape", async () => {
    vi.stubGlobal("fetch", createFetchMock({ ...defaultPayloads, "/api/run": runWithWorklistAsUnrelatedObject }));
    render(<App />);
    await screen.findByRole("heading", { name: /Fleet overview/i });
    const startDemoButton = screen.getByTestId("start-demo-button");
    fireEvent.click(startDemoButton);
    const demoShell = await screen.findByTestId("demo-shell");
    expect(demoShell.textContent).toMatch(/No fake incidents/i);
  });
});
