/**
 * Authentication state management for the K9b frontend.
 * 
 * This module manages authentication state using:
 * - Server-side HttpOnly session cookies (no tokens in localStorage/sessionStorage)
 * - /api/auth/me endpoint for checking authentication state
 * - /api/auth/login and /api/auth/logout for authentication actions
 * 
 * Security notes:
 * - Session cookies are HttpOnly (not accessible to JavaScript)
 * - Authentication state is kept in React state (memory only)
 * - No sensitive data is stored in localStorage or sessionStorage
 */

import { useState, useEffect, useCallback } from "react";

/**
 * User information returned from the auth API.
 */
export interface AuthUser {
  principal_id: string;
  display_name: string;
  auth_method: string;
}

/**
 * Response from /api/auth/me endpoint.
 */
export interface AuthMeResponse {
  authenticated: boolean;
  user: AuthUser | null;
}

/**
 * Response from /api/auth/login endpoint.
 */
export interface AuthLoginResponse {
  authenticated: boolean;
  user: AuthUser;
}

/**
 * Response from /api/auth/logout endpoint.
 */
export interface AuthLogoutResponse {
  authenticated: false;
}

/**
 * Authentication state for the application.
 */
export interface AuthState {
  /** Whether the user is authenticated */
  isAuthenticated: boolean;
  /** The authenticated user, or null if not authenticated */
  user: AuthUser | null;
  /** Whether authentication state is still loading */
  isLoading: boolean;
  /** Error message if authentication check failed */
  error: string | null;
}

/**
 * Login credentials.
 */
export interface LoginCredentials {
  username: string;
  password: string;
}

/**
 * Hook for managing authentication state.
 * 
 * This hook:
 * 1. Checks authentication state on mount by calling /api/auth/me
 * 2. Provides login/logout functions
 * 3. Returns current authentication state
 * 
 * @example
 * ```tsx
 * function App() {
 *   const auth = useAuth();
 *   
 *   if (auth.isLoading) {
 *     return <div>Loading...</div>;
 *   }
 *   
 *   if (!auth.isAuthenticated) {
 *     return <LoginPage onLogin={auth.login} />;
 *   }
 *   
 *   return <Dashboard user={auth.user} onLogout={auth.logout} />;
 * }
 * ```
 */
export function useAuth() {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: false,
    user: null,
    isLoading: true,
    error: null,
  });

  /**
   * Check authentication state by calling /api/auth/me
   */
  const checkAuth = useCallback(async () => {
    try {
      const response = await fetch("/api/auth/me", {
        // Include credentials (cookies) in the request
        credentials: "include",
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(`Auth check failed: ${response.statusText}`);
      }

      const data: AuthMeResponse = await response.json();

      setState({
        isAuthenticated: data.authenticated,
        user: data.user,
        isLoading: false,
        error: null,
      });
    } catch (err) {
      setState({
        isAuthenticated: false,
        user: null,
        isLoading: false,
        error: err instanceof Error ? err.message : "Failed to check authentication",
      });
    }
  }, []);

  /**
   * Login with username and password.
   */
  const login = useCallback(async (credentials: LoginCredentials): Promise<boolean> => {
    try {
      setState(prev => ({ ...prev, isLoading: true, error: null }));

      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include", // Include cookies in request
        body: JSON.stringify(credentials),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: "Login failed" }));
        throw new Error(errorData.error || "Login failed");
      }

      const data: AuthLoginResponse = await response.json();

      setState({
        isAuthenticated: true,
        user: data.user,
        isLoading: false,
        error: null,
      });

      return true;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Login failed";
      setState(prev => ({
        ...prev,
        isLoading: false,
        error: errorMessage,
      }));
      return false;
    }
  }, []);

  /**
   * Logout the current user.
   */
  const logout = useCallback(async (): Promise<void> => {
    try {
      setState(prev => ({ ...prev, isLoading: true }));

      await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "include", // Include cookies in request
        cache: "no-store",
      });

      setState({
        isAuthenticated: false,
        user: null,
        isLoading: false,
        error: null,
      });
    } catch (err) {
      // Even if logout fails, clear local state
      setState({
        isAuthenticated: false,
        user: null,
        isLoading: false,
        error: err instanceof Error ? err.message : "Logout failed",
      });
    }
  }, []);

  // Check authentication on mount
  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  return {
    ...state,
    login,
    logout,
    checkAuth,
  };
}

/**
 * Simple login function for use outside of React components.
 */
export async function loginApi(credentials: LoginCredentials): Promise<AuthLoginResponse> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify(credentials),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ error: "Login failed" }));
    throw new Error(errorData.error || "Login failed");
  }

  return response.json();
}

/**
 * Logout function for use outside of React components.
 */
export async function logoutApi(): Promise<void> {
  await fetch("/api/auth/logout", {
    method: "POST",
    credentials: "include",
    cache: "no-store",
  });
}

/**
 * Check authentication state function for use outside of React components.
 */
export async function checkAuthApi(): Promise<AuthMeResponse> {
  const response = await fetch("/api/auth/me", {
    credentials: "include",
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Auth check failed: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Response from /api/auth/status endpoint.
 */
export interface AuthStatusResponse {
  auth_enabled: boolean;
  supports_password_auth: boolean;
  development_mode: boolean;
}

/**
 * Check authentication status (whether auth is required/enabled).
 */
export async function checkAuthStatus(): Promise<AuthStatusResponse> {
  const response = await fetch("/api/auth/status", {
    credentials: "include",
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Auth status check failed: ${response.statusText}`);
  }

  return response.json();
}
