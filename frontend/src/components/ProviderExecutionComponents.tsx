/**
 * Provider Execution Panel Components
 *
 * Renders provider-assisted execution branch data in compact format.
 * Includes ExecutionLine for individual branches and ProviderExecutionPanel as container.
 */

import React from "react";
import type { ProviderExecution, ProviderExecutionBranch } from "../types";

/** Single execution line for a branch */
export const ExecutionLine: React.FC<{
  title: string;
  data: ProviderExecutionBranch | undefined | null;
}> = ({ title, data }) => {
  if (!data) {
    return (
      <div className="provider-execution-line">
        <strong>{title}</strong>
        <p className="small muted">Execution data unavailable for this branch.</p>
      </div>
    );
  }
  const segments = [
    data.eligible != null && `eligible ${data.eligible}`,
    `attempted ${data.attempted}`,
    `ok ${data.succeeded}`,
    `failed ${data.failed}`,
    `skipped ${data.skipped}`,
    data.unattempted != null && `unattempted ${data.unattempted}`,
    data.budgetLimited != null && data.budgetLimited > 0 && `budget-limited ${data.budgetLimited}`,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <div className="provider-execution-line">
      <strong>{title}</strong>
      <p className="muted tiny provider-execution-summary">{segments || "No counts yet."}</p>
      {data.notes ? <p className="muted tiny provider-execution-note">{data.notes}</p> : null}
    </div>
  );
};

/** Provider execution panel - container for auto drilldown and review enrichment branches */
export const ProviderExecutionPanel: React.FC<{
  execution: ProviderExecution | undefined | null;
}> = ({ execution }) => (
  <section className="panel provider-execution" id="provider-execution">
    <div className="section-head">
      <h2>Provider branches</h2>
      <p className="muted small">
        Counts derived from deterministic artifacts and run-config provenance for each branch.
      </p>
    </div>
    <div className="provider-execution-body">
      <ExecutionLine title="Auto drilldown" data={execution?.autoDrilldown} />
      <ExecutionLine title="Review enrichment" data={execution?.reviewEnrichment} />
    </div>
  </section>
);

export default { ExecutionLine, ProviderExecutionPanel };