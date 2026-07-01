/**
 * health.ts - Health API wrapper using generated OpenAPI client.
 *
 * This module wraps the generated client for health endpoints.
 * Existing React components import from this module, so exports remain stable.
 */

import type { Configuration } from "../generated/k9b-api";
import {
  HealthApi,
  GetHealth200Response,
  GetHealthDetails200Response,
} from "../generated/k9b-api";

/**
 * Create a HealthApi instance with the given configuration.
 */
export function createHealthApi(config: Configuration): HealthApi {
  return new HealthApi(config);
}

/**
 * Fetch backend health status (public - no auth required).
 */
export async function fetchHealth(config: Configuration): Promise<GetHealth200Response> {
  const api = createHealthApi(config);
  return api.getHealth();
}

/**
 * Fetch detailed health diagnostics (public - no auth required).
 */
export async function fetchHealthDetails(config: Configuration): Promise<GetHealthDetails200Response> {
  const api = createHealthApi(config);
  return api.getHealthDetails();
}
