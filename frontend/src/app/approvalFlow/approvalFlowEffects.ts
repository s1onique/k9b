/**
 * approvalFlowEffects.ts - Effect runner for approval flow commands.
 *
 * Contains async side effects that cannot be in the pure update() function.
 * These effects dispatch results back to the reducer.
 *
 * @module app/approvalFlow/approvalFlowEffects
 */
import type { Cmd, Msg } from "./approvalFlowModel";
import { approveNextCheckCandidate } from "../../api";

/**
 * Effect runner that executes a command and dispatches results.
 *
 * @param cmd - The command to execute
 * @param dispatch - Callback to dispatch messages back to the reducer
 * @param refresh - Optional refresh callback called after successful approval
 */
export async function runEffect(
  cmd: Cmd,
  dispatch: (msg: Msg) => void,
  refresh?: () => Promise<void>
): Promise<void> {
  switch (cmd.type) {
    case "ApproveCandidate": {
      const { candidateKey, request } = cmd;

      // Step 1: Call approval API
      try {
        const result = await approveNextCheckCandidate(request);
        dispatch({ type: "ApprovalSucceeded", candidateKey, result });
      } catch (err) {
        // Approval failed - dispatch failure and do not refresh
        const message = err instanceof Error ? err.message : "Approval failed";
        dispatch({ type: "ApprovalFailed", candidateKey, summary: message });
        return;
      }

      // Step 2: Refresh after successful approval (separate try/catch)
      if (refresh) {
        try {
          await refresh();
        } catch {
          // Refresh errors are non-fatal after approval succeeds.
          // Do not dispatch anything - the approval already succeeded.
        }
      }

      break;
    }
    case "NoOp": {
      // No-op, nothing to do
      break;
    }
  }
}
