/**
 * runtime.ts - Runtime status API wrapper using generated OpenAPI client.
 *
 * This module wraps the generated client for runtime status endpoints.
 * Existing React components import from this module, so exports remain stable.
 */

import type { Configuration } from "../generated/k9b-api";
import {
  RuntimeApi,
} from "../generated/k9b-api";

/**
 * Create a RuntimeApi instance with the given configuration.
 */
export function createRuntimeApi(config: Configuration): RuntimeApi {
  return new RuntimeApi(config);
}

/**
 * Fetch runtime status (PVC usage, log windows, etc.).
 * Returns the raw response from the generated client.
 */
export async function fetchRuntimeStatus(
  config: Configuration
): Promise<Record<string, unknown>> {
  const api = createRuntimeApi(config);
  return api.getRuntimeStatus() as Promise<Record<string, unknown>>;
}
