# Static/Artifact Serving Security Contract

**Document purpose:** Inventory all file-serving routes and document the security contract that protects them.

**Search scope:** This document covers all routes and functions that serve files or file-like artifacts from the k9b UI server, specifically:

- `src/k8s_diag_agent/ui/server_static.py` — static/artifact serving logic
- `src/k8s_diag_agent/ui/server.py` — HTTP route dispatch (`HealthUIRequestHandler`)

Routes or functions added after this document is written must either reuse the hardened primitives from `server_static.py` or include equivalent regression tests.

---

## Security Invariant

**No request may cause k9b to read or serve a file outside explicitly allowed roots.**

Every file-serving surface has a defined allowed root. Path input is treated as hostile. Containment is verified before filesystem access. Symlink artifacts are rejected.

---

## Route Inventory

| Route / Handler | Content Type | Allowed Root | Path Input Source | Valid Behavior | Malicious Path Behavior | Symlink Policy | Protecting Tests |
|-----------------|---------------|--------------|-------------------|---------------|------------------------|----------------|-----------------|
| `GET /artifact?path=<rel>` | JSON or ZIP | `runs_dir` (via handler) | Query param `path` (parsed via `parse_qs`) | Serves regular files under `runs_dir` | 400/403/404; no canary content served | **Reject** symlink artifacts (any `is_symlink()` → 400) | `TestServeArtifactPathTraversal` (test_server_static_path_traversal.py) <br> `TestSymlinkEscapePrevention` (test_server_static_symlink_escape.py) <br> `TestArtifactHTTPRoute` (test_server_http_routes.py) |
| `GET /*` (non-API) | Any static asset | `static_dir` (frontend/dist) | URL path (stripped `/`) | Serves static files; falls back to `index.html` for SPA | Falls back to `index.html`; never serves attacker-targeted files | N/A (no artifact path; static-only) | `TestServeStaticPathTraversal` (test_server_static_path_traversal.py) <br> `TestStaticHTTPRoute` (test_server_http_routes.py) |

### Route Details

#### `GET /artifact?path=<relative>`

- **Handler function:** `serve_artifact(handler, query)` in `server_static.py`
- **HTTP dispatch:** `HealthUIRequestHandler.do_GET()` → `route == "/artifact"` branch
- **Allowed root:** `handler.runs_dir` (set at server startup)
- **Subdirectories served:** Any regular file under `runs_dir` (e.g., `runs/health/`, `runs/external-analysis/`, etc.)
- **Content types:** JSON (`application/json; charset=utf-8`), ZIP (`application/zip` with Content-Disposition attachment header)

#### `GET /*` (Static/SPA fallback)

- **Handler function:** `serve_static(handler, route)` in `server_static.py`
- **HTTP dispatch:** `HealthUIRequestHandler.do_GET()` → `else` branch (non-API, non-artifact paths)
- **Allowed root:** `handler.static_dir` (default: `PROJECT_ROOT / "frontend" / "dist"`)
- **Behavior:** Serves matching static files; returns `index.html` for unknown paths (SPA routing)
- **Content types:** Determined by `mimetypes.guess_type()`

---

## Artifact-Serving Contract (`serve_artifact`)

The `serve_artifact` function in `server_static.py` enforces the following policy:

1. **`path` query parameter is hostile input.** It is parsed with `parse_qs`, which decodes URL encoding. The decoded value is passed to `_contains_hostile_components()` before any filesystem access.

2. **Decoded path is checked for hostile components.** `_contains_hostile_components()` rejects:
   - Null bytes (`\x00`)
   - Leading `/` or `\` (absolute paths)
   - Windows drive letters (`X:`)
   - UNC paths (`\\`)
   - `..` components (path traversal)

3. **Symlink artifacts are rejected.** `candidate.is_symlink()` is checked; any symlink returns 400. This prevents both direct symlink files and intermediate-symlink-component escapes.

4. **Resolved path must remain under resolved `runs_dir`.** After joining and resolving both paths, `Path.relative_to()` is used to verify containment. `ValueError` on containment failure returns 403.

5. **Only regular files are served.** `artifact_resolved.is_file()` must be True; directories and non-files return 404.

6. **Error responses must not leak host paths.** All error messages use static strings (e.g., `"Invalid artifact path"`, `"Access denied"`, `"Artifact not found"`). The `log_artifact_request()` structured log accepts `None` for `runs_root` when it would otherwise expose the path.

---

## Static/SPA-Serving Contract (`serve_static`)

The `serve_static` function in `server_static.py` enforces:

1. **Static files are served only from `static_dir`.** The candidate path is built as `static_dir / target.lstrip("/")` and resolved. String-prefix check `str(candidate).startswith(str(static_root))` verifies containment.

2. **Traversal/unknown routes fall back to `index.html`.** If the candidate path does not exist or escapes the static root, `candidate` is reassigned to `static_root / "index.html"`.

3. **Fallback must never serve attacker-targeted files.** The prefix check ensures the fallback `index.html` path is within `static_dir`.

4. **Fallback must not leak host paths.** The `404` message for missing static assets uses a static string (`"Static assets unavailable"`).

---

## Artifact Symlink Policy

> **Policy: Reject symlink artifacts.**

The `serve_artifact()` function checks `candidate.is_symlink()` before any path resolution and returns 400 if the artifact is a symlink. This is the preferred policy: reject symlink artifacts with no exceptions.

Rationale: A symlink inside `runs_dir` can point to a file outside `runs_dir`. The `relative_to()` containment check catches the escaped resolved path, but rejecting at `is_symlink()` provides a cleaner and more predictable policy.

The `serve_static()` function does not have an artifact-path input and is not affected by this policy.

---

## Regression Test Map

The following test modules and classes protect the file-serving surface:

| Test File | Test Classes | Coverage |
|-----------|--------------|----------|
| `tests/security/test_server_static_path_traversal.py` | `TestServeArtifactPathTraversal` | Path traversal (`..`), absolute paths, null bytes, sensitive file probes, dot-segment normalization, canary access |
| `tests/security/test_server_static_path_traversal.py` | `TestServeStaticPathTraversal` | Static route traversal → index.html fallback |
| `tests/security/test_server_static_symlink_escape.py` | `TestSymlinkEscapePrevention` | Symlink files, intermediate symlink directories |
| `tests/security/test_server_http_routes.py` | `TestArtifactHTTPRoute` | HTTP-level rejection of traversal, encoded traversal, double-encoded traversal, absolute paths, null bytes, canary access, path leak |
| `tests/security/test_server_http_routes.py` | `TestStaticHTTPRoute` | HTTP-level static fallback, canary not served, path leak |
| `tests/security/test_server_http_routes.py` | `TestSymlinkEscapeViaHTTP` | Symlink escape at HTTP layer |
| `tests/security/test_server_static_regression.py` | `TestPathValidationIntegration` | Verifies `safe_child_path` and `validate_run_id` integration |
| `tests/security/test_server_static_regression.py` | `TestSecurityGateCompleteness` | Payload corpus minimums |
| `tests/security/test_server_static_regression.py` | `TestBugClassRegressionCloseCriteria` | Regression close criteria |

**Support module:** `tests/security/server_static_test_support.py` — provides `SecurityCanaryFiles`, `MockHandler`, and all payload corpora (`TRAVERSAL_PAYLOADS`, `ENCODED_TRAVERSAL_PAYLOADS`, `ABSOLUTE_PATH_PAYLOADS`, `NULL_BYTE_PAYLOADS`, `DOT_SEGMENT_PAYLOADS`, `SENSITIVE_FILE_PAYLOADS`, `COMBINED_ATTACK_PAYLOADS`).

---

## Non-Goals

This document does not:

- Add authentication — auth is handled in `server.py` (`_validate_bearer_token`) and operator-auth design docs
- Redesign static serving — the SPA fallback behavior is intentional
- Permit symlink artifacts — reject policy is explicit
- Document artifact lifecycle semantics — only the serving security contract

---

## Future Guardrails

When adding new file-serving routes or modifying existing ones:

1. **New file-serving routes must reuse `serve_artifact()` or `serve_static()`** from `server_static.py`, or implement equivalent security checks:
   - Treat all path input as hostile
   - Check for `..`, null bytes, absolute paths before filesystem access
   - Verify resolved path containment using `Path.relative_to()` or `is_relative_to()`
   - Reject symlinks if serving artifacts

2. **New path parameters must be treated as hostile.** The pattern in `serve_artifact()` (`parse_qs` → `_contains_hostile_components()` → containment check) should be replicated.

3. **New downloadable artifact types must document allowed roots and file type behavior.** Extend this inventory table when new serving functions are added.

4. **Add regression tests for any new serving surface.** At minimum, add HTTP-level tests with:
   - Valid request → 200
   - Path traversal → non-200, no canary leak
   - Absolute path → non-200
   - Symlink artifact (if applicable) → non-200

---

## Verification Commands

```bash
# Verify the security invariant statement exists
grep -n "No request may cause" docs/security/static-artifact-serving-contract.md

# Verify symlink policy is documented
grep -n "reject symlink" docs/security/static-artifact-serving-contract.md

# Verify test file references
grep -n "test_server_static_regression.py" docs/security/static-artifact-serving-contract.md
grep -n "test_server_http_routes.py" docs/security/static-artifact-serving-contract.md

# Run the security regression tests
.venv/bin/python -m pytest tests/security/test_server_static_path_traversal.py tests/security/test_server_static_symlink_escape.py tests/security/test_server_http_routes.py tests/security/test_server_static_regression.py -v --tb=short

# Run the full verification gate
scripts/verify_all.sh
```

Expected test results: all tests pass with no canary content leakage.

---

*Last reviewed: 2026-05-29*
*Part of: Epic: Harden static and artifact path serving*
