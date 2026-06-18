/**
 * Authentication feature module.
 * 
 * Exports:
 * - AuthGate: Component that protects routes requiring authentication
 * - useAuth: React hook for authentication state
 * - useAuthContext: Hook to access auth context from within AuthGate
 * - LoginPage: Login page component
 * - AuthUser, AuthState, LoginCredentials: Type definitions
 * - loginApi, logoutApi, checkAuthApi, checkAuthStatus: Non-hook API functions
 */

export { AuthGate, useAuthContext } from "./AuthGate";
export type { AuthStatusResponse } from "./authState";
export { useAuth } from "./authState";
export type {
  AuthUser,
  AuthState,
  AuthMeResponse,
  AuthLoginResponse,
  AuthLogoutResponse,
  LoginCredentials,
} from "./authState";
export { loginApi, logoutApi, checkAuthApi, checkAuthStatus } from "./authState";

export { LoginPage } from "./LoginPage";
