/**
 * auth.ts - Auth API wrapper using generated OpenAPI client.
 *
 * This module wraps the generated client for auth endpoints.
 * Existing React components import from this module, so exports remain stable.
 */

import type { Configuration } from "../generated/k9b-api";
import {
  AuthApi,
  PostAuthLoginRequest,
  GetAuthStatus200Response,
  GetAuthMe200Response,
  PostAuthLogin200Response,
} from "../generated/k9b-api";

/**
 * Create an AuthApi instance with the given configuration.
 */
export function createAuthApi(config: Configuration): AuthApi {
  return new AuthApi(config);
}

/**
 * Get authentication status (public - no auth required).
 */
export async function fetchAuthStatus(config: Configuration): Promise<GetAuthStatus200Response> {
  const api = createAuthApi(config);
  return api.getAuthStatus();
}

/**
 * Get current user info (public - no auth required).
 */
export async function fetchAuthMe(config: Configuration): Promise<GetAuthMe200Response> {
  const api = createAuthApi(config);
  return api.getAuthMe();
}

/**
 * Login with username and password.
 */
export async function login(
  config: Configuration,
  credentials: PostAuthLoginRequest
): Promise<PostAuthLogin200Response> {
  const api = createAuthApi(config);
  return api.postAuthLogin({ postAuthLoginRequest: credentials });
}

/**
 * Logout current session.
 */
export async function logout(config: Configuration): Promise<PostAuthLogin200Response> {
  const api = createAuthApi(config);
  return api.postAuthLogout();
}
