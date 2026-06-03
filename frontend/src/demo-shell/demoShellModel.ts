/**
 * Pure Elm-ish model for DemoShell state management.
 *
 * This module contains no React dependencies - just pure state and transition logic.
 * The model is deterministic and testable without React rendering.
 */

/**
 * DemoShell state shape
 */
export type DemoShellState = {
  isOpen: boolean;
};

/**
 * Messages (actions) that can update DemoShell state
 */
export type DemoShellMsg =
  | { type: "open" }
  | { type: "close" };

/**
 * Initialize default DemoShell state
 */
export function initDemoShellState(): DemoShellState {
  return { isOpen: false };
}

/**
 * Exhaustive check helper - ensures all union cases are handled
 */
function assertNever(value: never): never {
  throw new Error(`Unhandled DemoShell message: ${JSON.stringify(value)}`);
}

/**
 * Pure state transition function
 * Given current state and a message, returns the next state
 */
export function updateDemoShell(
  state: DemoShellState,
  msg: DemoShellMsg,
): DemoShellState {
  switch (msg.type) {
    case "open":
      return { ...state, isOpen: true };
    case "close":
      return { ...state, isOpen: false };
    default:
      return assertNever(msg);
  }
}
