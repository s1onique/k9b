/**
 * generatedClient.ts - Handwritten wrapper around generated OpenAPI client.
 *
 * This module provides a thin layer over the generated TypeScript client.
 * It:
 * - Instantiates the generated client configuration
 * - Reuses existing frontend fetch behavior (credentials, base path)
 * - Preserves error handling conventions
 *
 * The generated client lives in ../generated/k9b-api/ and is generated
 * from the backend OpenAPI schema by running:
 *   bash scripts/generate_frontend_api_client.sh
 *
 * Do NOT edit files in ../generated/k9b-api/ directly - they are generated.
 */

import { Configuration } from "../generated/k9b-api";

// Use empty basePath so relative URLs work with the current host
const BASE_PATH = "";

/**
 * Create a typed API configuration matching existing frontend behavior.
 *
 * Uses credentials: "include" to send cookies with cross-origin requests,
 * matching the existing fetchJson behavior.
 */
export function createK9bApiConfiguration(): Configuration {
  return new Configuration({
    basePath: BASE_PATH,
    credentials: "include",
  });
}
