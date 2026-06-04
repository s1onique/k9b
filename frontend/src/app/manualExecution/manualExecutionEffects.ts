/**
 * manualExecutionEffects.ts - Effect runner for manual execution commands.
 *
 * Contains async side effects that cannot be in the pure update() function.
 * These effects dispatch results back to the reducer.
 *
 * @module app/manualExecution/manualExecutionEffects
 */
import type { Cmd, Msg } from "./manualExecutionModel";
import { executeNextCheckCandidate } from "../../api";

/**
 * Effect runner that executes a command and dispatches results.
 *
 * @param cmd - The command to execute
 * @param dispatch - Callback to dispatch messages back to the reducer
 */
export async function runEffect(cmd: Cmd, dispatch: (msg: Msg) => void): Promise<void> {
  switch (cmd.type) {
    case "ExecuteCandidate": {
      const { candidateKey, request } = cmd;
      try {
        const result = await executeNextCheckCandidate(request);
        dispatch({ type: "ExecutionSucceeded", candidateKey, result });
      } catch (err) {
        const message = err instanceof Error ? err.message : "Manual execution failed";
        const blockingReason =
          err instanceof Error && "blockingReason" in err
            ? (err as Error & { blockingReason?: string | null }).blockingReason
            : undefined;
        dispatch({
          type: "ExecutionFailed",
          candidateKey,
          error: { status: "error", summary: message, blockingReason: blockingReason ?? null },
        });
      }
      break;
    }
    case "HighlightCandidate": {
      // Highlight is handled by the hook directly, but we keep this for completeness
      break;
    }
    case "NoOp": {
      // No-op, nothing to do
      break;
    }
  }
}

/**
 * Execute highlight side effect.
 *
 * @param key - Candidate key to highlight
 * @param highlightQueueCard - The actual highlight function from React context
 */
export function runHighlightEffect(key: string, highlightQueueCard: (key: string) => void): void {
  requestAnimationFrame(() => {
    highlightQueueCard(key);
  });
}