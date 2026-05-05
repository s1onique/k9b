import type { LLMPolicy } from "../types";

export const LLMPolicyPanel = ({ policy }: { policy?: LLMPolicy | null }) => {
  const auto = policy?.autoDrilldown;
  const budgetStatus = auto
    ? auto.budgetExhausted === null
      ? "Budget status unknown"
      : auto.budgetExhausted
      ? "Budget exhausted"
      : "Within budget"
    : "Budget status unknown";
  const statusModifier = auto?.enabled ? "status-pill-healthy" : "status-pill-pending";
  return (
    <section className="panel llm-policy-panel" id="llm-policy">
      <div className="section-head">
        <div>
          <h2>LLM policy</h2>
          <p className="muted small">Auto drilldown policy and current usage.</p>
        </div>
        {auto ? (
          <span className={`status-pill ${statusModifier}`}>
            Auto drilldown {auto.enabled ? "enabled" : "disabled"}
          </span>
        ) : null}
      </div>
      {auto ? (
        <div className="llm-policy-grid">
          <div>
            <p className="tiny">Provider</p>
            <strong>{auto.provider || "default"}</strong>
          </div>
          <div>
            <p className="tiny">Budget</p>
            <strong>{auto.maxPerRun} per run</strong>
          </div>
          <div>
            <p className="tiny">Used this run</p>
            <strong>{auto.usedThisRun}</strong>
          </div>
          <div>
            <p className="tiny">Success / Failed / Skipped</p>
            <strong>
              {auto.successfulThisRun} / {auto.failedThisRun} / {auto.skippedThisRun}
            </strong>
          </div>
          <div>
            <p className="tiny">Budget status</p>
            <strong>{budgetStatus}</strong>
          </div>
        </div>
      ) : (
        <p className="muted small">LLM policy data is unavailable.</p>
      )}
    </section>
  );
};