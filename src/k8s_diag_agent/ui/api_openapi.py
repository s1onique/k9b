"""OpenAPI endpoint handlers for the k9b UI server.

This module provides:
- GET /api/openapi.json - Returns the OpenAPI 3.1 schema as JSON
- GET /api/docs - Returns an API reference HTML page that loads /api/openapi.json

Note: /api/docs is a custom endpoint listing UI, not real Swagger UI.
For production deployments, consider requiring auth for /api/docs or
restricting it to admin users to avoid exposing your API inventory.

These endpoints are public (no auth required) to allow API exploration
in development/test environments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .api_contract import build_openapi_schema

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler


# API reference HTML - static endpoint listing, no external dependencies, works offline
_API_REFERENCE_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>k9b API Documentation</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; padding: 20px; background: #fafafa; }
    .container { max-width: 1200px; margin: 0 auto; }
    h1 { color: #333; border-bottom: 2px solid #0066cc; padding-bottom: 10px; }
    .info { background: #e8f4fc; border: 1px solid #b8daef; border-radius: 4px; padding: 15px; margin-bottom: 20px; }
    .info p { margin: 5px 0; color: #2c5282; }
    .endpoints { background: white; border: 1px solid #ddd; border-radius: 4px; }
    .endpoint { border-bottom: 1px solid #eee; padding: 15px; }
    .endpoint:last-child { border-bottom: none; }
    .method { display: inline-block; padding: 4px 8px; border-radius: 3px; font-weight: bold; font-size: 12px; }
    .method.get { background: #61affe; color: white; }
    .method.post { background: #49cc90; color: white; }
    .method.put { background: #fca130; color: white; }
    .method.delete { background: #f93e3e; color: white; }
    .path { font-family: monospace; font-size: 14px; color: #3f3f3f; margin-left: 10px; }
    .summary { color: #666; font-size: 13px; margin-top: 5px; }
    .tags { display: inline-block; margin-left: 10px; }
    .tag { display: inline-block; background: #eee; padding: 2px 6px; border-radius: 3px; font-size: 11px; color: #555; margin-right: 5px; }
    .operation-id { font-family: monospace; font-size: 11px; color: #888; margin-top: 5px; }
    .auth-badge { display: inline-block; background: #ffeeba; padding: 2px 6px; border-radius: 3px; font-size: 11px; color: #856404; margin-left: 10px; }
  </style>
</head>
<body>
  <div class="container">
    <h1>k9b API Documentation</h1>
    <div class="info">
      <p><strong>OpenAPI Version:</strong> <span id="version">-</span></p>
      <p><strong>Base URL:</strong> <span id="base-url">-</span></p>
      <p><strong>Total Endpoints:</strong> <span id="count">-</span></p>
    </div>
    <div class="endpoints" id="endpoints">Loading...</div>
  </div>
  <script>
    async function loadSchema() {
      try {
        const response = await fetch('/api/openapi.json');
        const schema = await response.json();
        
        document.getElementById('version').textContent = schema.info?.version || '0.1.0';
        document.getElementById('base-url').textContent = (schema.servers?.[0]?.url) || '/';
        
        const container = document.getElementById('endpoints');
        container.innerHTML = '';
        
        let count = 0;
        const paths = schema.paths || {};
        
        for (const [path, methods] of Object.entries(paths)) {
          for (const [method, operation] of Object.entries(methods)) {
            if (['get', 'post', 'put', 'patch', 'delete'].includes(method.toLowerCase())) {
              count++;
              const div = document.createElement('div');
              div.className = 'endpoint';
              
              const tags = (operation.tags || []).map(t => '<span class="tag">' + t + '</span>').join('');
              const requiresAuth = operation.security === undefined || operation.security.length > 0;
              
              div.innerHTML = 
                '<span class="method ' + method.toLowerCase() + '">' + method.toUpperCase() + '</span>' +
                '<span class="path">' + path + '</span>' +
                '<span class="tags">' + tags + '</span>' +
                (requiresAuth ? '<span class="auth-badge">auth required</span>' : '<span class="auth-badge" style="background:#d4edda;color:#155724">public</span>') +
                '<div class="summary">' + (operation.summary || '') + '</div>' +
                '<div class="operation-id">operationId: ' + (operation.operationId || 'N/A') + '</div>';
              
              container.appendChild(div);
            }
          }
        }
        
        document.getElementById('count').textContent = count;
      } catch (err) {
        document.getElementById('endpoints').innerHTML = '<p style="color:red">Failed to load schema: ' + err.message + '</p>';
      }
    }
    loadSchema();
  </script>
</body>
</html>
"""


def handle_openapi_json(handler: HealthUIRequestHandler) -> None:
    """Handle GET /api/openapi.json - return the OpenAPI schema as JSON.

    This endpoint is public (no auth required) to allow API exploration.
    """
    from .server_response import send_json_response

    schema = build_openapi_schema()
    send_json_response(handler, schema, code=200)


def handle_openapi_docs(handler: HealthUIRequestHandler) -> None:
    """Handle GET /api/docs - return an API reference HTML page.

    This endpoint is public (no auth required) to allow API exploration.
    """
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Expires", "0")
    content = _API_REFERENCE_HTML.encode("utf-8")
    handler.send_header("Content-Length", str(len(content)))
    handler.end_headers()
    handler.wfile.write(content)
