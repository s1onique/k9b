/**
 * Login page component for K9b.
 * 
 * This component provides a simple login form that:
 * - Accepts username and password
 * - Calls /api/auth/login on submission
 * - Shows generic error messages (no username/password disclosure)
 * - Redirects to the main app on successful login
 */

import { useState, FormEvent } from "react";
import type { LoginCredentials } from "./authState";

interface LoginPageProps {
  /** Callback when login is successful */
  onLoginSuccess?: () => void;
}

/**
 * Simple login page component.
 */
export function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const [credentials, setCredentials] = useState<LoginCredentials>({
    username: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify(credentials),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({ error: "Login failed" }));
        // Generic error - don't disclose which field was wrong
        setError(data.error || "Invalid credentials");
        return;
      }

      // Login successful - notify parent
      onLoginSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <h1 className="login-title">K9b Operator</h1>
        <p className="login-subtitle">Kubernetes Diagnostics Agent</p>

        <form className="login-form" onSubmit={handleSubmit}>
          {error && (
            <div className="login-error" role="alert">
              {error}
            </div>
          )}

          <div className="form-group">
            <label htmlFor="username" className="form-label">
              Username
            </label>
            <input
              type="text"
              id="username"
              name="username"
              className="form-input"
              value={credentials.username}
              onChange={e =>
                setCredentials(prev => ({ ...prev, username: e.target.value }))
              }
              disabled={isLoading}
              autoComplete="username"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="password" className="form-label">
              Password
            </label>
            <input
              type="password"
              id="password"
              name="password"
              className="form-input"
              value={credentials.password}
              onChange={e =>
                setCredentials(prev => ({ ...prev, password: e.target.value }))
              }
              disabled={isLoading}
              autoComplete="current-password"
              required
            />
          </div>

          <button
            type="submit"
            className="login-button"
            disabled={isLoading || !credentials.username || !credentials.password}
          >
            {isLoading ? "Signing in..." : "Sign In"}
          </button>
        </form>

        <div className="login-footer">
          <p className="login-footer-text">
            Session-based authentication. Cookies required.
          </p>
        </div>
      </div>

      <style>{`
        .login-page {
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 100vh;
          background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
          padding: 1rem;
        }

        .login-container {
          background: white;
          border-radius: 12px;
          padding: 2.5rem;
          width: 100%;
          max-width: 400px;
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        }

        .login-title {
          font-size: 1.75rem;
          font-weight: 700;
          color: #1a1a2e;
          margin: 0 0 0.25rem 0;
          text-align: center;
        }

        .login-subtitle {
          font-size: 0.875rem;
          color: #666;
          margin: 0 0 2rem 0;
          text-align: center;
        }

        .login-form {
          display: flex;
          flex-direction: column;
          gap: 1.25rem;
        }

        .login-error {
          background: #fee;
          border: 1px solid #fcc;
          border-radius: 6px;
          color: #c00;
          padding: 0.75rem 1rem;
          font-size: 0.875rem;
          text-align: center;
        }

        .form-group {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }

        .form-label {
          font-size: 0.875rem;
          font-weight: 500;
          color: #333;
        }

        .form-input {
          padding: 0.75rem 1rem;
          border: 1px solid #ddd;
          border-radius: 6px;
          font-size: 1rem;
          transition: border-color 0.2s, box-shadow 0.2s;
        }

        .form-input:focus {
          outline: none;
          border-color: #4a90d9;
          box-shadow: 0 0 0 3px rgba(74, 144, 217, 0.15);
        }

        .form-input:disabled {
          background: #f5f5f5;
          cursor: not-allowed;
        }

        .login-button {
          margin-top: 0.5rem;
          padding: 0.875rem 1.5rem;
          background: #4a90d9;
          color: white;
          border: none;
          border-radius: 6px;
          font-size: 1rem;
          font-weight: 600;
          cursor: pointer;
          transition: background-color 0.2s, transform 0.1s;
        }

        .login-button:hover:not(:disabled) {
          background: #3a7fc9;
        }

        .login-button:active:not(:disabled) {
          transform: scale(0.98);
        }

        .login-button:disabled {
          background: #ccc;
          cursor: not-allowed;
        }

        .login-footer {
          margin-top: 2rem;
          padding-top: 1.5rem;
          border-top: 1px solid #eee;
        }

        .login-footer-text {
          font-size: 0.75rem;
          color: #999;
          text-align: center;
          margin: 0;
        }
      `}</style>
    </div>
  );
}

export default LoginPage;