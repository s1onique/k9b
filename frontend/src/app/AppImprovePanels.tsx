/**
 * AppImprovePanels Component
 *
 * Grouped panels for the "Improve" workflow lane.
 * Extracted from App.tsx to reduce component size.
 */

import type { Run } from "../types";
import { LLMPolicyPanel } from "../components/LLMPolicyPanel";
import { LLMActivityPanel } from "../components/LLMActivityPanel";
import { NotificationHistoryTable } from "../components/NotificationHistoryTable";

export interface AppImprovePanelsProps {
  run: Run | null | undefined;
}

export function AppImprovePanels({ run }: AppImprovePanelsProps) {
  return (
    <>
      <section className="panel" id="notifications">
        <div className="section-head">
          <h2>Notification history</h2>
          <p className="small">Filtering applies to the entire retained archive.</p>
        </div>
        <NotificationHistoryTable />
      </section>
      {run ? (
        <LLMPolicyPanel policy={run.llmPolicy} />
      ) : (
        <section className="panel llm-policy-panel" id="llm-policy">
          <div className="section-head">
            <h2>LLM policy</h2>
            <p className="muted">Loading selected run…</p>
          </div>
        </section>
      )}
      {run ? (
        <LLMActivityPanel activity={run.llmActivity} />
      ) : (
        <section className="panel llm-activity-panel" id="llm-activity">
          <div className="section-head">
            <h2>LLM activity</h2>
            <p className="muted">Loading selected run…</p>
          </div>
        </section>
      )}
    </>
  );
}