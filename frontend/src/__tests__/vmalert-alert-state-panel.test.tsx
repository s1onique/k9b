import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { VmalertAlertStatePanel } from "../components/VmalertAlertStatePanel";
import type { VmalertRuleState, VmalertRuleStateAlert } from "../types/vmalert";

// Re-export types for test file access
export type { VmalertRuleState, VmalertRuleStateAlert };

// Fixture builders aligned with backend VmalertRuleStatePayload contract
const makeVmalertRuleStateAlert = (overrides: Partial<VmalertRuleStateAlert> = {}): VmalertRuleStateAlert => ({
  alertname: "TestAlert",
  state: "firing",
  severity: "warning",
  cluster_label: null,
  namespace: null,
  workload: null,
  pod: null,
  instance: null,
  summary: null,
  description: null,
  active_at: null,
  starts_at: null,
  source_endpoint: null,
  group_name: null,
  rule_name: null,
  ...overrides,
});

const makeVmalertRuleState = (overrides: Partial<VmalertRuleState> = {}): VmalertRuleState => ({
  source_count: 0,
  fetched_source_count: 0,
  failed_source_count: 0,
  alert_count: 0,
  firing_alert_count: 0,
  pending_alert_count: 0,
  critical_firing_count: 0,
  rule_group_count: 0,
  fetch_error_count: 0,
  captured_at: "2026-05-13T12:00:00Z",
  alerts: [],
  rule_groups: [],
  fetch_errors: [],
  ...overrides,
});

describe("VmalertAlertStatePanel", () => {
  // Reset document theme before each test to ensure consistent CSS
  beforeEach(() => {
    document.documentElement.setAttribute("data-theme", "dark");
  });

  afterEach(() => {
    document.documentElement.removeAttribute("data-theme");
  });

  describe("Null-state behavior", () => {
    it("renders nothing when vmalertRuleState is null", () => {
      render(<VmalertAlertStatePanel vmalertRuleState={null} />);
      expect(screen.queryByText(/vmalert/i)).not.toBeInTheDocument();
    });

    it("renders nothing when vmalertRuleState is undefined", () => {
      render(<VmalertAlertStatePanel vmalertRuleState={undefined} />);
      expect(screen.queryByText(/vmalert/i)).not.toBeInTheDocument();
    });
  });

  describe("No data collected - quiet state", () => {
    it("shows no-data message when no sources fetched and no errors", () => {
      const state = makeVmalertRuleState({
        source_count: 0,
        fetched_source_count: 0,
        failed_source_count: 0,
        fetch_error_count: 0,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByText(/No vmalert alert state collected for this run/i)).toBeInTheDocument();
    });

    it("does NOT show an error when no data is collected", () => {
      const state = makeVmalertRuleState({
        source_count: 0,
        fetched_source_count: 0,
        failed_source_count: 0,
        fetch_error_count: 0,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      // No error pill, no warning indicator
      expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/⚠/)).not.toBeInTheDocument();
    });
  });

  describe("Zero alerts - healthy state", () => {
    it("renders 'No active vmalert alerts' when alert_count is 0 and sources fetched", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 0,
        firing_alert_count: 0,
        pending_alert_count: 0,
        critical_firing_count: 0,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByText("No active vmalert alerts")).toBeInTheDocument();
    });

    it("shows 'OK' status pill when no alerts and sources fetched", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 0,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByText(/OK/i)).toBeInTheDocument();
    });

    it("shows source summary when no alerts", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 0,
        firing_alert_count: 0,
        pending_alert_count: 0,
        critical_firing_count: 0,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByText(/Fetched from 1 source/i)).toBeInTheDocument();
    });
  });

  describe("Firing alerts - active state", () => {
    it("shows firing alert count", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 3,
        firing_alert_count: 2,
        pending_alert_count: 1,
        alerts: [
          makeVmalertRuleStateAlert({ alertname: "Alert1", state: "firing", severity: "warning" }),
          makeVmalertRuleStateAlert({ alertname: "Alert2", state: "firing", severity: "warning" }),
          makeVmalertRuleStateAlert({ alertname: "Alert3", state: "pending", severity: "info" }),
        ],
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      // Text is split across elements: <strong>3</strong> + " active alert" + "s"
      // Check the strong element with count
      expect(screen.getByText("3", { selector: ".vmalert-alert-state-summary strong" })).toBeInTheDocument();
      // Also verify the active alerts summary line is present
      expect(screen.getByText(/active alert/i)).toBeInTheDocument();
      // And the source breakdown
      expect(screen.getByText(/1 source/i)).toBeInTheDocument();
      expect(screen.getByText(/2 firing/i)).toBeInTheDocument();
      expect(screen.getByText(/1 pending/i)).toBeInTheDocument();
    });

    it("shows firing count in summary", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 2,
        firing_alert_count: 2,
        pending_alert_count: 0,
        alerts: [
          makeVmalertRuleStateAlert({ alertname: "Alert1", state: "firing", severity: "warning" }),
          makeVmalertRuleStateAlert({ alertname: "Alert2", state: "firing", severity: "warning" }),
        ],
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByText(/2 firing/i)).toBeInTheDocument();
    });

    it("shows pending count when alerts pending", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 2,
        firing_alert_count: 1,
        pending_alert_count: 1,
        alerts: [
          makeVmalertRuleStateAlert({ alertname: "Alert1", state: "firing", severity: "warning" }),
          makeVmalertRuleStateAlert({ alertname: "Alert2", state: "pending", severity: "info" }),
        ],
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByText(/1 pending/i)).toBeInTheDocument();
    });
  });

  describe("Critical firing alerts - prominent display", () => {
    it("shows critical count in status pill when critical firing alerts exist", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 2,
        firing_alert_count: 2,
        pending_alert_count: 0,
        critical_firing_count: 1,
        alerts: [
          makeVmalertRuleStateAlert({
            alertname: "CriticalAlert",
            state: "firing",
            severity: "critical",
            namespace: "monitoring",
          }),
          makeVmalertRuleStateAlert({
            alertname: "WarningAlert",
            state: "firing",
            severity: "warning",
            namespace: "default",
          }),
        ],
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      // Use exact text match with selector for status pill
      expect(screen.getByText("1 critical", { selector: ".status-pill" })).toBeInTheDocument();
    });

    it("shows worklist promotion note when critical firing alerts exist", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 1,
        firing_alert_count: 1,
        pending_alert_count: 0,
        critical_firing_count: 1,
        alerts: [
          makeVmalertRuleStateAlert({
            alertname: "CriticalAlert",
            state: "firing",
            severity: "critical",
          }),
        ],
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByText(/Only critical firing alerts are promoted to the operator worklist/i)).toBeInTheDocument();
    });

    it("shows correct row class for critical firing alert", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 1,
        firing_alert_count: 1,
        critical_firing_count: 1,
        alerts: [
          makeVmalertRuleStateAlert({
            alertname: "CriticalAlert",
            state: "firing",
            severity: "critical",
          }),
        ],
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      const row = screen.getByText("CriticalAlert").closest("tr");
      expect(row).toHaveClass("vmalert-alert-row--critical");
    });
  });

  describe("Fetch errors - non-fatal warning", () => {
    it("shows warning when fetch_error_count > 0", () => {
      const state = makeVmalertRuleState({
        source_count: 2,
        fetched_source_count: 1,
        failed_source_count: 1,
        fetch_error_count: 1,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByText(/⚠/)).toBeInTheDocument();
    });

    it("shows 'Partial' status pill when fetch errors exist", () => {
      const state = makeVmalertRuleState({
        source_count: 2,
        fetched_source_count: 1,
        failed_source_count: 1,
        fetch_error_count: 1,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByText(/Partial/i)).toBeInTheDocument();
    });

    it("shows clear message about failed sources", () => {
      const state = makeVmalertRuleState({
        source_count: 2,
        fetched_source_count: 1,
        failed_source_count: 1,
        fetch_error_count: 1,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByText(/Could not fetch from 1 vmalert source/i)).toBeInTheDocument();
    });

    it("shows 'non-fatal' note in error message", () => {
      const state = makeVmalertRuleState({
        source_count: 2,
        fetched_source_count: 1,
        failed_source_count: 1,
        fetch_error_count: 1,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByText(/This is non-fatal/i)).toBeInTheDocument();
    });
  });

  describe("Alert list display", () => {
    it("shows alert name in table", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 1,
        firing_alert_count: 1,
        alerts: [
          makeVmalertRuleStateAlert({ alertname: "PodNotReady", state: "firing", severity: "warning" }),
        ],
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByText("PodNotReady")).toBeInTheDocument();
    });

    it("shows severity badge", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 1,
        firing_alert_count: 1,
        alerts: [
          makeVmalertRuleStateAlert({ alertname: "TestAlert", state: "firing", severity: "warning" }),
        ],
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByText(/warning/i)).toBeInTheDocument();
    });

    it("shows state badge", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 1,
        firing_alert_count: 1,
        alerts: [
          makeVmalertRuleStateAlert({ alertname: "TestAlert", state: "firing", severity: "warning" }),
        ],
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      // Check for state badge specifically (has specific class)
      expect(screen.getByText("firing", { selector: ".vmalert-alert-state-badge" })).toBeInTheDocument();
    });

    it("shows namespace when present", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 1,
        firing_alert_count: 1,
        alerts: [
          makeVmalertRuleStateAlert({
            alertname: "TestAlert",
            state: "firing",
            severity: "warning",
            namespace: "monitoring",
          }),
        ],
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByText("monitoring")).toBeInTheDocument();
    });

    it("shows workload when present", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 1,
        firing_alert_count: 1,
        alerts: [
          makeVmalertRuleStateAlert({
            alertname: "TestAlert",
            state: "firing",
            severity: "warning",
            namespace: "monitoring",
            workload: "prometheus-0",
          }),
        ],
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByText("prometheus-0")).toBeInTheDocument();
    });

    it("shows pod when workload not present", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 1,
        firing_alert_count: 1,
        alerts: [
          makeVmalertRuleStateAlert({
            alertname: "TestAlert",
            state: "firing",
            severity: "warning",
            namespace: "monitoring",
            workload: null,
            pod: "alertmanager-0",
          }),
        ],
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByText("alertmanager-0")).toBeInTheDocument();
    });

    it("shows dash for missing namespace", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 1,
        firing_alert_count: 1,
        alerts: [
          makeVmalertRuleStateAlert({
            alertname: "TestAlert",
            state: "firing",
            severity: "warning",
            namespace: null,
            workload: null,
            pod: null,
          }),
        ],
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      // Use getAllByText since both namespace and workload cells show "—" for missing values
      expect(screen.getAllByText("—")).toHaveLength(2);
    });
  });

  describe("Alert sorting - priority order", () => {
    it("sorts critical firing alerts first", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 3,
        firing_alert_count: 3,
        pending_alert_count: 0,
        critical_firing_count: 1,
        alerts: [
          makeVmalertRuleStateAlert({ alertname: "WarningAlert", state: "firing", severity: "warning" }),
          makeVmalertRuleStateAlert({ alertname: "CriticalAlert", state: "firing", severity: "critical" }),
          makeVmalertRuleStateAlert({ alertname: "InfoAlert", state: "firing", severity: "info" }),
        ],
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      const rows = screen.getAllByRole("row");
      // Header row is first, then data rows
      const alertRows = rows.slice(1);
      // Critical should be first
      expect(alertRows[0].textContent).toContain("CriticalAlert");
    });

    it("sorts pending alerts after firing alerts", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 2,
        firing_alert_count: 1,
        pending_alert_count: 1,
        alerts: [
          makeVmalertRuleStateAlert({ alertname: "PendingAlert", state: "pending", severity: "warning" }),
          makeVmalertRuleStateAlert({ alertname: "FiringAlert", state: "firing", severity: "warning" }),
        ],
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      const rows = screen.getAllByRole("row");
      const alertRows = rows.slice(1);
      // Firing should be first
      expect(alertRows[0].textContent).toContain("FiringAlert");
    });
  });

  describe("Alert pagination", () => {
    it("shows 10 alerts per page when more than 10 alerts exist", () => {
      // Create 15 alerts with unique names
      const alerts: VmalertRuleStateAlert[] = [];
      for (let i = 0; i < 15; i++) {
        alerts.push(makeVmalertRuleStateAlert({
          alertname: `PageTestAlert${i}`,
          state: "firing",
          severity: "warning",
        }));
      }
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 15,
        firing_alert_count: 15,
        alerts,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      // Should show 10 rows (header + 10 data rows)
      const rows = screen.getAllByRole("row");
      const alertRows = rows.slice(1); // Skip header
      expect(alertRows).toHaveLength(10);
    });

    it("shows pagination controls when more than 10 alerts", () => {
      const alerts: VmalertRuleStateAlert[] = [];
      for (let i = 0; i < 15; i++) {
        alerts.push(makeVmalertRuleStateAlert({
          alertname: `Alert${i}`,
          state: "firing",
          severity: "warning",
        }));
      }
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 15,
        firing_alert_count: 15,
        alerts,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      // Should show pagination navigation
      expect(screen.getByRole("navigation", { name: /alerts pagination/i })).toBeInTheDocument();
      // Should show pagination summary with correct total count
      const paginationSummary = document.querySelector('.pagination-summary');
      expect(paginationSummary).not.toBeNull();
      expect(paginationSummary?.textContent).toContain('15');
      // Check page indicator using textContent on the page indicator element
      const pageIndicator = document.querySelector('.pagination-page-indicator');
      expect(pageIndicator).not.toBeNull();
      expect(pageIndicator?.textContent).toContain('1');
      expect(pageIndicator?.textContent).toContain('2');
    });

    it("Next button is present and enabled on first page", () => {
      const alerts: VmalertRuleStateAlert[] = [];
      for (let i = 0; i < 15; i++) {
        alerts.push(makeVmalertRuleStateAlert({
          alertname: `NextTest${i}`,
          state: "firing",
          severity: "warning",
        }));
      }
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 15,
        firing_alert_count: 15,
        alerts,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      const nextButton = screen.getByRole("button", { name: /next page/i });
      expect(nextButton).not.toBeDisabled();
    });

    it("Previous button is disabled on first page", () => {
      const alerts: VmalertRuleStateAlert[] = [];
      for (let i = 0; i < 15; i++) {
        alerts.push(makeVmalertRuleStateAlert({
          alertname: `DisabledTest${i}`,
          state: "firing",
          severity: "warning",
        }));
      }
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 15,
        firing_alert_count: 15,
        alerts,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      const prevButton = screen.getByRole("button", { name: /previous page/i });
      expect(prevButton).toBeDisabled();
    });

    it("clicking Next navigates to page 2 and Previous returns to page 1", async () => {
      const alerts: VmalertRuleStateAlert[] = [];
      for (let i = 0; i < 15; i++) {
        alerts.push(makeVmalertRuleStateAlert({
          alertname: `PageNav${i}`,
          state: "firing",
          severity: "warning",
        }));
      }
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 15,
        firing_alert_count: 15,
        alerts,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      // Page 1: should show 10 rows
      const rowsOnPage1 = screen.getAllByRole("row").slice(1);
      expect(rowsOnPage1).toHaveLength(10);
      // Page indicator shows Page 1 of 2
      const pageIndicator1 = document.querySelector('.pagination-page-indicator');
      expect(pageIndicator1?.textContent).toContain('1');
      expect(pageIndicator1?.textContent).toContain('2');

      // Click Next to go to page 2
      const nextButton = screen.getByRole("button", { name: /next page/i });
      await act(async () => {
        await userEvent.click(nextButton);
      });

      // Page 2: should show 5 rows
      const rowsOnPage2 = screen.getAllByRole("row").slice(1);
      expect(rowsOnPage2).toHaveLength(5);
      // Page indicator shows Page 2 of 2
      const pageIndicator2 = document.querySelector('.pagination-page-indicator');
      expect(pageIndicator2?.textContent).toContain('2');

      // Click Previous to return to page 1
      const prevButton = screen.getByRole("button", { name: /previous page/i });
      await act(async () => {
        await userEvent.click(prevButton);
      });

      // Back on page 1: should show 10 rows again
      const rowsOnPage1Back = screen.getAllByRole("row").slice(1);
      expect(rowsOnPage1Back).toHaveLength(10);
    });

    it("hides pagination controls when alert_count <= 10", () => {
      const alerts: VmalertRuleStateAlert[] = [];
      for (let i = 0; i < 5; i++) {
        alerts.push(makeVmalertRuleStateAlert({
          alertname: `Small${i}`,
          state: "firing",
          severity: "warning",
        }));
      }
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 5,
        firing_alert_count: 5,
        alerts,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      // Should not show pagination controls
      expect(screen.queryByRole("navigation", { name: /alerts pagination/i })).not.toBeInTheDocument();
    });

    it("does not show pagination when exactly 10 alerts", () => {
      const alerts: VmalertRuleStateAlert[] = [];
      for (let i = 0; i < 10; i++) {
        alerts.push(makeVmalertRuleStateAlert({
          alertname: `ExactTen${i}`,
          state: "firing",
          severity: "warning",
        }));
      }
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 10,
        firing_alert_count: 10,
        alerts,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      // Should not show pagination controls (only 1 page)
      expect(screen.queryByRole("navigation", { name: /alerts pagination/i })).not.toBeInTheDocument();
    });

    it("preserves sort order across pages", () => {
      const alerts: VmalertRuleStateAlert[] = [
        // Critical firing first (page 1)
        makeVmalertRuleStateAlert({
          alertname: "CriticalAlpha",
          state: "firing",
          severity: "critical",
        }),
        makeVmalertRuleStateAlert({
          alertname: "CriticalBeta",
          state: "firing",
          severity: "critical",
        }),
        // Other firing (page 1 - fills to 10)
        makeVmalertRuleStateAlert({
          alertname: "WarningAlpha",
          state: "firing",
          severity: "warning",
        }),
        makeVmalertRuleStateAlert({
          alertname: "WarningBeta",
          state: "firing",
          severity: "warning",
        }),
        makeVmalertRuleStateAlert({
          alertname: "WarningGamma",
          state: "firing",
          severity: "warning",
        }),
        makeVmalertRuleStateAlert({
          alertname: "WarningDelta",
          state: "firing",
          severity: "warning",
        }),
        makeVmalertRuleStateAlert({
          alertname: "WarningEpsilon",
          state: "firing",
          severity: "warning",
        }),
        makeVmalertRuleStateAlert({
          alertname: "WarningZeta",
          state: "firing",
          severity: "warning",
        }),
        makeVmalertRuleStateAlert({
          alertname: "WarningEta",
          state: "firing",
          severity: "warning",
        }),
        makeVmalertRuleStateAlert({
          alertname: "WarningTheta",
          state: "firing",
          severity: "warning",
        }),
        // Pending alerts (page 2)
        makeVmalertRuleStateAlert({
          alertname: "PendingAlpha",
          state: "pending",
          severity: "warning",
        }),
        makeVmalertRuleStateAlert({
          alertname: "PendingBeta",
          state: "pending",
          severity: "info",
        }),
      ];
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 12,
        firing_alert_count: 10,
        pending_alert_count: 2,
        alerts,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      // Page 1 should show 10 rows
      const rowsOnPage1 = screen.getAllByRole("row");
      const alertRowsOnPage1 = rowsOnPage1.slice(1);
      expect(alertRowsOnPage1).toHaveLength(10);
      // Critical should be first
      expect(alertRowsOnPage1[0].textContent).toContain("CriticalAlpha");
      expect(alertRowsOnPage1[1].textContent).toContain("CriticalBeta");
    });
  });

  describe("Section heading and structure", () => {
    it("renders with correct section heading", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 0,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(screen.getByRole("heading", { name: /vmalert alert state/i })).toBeInTheDocument();
    });

    it("renders with correct section id for navigation", () => {
      const state = makeVmalertRuleState({
        source_count: 1,
        fetched_source_count: 1,
        alert_count: 0,
      });
      render(<VmalertAlertStatePanel vmalertRuleState={state} />);

      expect(document.getElementById("vmalert-alert-state")).toBeInTheDocument();
    });
  });
});
