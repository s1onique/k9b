/**
 * AppNavigation Component
 *
 * Navigation bar for the K8s Operator Advisor application.
 * Redesigned to prioritize incidents as the primary operational object.
 * Extracted from App.tsx to reduce component size.
 */

import type { Run } from "../types";

export interface AppNavigationProps {
  run: Run | null | undefined;
}

export function AppNavigation({ run }: AppNavigationProps) {
  return (
    <nav className="cockpit-nav" aria-label="Fleet cockpit sections">
      {/* Incident-first navigation - primary operational object */}
      <a className="cockpit-nav__item" href="#incident-list">Incidents</a>
      <a className="cockpit-nav__item" href="#recent-runs">Recent runs</a>
      <a className="cockpit-nav__item" href="#run-detail">Run summary</a>
      <a className="cockpit-nav__item" href="#review-enrichment">Provider advisory</a>
      <a className="cockpit-nav__item" href="#provider-execution">Provider branches</a>
      <a className="cockpit-nav__item" href="#diagnostic-pack-download">Diagnostic package</a>
      {run?.diagnosticPackReview && (
        <a className="cockpit-nav__item" href="#diagnostic-pack-review">Diagnostic pack review</a>
      )}
      <a className="cockpit-nav__item" href="#deterministic-next-checks">Deterministic checks</a>
      <a className="cockpit-nav__item" href="#execution-history">Execution review</a>
      <a className="cockpit-nav__item" href="#next-check-queue">Work list</a>
      <a className="cockpit-nav__item" href="#fleet">Fleet overview</a>
      <a className="cockpit-nav__item" href="#cluster">Cluster detail</a>
      <a className="cockpit-nav__item" href="#proposals">Action proposals</a>
      <a className="cockpit-nav__item" href="#notifications">Notifications</a>
      <a className="cockpit-nav__item" href="#llm-policy">LLM policy</a>
      <a className="cockpit-nav__item" href="#llm-activity">LLM activity</a>
    </nav>
  );
}
