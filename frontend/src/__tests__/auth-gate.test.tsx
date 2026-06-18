/**
 * AuthGate component tests.
 * 
 * Tests that AuthGate correctly:
 * - Shows LoginPage when auth is enabled and user is not authenticated
 * - Shows main App when auth is disabled (development mode)
 * - Shows loading state while checking auth status
 */

import { render, screen, waitFor } from "@testing-library/react";
import { describe, test, vi, beforeEach, afterEach } from "vitest";
import { AuthGate } from "../features/auth/AuthGate";

// Mock LoginPage to avoid complex form rendering
vi.mock("../features/auth/LoginPage", () => ({
  LoginPage: ({ onLoginSuccess }: { onLoginSuccess?: () => void }) => (
    <div data-testid="login-page">
      <button onClick={onLoginSuccess}>Mock Login</button>
    </div>
  ),
}));

describe("AuthGate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("shows loading state while checking auth", async () => {
    // Mock fetch to hang (never resolve)
    const fetchMock = vi.fn(() => new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthGate>
        <div data-testid="main-app">Main App</div>
      </AuthGate>
    );

    // Should show loading spinner
    expect(screen.getByTestId("auth-gate-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("main-app")).not.toBeInTheDocument();
  });

  test("shows LoginPage when auth is enabled and user is not authenticated", async () => {
    // Mock auth status endpoint - auth enabled
    // Mock auth/me endpoint - not authenticated
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/auth/status") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ auth_enabled: true, supports_password_auth: true, development_mode: false }),
        });
      }
      if (url === "/api/auth/me") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ authenticated: false, user: null }),
        });
      }
      return Promise.reject(new Error("Unexpected URL"));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthGate>
        <div data-testid="main-app">Main App</div>
      </AuthGate>
    );

    // Should show LoginPage
    await waitFor(() => {
      expect(screen.getByTestId("login-page")).toBeInTheDocument();
    });
    // Main app should NOT be visible
    expect(screen.queryByTestId("main-app")).not.toBeInTheDocument();
  });

  test("shows main app when auth is disabled (development mode)", async () => {
    // Mock auth status endpoint - auth disabled
    // Mock auth/me endpoint - authenticated (dev mode auto-authenticates)
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/auth/status") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ auth_enabled: false, supports_password_auth: true, development_mode: true }),
        });
      }
      if (url === "/api/auth/me") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ authenticated: true, user: { principal_id: "dev", display_name: "Developer", auth_method: "local-dev" } }),
        });
      }
      return Promise.reject(new Error("Unexpected URL"));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthGate>
        <div data-testid="main-app">Main App</div>
      </AuthGate>
    );

    // Should show main app (wrapped in AuthContext)
    await waitFor(() => {
      expect(screen.getByTestId("main-app")).toBeInTheDocument();
    });
    // LoginPage should NOT be visible
    expect(screen.queryByTestId("login-page")).not.toBeInTheDocument();
  });

  test("shows main app when user is authenticated", async () => {
    // Mock auth status endpoint - auth enabled
    // Mock auth/me endpoint - authenticated
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/auth/status") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ auth_enabled: true, supports_password_auth: true, development_mode: false }),
        });
      }
      if (url === "/api/auth/me") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ authenticated: true, user: { principal_id: "admin", display_name: "Admin", auth_method: "local" } }),
        });
      }
      return Promise.reject(new Error("Unexpected URL"));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthGate>
        <div data-testid="main-app">Main App</div>
      </AuthGate>
    );

    // Should show main app
    await waitFor(() => {
      expect(screen.getByTestId("main-app")).toBeInTheDocument();
    });
    // LoginPage should NOT be visible
    expect(screen.queryByTestId("login-page")).not.toBeInTheDocument();
  });
});