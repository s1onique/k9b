import "@testing-library/jest-dom";
import { beforeEach, afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// Mock localStorage for all tests
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string): string | null => store[key] ?? null,
    setItem: (key: string, value: string): void => {
      store[key] = value;
    },
    removeItem: (key: string): void => {
      delete store[key];
    },
    clear: (): void => {
      store = {};
    },
    get length(): number {
      return Object.keys(store).length;
    },
    key: (index: number): string | null => {
      const keys = Object.keys(store);
      return keys[index] ?? null;
    },
  };
})();

Object.defineProperty(globalThis, "localStorage", {
  value: localStorageMock,
  writable: true,
  configurable: true,
});

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  // Flush any pending async work and cleanup React Testing Library rendered elements
  // This prevents async cleanup errors like "ReferenceError: window is not defined"
  // when setTimeout callbacks from mock implementations fire after jsdom teardown
  try {
    vi.runOnlyPendingTimers();
  } catch {
    // Timers not mocked (real timers used), skip timer flushing
  }
  cleanup();
});
