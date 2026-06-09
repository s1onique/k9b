# Discovery Logging Hygiene Doctrine

**Purpose:** Prevent accidental information leakage through raw Kubernetes discovery error logging.

**Status:** Active doctrine for all discovery strategy files.

**Scope:** `src/k8s_diag_agent/external_analysis/*discovery*strategy*.py`

---

## Core Rule

> **Discovery fallback logs are operator-facing security surfaces.**
>
> Raw kubectl/API error text must never appear in logger calls.

Discovery code runs in environments where:
- Operators may not have cluster admin access
- RBAC constraints are intentional and expected
- Namespace and resource names are sensitive
- Service account identity reveals deployment topology

Logging raw errors can leak:
- namespace names
- resource names
- RBAC policy hints
- service account identity
- cluster topology
- stderr fragments
- stack traces

---

## Forbidden Patterns

The following patterns are forbidden in discovery strategy files:

| Pattern | Why Forbidden |
|---------|---------------|
| `_logger.warning(...)` | Raw warning logs can leak sensitive error text |
| `exc_info=True` | Exception tracebacks expose internal state |
| `stderr` in logger calls | Raw subprocess stderr leaks API response details |

### 1. `_logger.warning(...)` — Forbidden

```python
# BAD - leaks error text
_logger.warning("kubectl failed: %s", result.stderr)

# GOOD - structured, sanitized event
log_discovery_failure(
    logger=_logger,
    event=DiscoveryEvent.CRD_NOT_FOUND,
    context=context_name,
    detail="forbidden",
)
```

### 2. `exc_info=True` — Forbidden

```python
# BAD - traceback leaks internal state
_logger.error("Discovery failed", exc_info=True)

# GOOD - no traceback, structured message only
_logger.error("Discovery step failed: step=crd_list")
```

### 3. Raw `stderr` in logger calls — Forbidden

```python
# BAD - leaks API response details
_logger.debug("Command failed: %s", result.stderr)

# GOOD - sanitized event without raw output
_logger.debug("kubectl command failed during discovery step=%s", "service_list")
```

---

## Allowed Patterns

The following are permitted:

- `_logger.debug(...)` — without `exc_info` or raw `stderr`
- `_logger.info(...)` — structured messages only
- `_logger.error(...)` — without `exc_info`, structured messages only

### Structured Event Example

```python
from k8s_diag_agent.external_analysis.discovery_structured_logging import (
    DiscoveryEvent,
    log_discovery_failure,
)

# GOOD - structured, sanitized event
log_discovery_failure(
    logger=_logger,
    event=DiscoveryEvent.CRD_NOT_FOUND,
    context=context_name,
    detail="forbidden",
)
```

The structured logging module provides sanitized event types that:
- Never include raw error text
- Never include stderr or stdout
- Never include stack traces
- Use enumerated event types for correlation

---

## Why Forbidden/RBAC Failures Are Expected

Discovery fallbacks exist precisely because:

1. **RBAC is intentional** — Users configure permissions deliberately
2. **Not exceptional** — Forbidden errors are operational, not exceptional
3. **Not actionable** — A traceback doesn't help the operator

Logging raw RBAC failures would expose:
- Which permissions are missing
- Cluster RBAC policy structure
- Service account capabilities

This information could assist unauthorized enumeration.

---

## Enforced By

This doctrine is enforced via:

- **Gate:** `scripts/verify_discovery_logging_hygiene.py`
- **Tests:** `tests/unit/test_discovery_logging_hygiene.py`

Run verification:
```bash
python scripts/verify_discovery_logging_hygiene.py
python -m pytest tests/unit/test_discovery_logging_hygiene.py
```

---

## Verifier Scope

The verifier scans files matching:
- `src/k8s_diag_agent/external_analysis/*discovery*strategy*.py`
- `src/k8s_diag_agent/external_analysis/*strategy*discovery*.py`

The verifier is intentionally narrow and deterministic:
- Does not scan all Python files
- Does not check logging configuration
- Does not validate structured logging module usage

---

## Relationship to Other Doctrine

- Complement to `identity-primer.md` for auth/authz sensitivity
- Complement to `path-security-doctrine.md` for security surface hygiene
- Discovery errors are signals, not actionable tracebacks

---

## Change Policy

This doctrine changes only when:
- New leakage vector is identified
- Structured logging API changes materially
- Discovery scope expands beyond current files

Do not change for:
- Temporary workarounds
- Convenience logging
- Debugging overrides
