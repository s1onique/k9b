/**
 * Tests for the pure DemoShell Elm-ish model.
 *
 * These tests verify the pure state/update logic without React dependencies.
 */

import { describe, expect, it } from "vitest";
import {
  initDemoShellState,
  updateDemoShell,
  type DemoShellMsg,
  type DemoShellState,
} from "../demoShellModel";

describe("DemoShellModel", () => {
  describe("initDemoShellState", () => {
    it("returns state with isOpen false", () => {
      const state = initDemoShellState();
      expect(state).toEqual({ isOpen: false });
    });
  });

  describe("updateDemoShell", () => {
    it("open message sets isOpen to true", () => {
      const initialState: DemoShellState = { isOpen: false };
      const msg: DemoShellMsg = { type: "open" };
      const nextState = updateDemoShell(initialState, msg);
      expect(nextState).toEqual({ isOpen: true });
    });

    it("close message sets isOpen to false", () => {
      const initialState: DemoShellState = { isOpen: true };
      const msg: DemoShellMsg = { type: "close" };
      const nextState = updateDemoShell(initialState, msg);
      expect(nextState).toEqual({ isOpen: false });
    });

    it("open from open state is idempotent", () => {
      const state: DemoShellState = { isOpen: true };
      const msg: DemoShellMsg = { type: "open" };
      const nextState = updateDemoShell(state, msg);
      expect(nextState).toEqual({ isOpen: true });
    });

    it("close from closed state is idempotent", () => {
      const state: DemoShellState = { isOpen: false };
      const msg: DemoShellMsg = { type: "close" };
      const nextState = updateDemoShell(state, msg);
      expect(nextState).toEqual({ isOpen: false });
    });

    it("repeated open/close is stable", () => {
      let state: DemoShellState = { isOpen: false };

      // Open
      state = updateDemoShell(state, { type: "open" });
      expect(state.isOpen).toBe(true);

      // Close
      state = updateDemoShell(state, { type: "close" });
      expect(state.isOpen).toBe(false);

      // Open again
      state = updateDemoShell(state, { type: "open" });
      expect(state.isOpen).toBe(true);

      // Close again
      state = updateDemoShell(state, { type: "close" });
      expect(state.isOpen).toBe(false);
    });

    it("does not mutate original state", () => {
      const originalState: DemoShellState = { isOpen: true };
      const stateCopy = { ...originalState };

      updateDemoShell(originalState, { type: "close" });

      expect(originalState).toEqual(stateCopy);
    });
  });
});