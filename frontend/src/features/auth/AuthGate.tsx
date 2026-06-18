/**
 * AuthGate component - protects application routes with authentication.
 * 
 * This component:
 * 1. Fetches auth status to check if authentication is enabled
 * 2. Fetches current auth state to check if user is logged in
 * 3. Shows loading state while checking
 * 4. Shows LoginPage if auth is enabled but user is not authenticated
 * 5. Renders children when user is authenticated (or auth is disabled)
 */

import { useState, useEffect, useCallback } from "react";
import { LoginPage } from "./LoginPage";
import type { AuthUser, AuthStatusResponse } from "./authState";

interface AuthGateProps {
  children: React.ReactNode;
}

/**
 * AuthGate component that protects routes requiring authentication.
 */
export function AuthGate({ children }: AuthGateProps) {
  const [authEnabled, setAuthEnabled] = useState<boolean | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const checkAuthStatus = useCallback(async () => {
    try {
      const response = await fetch("/api/auth/status", {
        credentials: "include",
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`Auth status check failed: ${response.statusText}`);
      }
      const data: AuthStatusResponse = await response.json();
      setAuthEnabled(data.auth_enabled);
    } catch (err) {
      // If status endpoint fails, assume auth is enabled for security
      setAuthEnabled(true);
      setError(err instanceof Error ? err.message : "Failed to check auth status");
    }
  }, []);

  const checkAuth = useCallback(async () => {
    try {
      const response = await fetch("/api/auth/me", {
        credentials: "include",
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`Auth check failed: ${response.statusText}`);
      }
      const data = await response.json();
      setIsAuthenticated(data.authenticated);
      setUser(data.user || null);
    } catch (err) {
      setIsAuthenticated(false);
      setError(err instanceof Error ? err.message : "Failed to check authentication");
    }
  }, []);

  useEffect(() => {
    const initAuth = async () => {
      setIsLoading(true);
      setError(null);
      await checkAuthStatus();
      await checkAuth();
      setIsLoading(false);
    };
    initAuth();
  }, [checkAuthStatus, checkAuth]);

  // Handle successful login
  const handleLoginSuccess = useCallback(() => {
    setIsAuthenticated(true);
    checkAuth();
  }, [checkAuth]);

  // Handle logout
  const handleLogout = useCallback(async () => {
    try {
      await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "include",
        cache: "no-store",
      });
    } catch {
      // Ignore logout errors
    }
    setIsAuthenticated(false);
    setUser(null);
  }, []);

  // Show loading state
  if (isLoading || authEnabled === null || isAuthenticated === null) {
    return (
      <div className="auth-gate-loading" data-testid="auth-gate-loading">
        <div className="loading-spinner" />
        <style>{`
          .auth-gate-loading {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            background: #1a1a2e;
          }
          .loading-spinner {
            width: 40px;
            height: 40px;
            border: 3px solid rgba(255, 255, 255, 0.1);
            border-top-color: #4a90d9;
            border-radius: 50%;
            animation: spin 1s linear infinite;
          }
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }

  // If auth is enabled and user is not authenticated, show login page
  if (authEnabled && !isAuthenticated) {
    return (
      <LoginPage onLoginSuccess={handleLoginSuccess} />
    );
  }

  // Auth is disabled OR user is authenticated - render children with auth context
  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, logout: handleLogout }}>
      {children}
    </AuthContext.Provider>
  );
}

// Auth context for sharing auth state with components
import { createContext, useContext } from "react";

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  isAuthenticated: false,
  logout: () => {},
});

export function useAuthContext() {
  return useContext(AuthContext);
}

// Re-export LoginPage for convenience
export { LoginPage } from "./LoginPage";
