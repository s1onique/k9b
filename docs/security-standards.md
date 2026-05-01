# Security Standards

This document defines mandatory security standards for the k9b backend and API layer.

## 1. Identifier Validation

### Requirement

User-controlled identifiers (run_id, artifact_id, proposal_id, execution_id, cluster_label, source_id) **must never** be interpolated into:
- File paths
- Glob patterns
- Subprocess arguments
- Artifact lookups

...without prior validation.

### Validated Pattern

Valid run IDs match: `^[a-zA-Z0-9][a-zA-Z0-9_-]*$`

This pattern accepts:
- Alphanumeric characters
- Hyphens and underscores (not at start)
- Minimum 1 character

### Rejection Criteria

The following must be **rejected**:
- Path traversal strings: `../`, `..`
- Absolute paths: starting with `/` or `\` or a drive letter
- Glob metacharacters: `*`, `?`, `[`, `]`, `{`, `}`
- Null bytes: `\x00`
- Newlines or control characters

### Validation Functions

```python
# src/k8s_diag_agent/security/path_validation.py
validate_run_id(value: str) -> str  # Raises ValueError on invalid
validate_safe_path_id(value: str, field_name: str) -> str
```

## 2. Path Containment

### Requirement

All file access operations must resolve under a **trusted root**.

### Implementation

```python
safe_child_path(root: Path, *parts: str) -> Path
```

This helper:
1. Validates each part against the safe path ID pattern
2. Resolves the resulting path
3. Confirms it is relative to the trusted root using Path semantics
4. Raises `SecurityError` if containment is violated

### Never Do This

```python
# BAD - path traversal vulnerability
path = root / user_input

# BAD - unvalidated glob
glob(f"{run_id}-*.json")

# GOOD - validated glob pattern (separate from path construction)
validated_run_id = validate_run_id(user_input)
pattern = safe_run_artifact_glob(validated_run_id)  # Returns "run-id*.json"
for file in artifact_dir.glob(pattern):
    ...
```

## 3. Artifact JSON Schema Boundary

### Requirement

When reading artifact JSON files:
1. Validate the file path is under the trusted root
2. Parse JSON safely
3. Validate required fields before use
4. Handle malformed JSON gracefully (log, skip, continue)

### Pattern

```python
def read_artifact(root: Path, validated_id: str, filename_pattern: str) -> dict | None:
    safe_path = safe_child_path(root, validated_id, filename_pattern)
    if not safe_path.exists():
        return None
    try:
        return json.loads(safe_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Malformed artifact", extra={"path": str(safe_path)})
        return None
```

## 4. Exception/Logging Policy

### Requirement

Silent exception swallowing is **banned**. Every exception handler must either:
1. Re-raise with context
2. Log with structured output including `exc_info=True`
3. Convert to a typed API error response

### Structured Logging Pattern

```python
try:
    do_something()
except SomeError as exc:
    logger.warning(
        "Operation failed",
        exc_info=True,  # Always include for recoverable errors
        extra={"run_id": run_id, "operation": "do_something"}
    )
    raise
```

### Banned Patterns

```python
# BANNED - silent swallow
except Exception:
    pass

# BANNED - no context
except Exception as e:
    logger.warning(f"Failed: {e}")

# BANNED - no stack trace
except Exception:
    logger.warning("Failed")
```

### Exception to Policy

Silent handling is allowed **only** when:
1. The operation is explicitly optional
2. Failure has no observable side effects
3. A comment documents why this is safe

## 5. Subprocess Evidence Policy

### Requirement

Diagnostic subprocesses must **never** use `stderr=DEVNULL`.

### Rationale

Stderr contains diagnostic information that may be critical for debugging. Suppressing it can hide:
- Command failures
- Error messages
- Warning conditions

### Banned Pattern

```python
# BANNED
subprocess.run(cmd, stderr=DEVNULL)
```

### Required Pattern

```python
# Capture stderr for diagnostics
result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
)
if result.returncode != 0:
    logger.warning(
        "Command failed",
        extra={
            "cmd": cmd,
            "returncode": result.returncode,
            "stderr_preview": result.stderr[:500],  # Log for debugging
        },
    )
```

## 6. API Error Envelope Policy

### Requirement

All API errors must return a structured JSON envelope.

### Required Shape

```json
{
  "error": "Human-readable message",
  "code": "MACHINE_CODE"  // Optional, for programmatic handling
}
```

### Status Codes

- `400` - Invalid input / validation failure
- `404` - Resource not found
- `409` - Conflict (e.g., duplicate)
- `500` - Internal server error

### Never Do This

```python
# BANNED - leaking internal details
handler._send_text("Database error: Connection to db-server-01 refused", 500)

# BANNED - no error body
handler.send_error(404)
```

## 7. Frontend Decoder/Classname Policy

### Requirement

Never construct class names or identifiers from raw payload data without validation.

### Banned Pattern

```python
# BANNED - direct class name from payload
class_name = f"Panel-{payload.get('type')}"
element.className = class_name

# BANNED - unvalidated data in class
element.className = f"status-{raw_value}"
```

### Safe Pattern

```python
# GOOD - validated value mapped to safe class
ALLOWED_STATUS_CLASSES = {"success": "status-ok", "warning": "status-warn", "error": "status-err"}
raw = payload.get("status", "")
safe_status = raw if raw in ALLOWED_STATUS_CLASSES else "unknown"
element.className = ALLOWED_STATUS_CLASSES.get(safe_status, "status-unknown")
```

## 8. Required Tests

For each security-sensitive function, tests must verify:

### Identifier Validation

- [ ] Valid run IDs are accepted (existing patterns: `run-test-123`, `my_run`)
- [ ] Path traversal strings are rejected (`../etc`, `..`, `/etc`)
- [ ] Absolute paths are rejected (`/tmp/file`, `C:\Windows`)
- [ ] Glob metacharacters are rejected (`*`, `?`, `[`, `]`, `{`, `}`)
- [ ] Null bytes are rejected
- [ ] Empty strings are rejected
- [ ] Invalid run_id returns typed error

### Path Containment

- [ ] Safe path returns expected result
- [ ] Path traversal is blocked with SecurityError
- [ ] Absolute paths are blocked with SecurityError
- [ ] Glob metacharacters are blocked with SecurityError

### API Errors

- [ ] Invalid input returns 400 with structured error
- [ ] Missing resource returns 404
- [ ] Server errors do not leak internal details

## 9. Secrets Logging Policy

### Never Log

The following **must never** appear in logs (structured or unstructured):
- Bearer tokens
- Kubeconfig contents
- Request bodies (may contain secrets)
- Raw artifact payloads (may contain secrets)
- Passwords or API keys
- Secret manifests

### Allowed Logging

- Run IDs and artifact IDs (not the content)
- Timing metrics
- Error types (not error messages that may contain secrets)
- Structured sanitized metadata

## 10. Remaining Phases

This baseline establishes the foundation. Future hardening phases will address:

1. **Phase 2**: Audit existing glob usages beyond next-check-plan
2. **Phase 3**: Apply validation to all user-controlled identifiers
3. **Phase 4**: Convert remaining bare `except Exception:` handlers
4. **Phase 5**: Audit subprocess calls for stderr=DEVNULL
5. **Phase 6**: Add integration tests with security fixtures
