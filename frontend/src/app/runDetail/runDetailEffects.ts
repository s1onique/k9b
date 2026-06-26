/**
 * runDetailEffects.ts - Effect handlers for Run Detail UI state.
 *
 * Contains the side-effect logic (API calls, downloads) that is executed
 * outside the pure update function.
 *
 * Each effect handler dispatches a message back to the reducer when complete.
 *
 * @module app/runDetail/runDetailEffects
 */
import type { Cmd, Msg } from "./runDetailModel";
import { fetchDebugDiagnosticsEnabled, downloadExecutionStateDiagnostics } from "../../api";

/**
 * Effect handler context - provides dispatch function for sending messages.
 */
export interface EffectContext {
  dispatch: (msg: Msg) => void;
}

/**
 * Executes a single command effect.
 *
 * @param cmd - The command to execute
 * @param context - The effect context (provides dispatch)
 */
export function executeEffect(cmd: Cmd, context: EffectContext): void {
  const { dispatch } = context;

  switch (cmd.type) {
    case "CheckDebugDiagnosticsEnabled": {
      fetchDebugDiagnosticsEnabled()
        .then((response) => {
          // Defensive: treat undefined/null/malformed response as disabled
          dispatch({
            type: "DebugDiagnosticsEnabled",
            enabled: response?.debugExecutionDiagnosticsEnabled === true,
          });
        })
        .catch(() => {
          // Silently disable if fetch fails (e.g., endpoint not available)
          dispatch({
            type: "DebugDiagnosticsEnabled",
            enabled: false,
          });
        });
      break;
    }

    case "DownloadDiagnostics": {
      const { runId } = cmd;

      dispatch({ type: "DiagnosticsDownloadStarted" });

      downloadExecutionStateDiagnostics(runId)
        .then((blob) => {
          // Create download link
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = `k9b-execution-state-diagnostics-${runId}.zip`;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          URL.revokeObjectURL(url);

          dispatch({ type: "DiagnosticsDownloadSucceeded" });
        })
        .catch((err) => {
          // Preserve backend error message so operators see "Debug endpoints disabled" etc.
          const errorMessage = err instanceof Error ? err.message : String(err);
          dispatch({
            type: "DiagnosticsDownloadFailed",
            error: errorMessage || "Failed to download diagnostics bundle",
          });
        });
      break;
    }

    case "NoOp": {
      // No-op - do nothing
      break;
    }
  }
}

/**
 * Drain all pending effects from a queue.
 *
 * @param effects - Array of effects to execute
 * @param context - The effect context
 */
export function drainEffects(effects: Cmd[], context: EffectContext): void {
  for (const effect of effects) {
    executeEffect(effect, context);
  }
}
