/**
 * generatedClient.ts - Handwritten wrapper around generated OpenAPI client.
 *
 * This module provides a thin layer over the generated TypeScript client.
 * It:
 * - Instantiates the generated client configuration
 * - Reuses existing frontend fetch behavior (credentials, base path)
 * - Preserves error handling conventions
 * - Guards against SPA HTML fallback responses
 *
 * The generated client lives in ../generated/k9b-api/ and is generated
 * from the backend OpenAPI schema by running:
 *   bash scripts/generate_frontend_api_client.sh
 *
 * Do NOT edit files in ../generated/k9b-api/ directly - they are generated.
 */

import { Configuration } from "../generated/k9b-api";
import { ResponseError } from "../generated/k9b-api/runtime";

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

/**
 * Check if a response body looks like HTML content.
 * Detects common HTML patterns including DOCTYPE, <html>, <body> tags.
 */
function looksLikeHtml(body: string): boolean {
  const trimmed = body.trim();
  return (
    trimmed.startsWith("<!") ||
    trimmed.startsWith("<html") ||
    trimmed.startsWith("<body") ||
    /<(doctype|html|head|body)/i.test(trimmed)
  );
}

/**
 * Normalize errors from the generated OpenAPI client to match existing
 * frontend error handling conventions.
 *
 * The generated typescript-fetch client throws ResponseError for non-2xx responses.
 * This helper extracts the error message in a way compatible with the existing
 * extractErrorMessage pattern used by handwritten fetch wrappers.
 *
 * Also detects SPA HTML fallback responses by checking if the response body
 * looks like HTML content.
 */
export async function normalizeGeneratedApiError(error: unknown): Promise<Error> {
  if (error instanceof ResponseError) {
    let detail = "";
    try {
      detail = await error.response.text();
      // Try to parse as JSON and extract error field
      try {
        const payload = JSON.parse(detail);
        if (payload && typeof payload === "object" && "error" in payload) {
          detail = String((payload as Record<string, unknown>).error);
        }
      } catch {
        // Not JSON, check if it looks like HTML
        if (looksLikeHtml(detail)) {
          // This is HTML content returned instead of JSON
          // Use a descriptive message
          detail =
            `Expected JSON but received text/html. ` +
            "API route may be falling through to SPA index.html";
        }
        // Otherwise use raw text
      }
    } catch {
      // ignore text extraction failures
    }
    return new Error(detail || `Request failed with status ${error.response.status}`);
  }

  return error instanceof Error ? error : new Error(String(error));
}
