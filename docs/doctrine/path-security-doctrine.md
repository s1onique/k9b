# Path and Artifact Security Doctrine

**Purpose:** Prevent path traversal, arbitrary file access, and injection vulnerabilities when handling user-controlled identifiers in file paths, globs, and artifact lookups.

**Status:** Active doctrine for all static serving, artifact serving, file downloads, and path validation work.

---

## Core Rule

> **Any user-controlled path segment must be treated as hostile.**

Do not trust:
- run IDs from URL parameters
- file names from query strings
- paths from user input
- identifiers from external sources

---

## Security Invariants

### 1. Never validate paths using raw string prefix alone

Bad:
```python
if path.startswith(trusted_root):
    serve(path)
```

This fails for sibling-prefix cases like `/tmp/root-evil` under `/tmp/root`.

Good:
```python
resolved = path.resolve()
if not resolved.is_relative_to(trusted_root.resolve()):
    raise SecurityError("Path escapes root")
```

### 2. Resolve/canonicalize before boundary checks

Always use `Path.resolve()` (or `Path.absolute()`) before containment checks.

Resolution must happen after path construction, not before.

### 3. Validate each path segment individually

For composed paths, validate:
- No null bytes
- No path separators (`/` or `\`)
- No path traversal patterns (`..`)
- No glob metacharacters (`*`, `?`, `[`, `]`, `{`, `}`)
- No shell metacharacters
- Matches safe identifier pattern

### 4. Never serve arbitrary files from artifact roots

Use identifier-to-path lookup instead of direct path input.

```python
# Bad - user controls the path directly
@app.get("/download")
def download(path: str):
    return FileResponse(path)

# Good - look up by validated identifier
@app.get("/download/{run_id}/{filename}")
def download(run_id: str, filename: str):
    safe_path = safe_child_path(runs_dir, run_id, filename)
    return FileResponse(safe_path)
```

### 5. Prefer allowlist patterns over blocklists

Define what is valid rather than what is forbidden.
Allowlists are more robust against bypass attempts.

---

## Required Checks for Static/Artifact Serving

When a task touches static serving, artifact serving, file downloads, or path validation:

1. **Read the security path validation module:**
   - `src/k8s_diag_agent/security/path_validation.py`

2. **Run targeted traversal tests:**
   - `tests/test_security_path_validation.py`

3. **Add regression tests for new path boundaries:**
   - Every new file-serving path needs negative tests

4. **Close report must include trust-boundary statement:**
   - Document what root is trusted
   - Document what validation occurs
   - Document what happens on validation failure

---

## Negative Test Cases

Every new file-serving path needs tests for:

| Test case | Description |
|-----------|-------------|
| `../` | Parent directory traversal |
| `..%2F..%2F` | URL-encoded traversal |
| `%2e%2e%2f` | Double-encoded traversal |
| `/etc/passwd` | Absolute path attempt |
| `/tmp/../../../etc` | Multi-level traversal |
| `null\x00` | Null byte injection |
| `evil/../../../secret` | Mixed traversal |
| `valid.txt/../secret` | Post-fix traversal |
| `valid.txt/../../etc` | Sibling escape |
| Empty string | Invalid identifier |
| Very long string | Buffer boundary |
| Non-existent file | 404 handling |
| Directory instead of file | Type mismatch |

---

## Validator Functions

Use the security module's validators:

```python
from k8s_diag_agent.security.path_validation import (
    SecurityError,
    validate_run_id,
    validate_safe_path_id,
    safe_child_path,
    safe_run_artifact_glob,
    validate_kube_context_name,
    validate_kubernetes_namespace,
    validate_kubernetes_resource_name,
)
```

### validate_run_id(value: str) -> str

Validates run identifiers:
- Alphanumeric, hyphens, underscores only
- Must start with alphanumeric
- No path separators, traversal, or special characters
- Raises `SecurityError` on invalid input

### validate_safe_path_id(value: str, field_name: str) -> str

Same as `validate_run_id` but with custom field name in error messages.

### safe_child_path(root: Path, *parts: str) -> Path

Constructs a child path safely under a trusted root:
- Validates each segment
- Uses `Path.resolve()` to canonicalize
- Uses `is_relative_to()` (Python 3.9+) or `relative_to()` for containment
- Rejects sibling-prefix ambiguity (e.g., `/tmp/root-evil` is NOT under `/tmp/root`)
- Raises `SecurityError` if path escapes root

### safe_run_artifact_glob(run_id: str, suffix: str = "*.json") -> str

Constructs a safe glob pattern string:
- Validates run_id internally
- Validates suffix for path separators and traversal
- Returns validated glob pattern string

---

## Forbidden Patterns

Do not use:
- `path.startswith(trusted)` — fails for sibling prefixes
- `os.path.join` without validation — may not resolve traversal
- `open(user_path)` — no containment check
- `send_file(user_path)` — no containment check
- User-controlled suffixes in glob patterns without validation

---

## Error Handling

All security validation raises `SecurityError` (subclass of `ValueError`).

```python
try:
    safe_path = safe_child_path(root, run_id, filename)
except SecurityError as e:
    # Log the attempt, return 400 or 403
    raise HTTPException(status_code=400, detail="Invalid path")
```

---

## Enforcement

This doctrine is enforced via:
- Code review (reviewer checks for path security patterns)
- Unit tests (`tests/test_security_path_validation.py`)
- Integration tests for file serving endpoints
- LLM-friendly file size checks (not related but present in gate)

---

## Relationship to Other Doctrine

- Part of the security doctrine family
- Complement to `identity-primer.md` for auth/authz concerns
- Complement to `executable-claims.md` for capability claims
- Required reading for any static/artifact/file-serving work

---

## Change Policy

This doctrine changes only when:
- New attack vector is identified
- Security library behavior changes materially
- Architecture introduces new trust boundaries

Do not change for:
- Temporary workarounds
- Convenience overrides
- Local preferences