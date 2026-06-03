/**
 * React hook adapter for DemoShell Elm-ish model.
 *
 * Wraps the pure model/update functions with React's useReducer.
 * All hooks are unconditional and the state machine is fully testable.
 */

import { useCallback, useReducer } from "react";
import {
  initDemoShellState,
  updateDemoShell,
  type DemoShellMsg,
  type DemoShellState,
} from "./demoShellModel";

/**
 * Return type for the useDemoShellModel hook
 */
export interface UseDemoShellModelReturn {
  state: DemoShellState;
  openDemo: () => void;
  closeDemo: () => void;
}

/**
 * React hook for DemoShell state management.
 *
 * Provides a clean seam between React and the pure Elm-ish model.
 * All hooks run unconditionally before any render.
 */
export function useDemoShellModel(): UseDemoShellModelReturn {
  const [state, dispatch] = useReducer(
    updateDemoShell,
    undefined,
    initDemoShellState,
  );

  const openDemo = useCallback(() => {
    dispatch({ type: "open" });
  }, []);

  const closeDemo = useCallback(() => {
    dispatch({ type: "close" });
  }, []);

  return {
    state,
    openDemo,
    closeDemo,
  };
}