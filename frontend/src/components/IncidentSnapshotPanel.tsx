/**
 * IncidentSnapshotPanel Component
 *
 * Minimal UI trigger for incident snapshot capture.
 * Allows operators to capture namespace evidence bundles without CLI commands.
 */

import { useState, useCallback } from "react";
import type { IncidentSnapshotResponse } from "../api";
import { captureIncidentSnapshot } from "../api";

export interface IncidentSnapshotPanelProps {
  /** Current namespace (reused from cluster context) */
  namespace: string | null;
  /** Default namespace when none provided */
  defaultNamespace?: string;
}

interface SnapshotState {
  status: "idle" | "capturing" | "success" | "error";
  result: IncidentSnapshotResponse | null;
  error: string | null;
}

export const IncidentSnapshotPanel: React.FC<IncidentSnapshotPanelProps> = ({
  namespace,
  defaultNamespace = "default",
}) => {
  const [state, setState] = useState<SnapshotState>({
    status: "idle",
    result: null,
    error: null,
  });
  const [inputNamespace, setInputNamespace] = useState(
    namespace ?? defaultNamespace
  );

  const handleCapture = useCallback(async () => {
    const targetNamespace = namespace ?? inputNamespace;
    if (!targetNamespace.trim()) {
      setState({
        status: "error",
        result: null,
        error: "Namespace is required",
      });
      return;
    }

    setState({ status: "capturing", result: null, error: null });

    try {
      const result = await captureIncidentSnapshot({
        namespace: targetNamespace,
        since_hours: 2,
      });

      // If backend returns an error in response body
      if (result.error) {
        setState({
          status: "error",
          result,
          error: result.error,
        });
      } else {
        setState({
          status: "success",
          result,
          error: null,
        });
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to capture snapshot";
      setState({
        status: "error",
        result: null,
        error: message,
      });
    }
  }, [namespace, inputNamespace]);

  const handleCopyBundle = useCallback(() => {
    if (state.result?.bundle) {
      const json = JSON.stringify(state.result.bundle, null, 2);
      navigator.clipboard.writeText(json).catch(() => {
        // Fallback: create textarea and select
        const textarea = document.createElement("textarea");
        textarea.value = json;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      });
    }
  }, [state.result?.bundle]);

  const handleDownloadBundle = useCallback(() => {
    if (state.result?.bundle) {
      const json = JSON.stringify(state.result.bundle, null, 2);
      const blob = new Blob([json], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `incident-bundle-${state.result.bundle_id}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  }, [state.result?.bundle, state.result?.bundle_id]);

  const handleReset = useCallback(() => {
    setState({ status: "idle", result: null, error: null });
  }, []);

  const targetNamespace = namespace ?? inputNamespace;
  const showInput = !namespace;

  return (
    <section className="panel" id="incident-snapshot">
      <div className="section-head">
        <h2>Capture incident snapshot</h2>
        <p className="muted small">
          Capture namespace evidence bundle for LLM review
        </p>
      </div>

      {/* Input section */}
      {showInput && state.status === "idle" && (
        <div className="incident-snapshot-input">
          <label>
            Namespace
            <input
              type="text"
              value={inputNamespace}
              onChange={(e) => setInputNamespace(e.target.value)}
              placeholder="e.g., default"
              disabled={state.status === "capturing"}
            />
          </label>
        </div>
      )}

      {/* Capture button */}
      {state.status === "idle" && (
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleCapture}
          disabled={state.status === "capturing"}
        >
          Capture incident bundle
        </button>
      )}

      {/* Loading state */}
      {state.status === "capturing" && (
        <div className="incident-snapshot-loading">
          <p>Capturing incident snapshot for namespace "{targetNamespace}"...</p>
          <p className="muted small">This may take a few seconds</p>
        </div>
      )}

      {/* Success state */}
      {state.status === "success" && state.result && (
        <div className="incident-snapshot-result">
          <div className="incident-snapshot-summary">
            <h3>Bundle captured</h3>
            <dl>
              <dt>Bundle ID</dt>
              <dd>
                <code>{state.result.bundle_id}</code>
              </dd>
              <dt>Namespace</dt>
              <dd>{state.result.namespace}</dd>
              <dt>Captured at</dt>
              <dd>{new Date(state.result.captured_at).toLocaleString()}</dd>
            </dl>
            <h4>Evidence summary</h4>
            <ul className="incident-snapshot-counts">
              <li>
                Total pods:{" "}
                <strong>{state.result.summary.total_pods}</strong>
              </li>
              <li>
                Failing pods:{" "}
                <strong>{state.result.summary.failing_pods_count}</strong>
              </li>
              <li>
                Total deployments:{" "}
                <strong>{state.result.summary.total_deployments}</strong>
              </li>
              <li>
                Total events:{" "}
                <strong>{state.result.summary.total_events}</strong>
              </li>
              <li>
                Symptoms: <strong>{state.result.summary.symptoms_count}</strong>
              </li>
            </ul>
          </div>

          {/* Bundle exposure */}
          <div className="incident-snapshot-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleCopyBundle}
            >
              Copy bundle JSON
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleDownloadBundle}
            >
              Download bundle JSON
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={handleReset}
            >
              New capture
            </button>
          </div>
        </div>
      )}

      {/* Error state */}
      {state.status === "error" && (
        <div className="incident-snapshot-error">
          <h3>Capture failed</h3>
          <p className="error-message">{state.error}</p>
          {state.result && (
            <p className="muted small">
              Bundle ID: {state.result.bundle_id || "—"} | Namespace:{" "}
              {state.result.namespace}
            </p>
          )}
          <button type="button" className="btn btn-ghost" onClick={handleReset}>
            Try again
          </button>
        </div>
      )}
    </section>
  );
};

export default IncidentSnapshotPanel;