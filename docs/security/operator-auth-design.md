# Operator Authentication Design (API-R3)

**Date**: 2026-05-06
**Parent Risk**: AU-03 - "No authentication layer on POST mutation endpoints"
**Related Controls**: INV-1 (UI Server Network Binding), API-R1 (Content-Type validation), API-R2 (Origin/Referer guard)
**Status**: Design Document - Implementation Pending

---

## 1. Context and Problem Statement

### 1.1 Current State

From AU-03 audit findings:
- **Default bind**: `127.0.0.1:8080` (localhost-only) ✅
- **CLI startup**: `--host` defaults to `127.0.0.1` in `cli.py`
- **Helm chart**: `HEALTH_UI_HOST: "0.0.0.0"` - binds to all interfaces
- **API-R1**: Content-Type + 1 MiB size limit implemented ✅
- **API-R2**: Origin/Referer CSRF guard implemented ✅
- **Auth layer**: None ❌

### 1.2 Identified Risk

> **RISK-05 (HIGH)**: "Unauthorized cluster mutations via API"
> Any client that can reach the server can mutate state.

**Exposure vectors**:
1. Helm deployment binds to `0.0.0.0:8080` - network-accessible
2. Operator explicitly binds to non-localhost for access from other machines
3. Misconfigured network (pod accessible outside cluster)

### 1.3 Constraints

From AGENTS.md and architecture doctrine:
- **localhost-first operator workflow**: Primary use case is local access
- **modular monolith**: Avoid introducing heavyweight auth services
- **minimal complexity for local dev**: Must not break `python -m k8s_diag_agent health-ui`
- **staged evolution**: Design for incremental implementation
- **conservative with causality**: Don't over-engineer for hypothetical multi-user scenarios

---

## 2. Deployment Model Inventory

### 2.1 Current Bind Address Patterns

| Deployment Mode | Default Host | Port | Network Exposure | Auth Required |
|-----------------|-------------|------|-----------------|---------------|
| CLI local dev | `127.0.0.1` | 8080 | Localhost only | None (safe) |
| Helm production | `0.0.0.0` | 8080 | Cluster-wide | **YES** |
| Docker compose | Configurable | 8080 | Depends on config | Depends |
| Port-forward access | `127.0.0.1` | Dynamic | Localhost via tunnel | None (safe) |

### 2.2 CLI Startup Options

From `src/k8s_diag_agent/cli.py` lines 271-288:
```python
ui_parser.add_argument("--host", default="127.0.0.1", help="Host address to bind the UI server.")
ui_parser.add_argument("--port", type=_positive_int, default=8080, help="Port to listen for operator UI requests.")
```

**Current behavior**: Defaults to localhost ✅
**Gap**: No warning or protection when binding to non-loopback

### 2.3 Helm Chart Values

From `charts/k9b/values.yaml` lines 18-22:
```yaml
backend:
  env:
    HEALTH_UI_HOST: "0.0.0.0"  # PROBLEM: binds to all interfaces
    HEALTH_UI_PORT: "8080"
```

**Current behavior**: Binds to all interfaces in Kubernetes
**Gap**: No auth token configuration option

### 2.4 Server Entry Point

From `src/k8s_diag_agent/ui/server.py` lines 613-636:
```python
def start_ui_server(
    runs_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8080,
    static_dir: Path | None = None,
) -> None:
```

---

## 3. Authentication Model Evaluation

### 3.1 Option A: Localhost-Only with Unsafe-Expose Mode

**Description**: Keep localhost binding as the only safe option. Any non-localhost binding requires explicit `--unsafe-bind` flag and prints security warning.

| Aspect | Assessment |
|--------|------------|
| **Security Value** | HIGH - Makes accidental exposure explicit |
| **Operator UX** | LOW - Additional flag required for remote access |
| **CI/Test Impact** | LOW - No changes needed |
| **Helm Impact** | MEDIUM - Must change default to 127.0.0.1 or require --unsafe-bind |
| **Local Dev Compatibility** | HIGH - Default works unchanged |
| **GET Protection** | No (only enforces explicit opt-in for exposure) |
| **POST Protection** | No (only enforces explicit opt-in for exposure) |
| **Failure Modes** | None - safe by default |

**Pros**:
- Zero-config for local development
- Makes network exposure explicit and intentional
- Low implementation complexity

**Cons**:
- Operators needing remote access must enable unsafe mode
- No protection if unsafe mode is enabled
- Doesn't solve the helm chart `0.0.0.0` problem

### 3.2 Option B: Shared Bearer Token

**Description**: Configure a static token via environment variable. All mutation endpoints require `Authorization: Bearer <token>` header.

| Aspect | Assessment |
|--------|------------|
| **Security Value** | MEDIUM - Protects against casual access |
| **Operator UX** | MEDIUM - Token must be configured and passed |
| **CI/Test Impact** | MEDIUM - Tests need token configured |
| **Helm Impact** | HIGH - Must add secret/token configuration |
| **Local Dev Compatibility** | MEDIUM - Requires env var setup |
| **GET Protection** | Optional |
| **POST Protection** | Yes (primary) |
| **Failure Modes** | Token in logs, token rotation complexity |

**Pros**:
- Simple implementation
- Works with curl/cli tools
- Standard pattern

**Cons**:
- Static token in env var (secrets management concern)
- No revocation without redeployment
- Token printed in startup message risk
- Doesn't integrate with existing cluster auth

### 3.3 Option C: Randomly Generated Startup Token

**Description**: Generate a random token at startup, print to console. Client must use token from startup log.

| Aspect | Assessment |
|--------|------------|
| **Security Value** | LOW - Token visible in logs/terminal |
| **Operator UX** | LOW - Must copy token from logs |
| **CI/Test Impact** | HIGH - No stable token for tests |
| **Helm Impact** | MEDIUM - Token regenerated each pod restart |
| **Local Dev Compatibility** | LOW - Inconvenient for local dev |
| **GET Protection** | Optional |
| **POST Protection** | Yes |
| **Failure Modes** | Token rotation on restart, log access required |

**Pros**:
- No pre-configuration required
- Token tied to specific server instance

**Cons**:
- Token appears in logs (security risk)
- Different token on each restart (usability issue)
- CI/test automation difficult
- Not suitable for production

### 3.4 Option D: Env-Configured Operator Token

**Description**: Token read from `K9B_UI_TOKEN` environment variable. Generated by operator or deployment tooling.

| Aspect | Assessment |
|--------|------------|
| **Security Value** | MEDIUM-HIGH - Token managed by operator |
| **Operator UX** | MEDIUM - Requires env var setup |
| **CI/Test Impact** | MEDIUM - Tests need token in env |
| **Helm Impact** | HIGH - Kubernetes Secret integration |
| **Local Dev Compatibility** | MEDIUM - Simple env var |
| **GET Protection** | Optional |
| **POST Protection** | Yes |
| **Failure Modes** | Missing env var behavior (deny-all vs allow-all) |

**Pros**:
- Operator controls token generation
- Works with Kubernetes Secrets
- Stable across restarts
- Supports token rotation

**Cons**:
- Requires secret management infrastructure
- Startup failure if token missing (unless allow-no-auth)
- More complex than localhost-only

### 3.5 Option E: Reverse-Proxy Auth

**Description**: No built-in auth. Authenticate at reverse proxy layer (nginx, traefik, ambassador) before requests reach k9b.

| Aspect | Assessment |
|--------|------------|
| **Security Value** | HIGH - Mature auth solutions |
| **Operator UX** | MEDIUM - Standard proxy config |
| **CI/Test Impact** | LOW - Direct access for tests |
| **Helm Impact** | LOW - Ingress with auth annotation |
| **Local Dev Compatibility** | HIGH - No changes for local |
| **GET Protection** | Yes (via proxy) |
| **POST Protection** | Yes (via proxy) |
| **Failure Modes** | Proxy misconfiguration, proxy downtime |

**Pros**:
- Leverages existing infrastructure
- Supports SSO, OIDC, mTLS via proxy
- No code changes to k9b
- Works with cluster ingress

**Cons**:
- Requires reverse proxy deployment
- Documentation-heavy
- Proxy becomes security-critical
- Local dev needs proxy for full auth testing

### 3.6 Option F: mTLS

**Description**: Mutual TLS authentication. Both client and server present certificates.

| Aspect | Assessment |
|--------|------------|
| **Security Value** | HIGH - Strong authentication |
| **Operator UX** | LOW - Certificate management burden |
| **CI/Test Impact** | HIGH - Certificate setup for tests |
| **Helm Impact** | MEDIUM - Certificate Secret integration |
| **Local Dev Compatibility** | LOW - Dev cert setup required |
| **GET Protection** | Yes |
| **POST Protection** | Yes |
| **Failure Modes** | Cert expiration, rotation complexity |

**Pros**:
- Strong authentication
- No password/token to leak
- Works with Kubernetes SPIFFE/SPIRE

**Cons**:
- Complex certificate management
- Overkill for single-operator local workflow
- Not practical for localhost-first use case

### 3.7 Option G: No Built-In Auth + Documentation

**Description**: Acknowledge localhost-only assumption. Document hard requirement for reverse proxy in production.

| Aspect | Assessment |
|--------|------------|
| **Security Value** | LOW - Relies entirely on network isolation |
| **Operator UX** | HIGH - No changes |
| **CI/Test Impact** | LOW - No changes |
| **Helm Impact** | LOW - Documentation only |
| **Local Dev Compatibility** | HIGH - No changes |
| **GET Protection** | No |
| **POST Protection** | No |
| **Failure Modes** | Network isolation failure = complete exposure |

**Pros**:
- Zero implementation cost
- Preserves current behavior

**Cons**:
- Doesn't address RISK-05
- Helm chart binds to all interfaces
- No protection if exposed

### 3.8 Option H: Kubernetes ServiceAccount + RBAC

**Description**: Authenticate requests using Kubernetes service account tokens. RBAC controls access to mutation endpoints.

| Aspect | Assessment |
|--------|------------|
| **Security Value** | HIGH - Native K8s integration |
| **Operator UX** | MEDIUM - Cluster access required |
| **CI/Test Impact** | MEDIUM - Token in pod |
| **Helm Impact** | LOW - Automatic SA token mount |
| **Local Dev Compatibility** | LOW - Requires cluster |
| **GET Protection** | Yes (RBAC) |
| **POST Protection** | Yes (RBAC) |
| **Failure Modes** | SA token exposure, RBAC misconfiguration |

**Pros**:
- Native Kubernetes authentication
- RBAC for fine-grained access control
- Token auto-rotated by K8s

**Cons**:
- Doesn't work outside cluster
- UI server needs pod-level permissions
- Complex for local development
- Not suitable for standalone operator workstation

---

## 4. Recommended Auth Model

### 4.1 Tiered Approach

Based on the analysis and constraints (localhost-first, modular monolith, staged evolution):

**Tier 1: Localhost-Safe Default** (Immediate)
- Keep default bind as `127.0.0.1`
- Add `--unsafe-bind` flag for explicit non-loopback binding
- Print security warning when binding to non-loopback without auth

**Tier 2: Optional Bearer Token Auth** (Next Sprint)
- Add `K9B_UI_TOKEN` environment variable support
- Token optional (only required when exposed)
- Bearer token on all POST endpoints
- GET endpoints remain unprotected (consistent with current scope)

**Tier 3: Production Documentation** (Parallel)
- Document reverse-proxy auth as production requirement
- Update Helm chart README with ingress + auth annotation examples
- Add security hardening section to deployment docs

### 4.2 Rejected Alternatives

| Option | Reason for Rejection |
|--------|---------------------|
| **Option C (Startup Token)** | Token in logs is security risk; restart rotation breaks automation |
| **Option F (mTLS)** | Overkill for localhost-first; cert management burden |
| **Option G (No Auth + Docs)** | Doesn't address RISK-05; helm chart still binds to 0.0.0.0 |
| **Option H (K8s SA/RBAC)** | Doesn't work for standalone workstation use case |

### 4.3 Deferred Decisions

| Decision | Deferred To | Rationale |
|----------|-------------|-----------|
| GET endpoint protection | Tier 2 or 3 | POST mutation risk is primary concern; GET is read-only |
| CSRF token validation | API-R2 covers Origin/Referer | Full CSRF tokens add complexity; browser CORS already protected |
| Multi-user auth | Future | Single-operator is current assumption; not in scope |

---

## 5. Implementation Plan

### 5.1 Phase 1: Unsafe-Bind Protection (Low Effort)

**Files to modify**:
- `src/k8s_diag_agent/cli.py` - Add `--unsafe-bind` flag
- `src/k8s_diag_agent/ui/server.py` - Accept auth config, print warnings
- `src/k8s_diag_agent/cli_handlers.py` - Pass auth config to server

**Changes**:
```python
# cli.py
ui_parser.add_argument("--unsafe-bind", action="store_true", 
    help="Allow non-localhost binding (DANGEROUS without --auth-token)")

# server.py
def start_ui_server(
    runs_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8080,
    static_dir: Path | None = None,
    auth_token: str | None = None,
    unsafe_bind: bool = False,
) -> None:
    # Warn if binding to non-loopback without token
    if host not in ("127.0.0.1", "localhost", "::1") and not unsafe_bind:
        print("WARNING: Binding to non-localhost address without --unsafe-bind", file=sys.stderr)
```

### 5.2 Phase 2: Bearer Token Support (Medium Effort)

**Files to modify**:
- `src/k8s_diag_agent/ui/server_shared.py` - Add token validation helper
- `src/k8s_diag_agent/ui/server.py` - Integrate token check into POST handlers
- `src/k8s_diag_agent/security/__init__.py` - Optional auth module

**Changes**:
```python
# server_shared.py
def _validate_bearer_token(handler, expected_token: str | None) -> bool:
    """Validate Bearer token if configured."""
    if not expected_token:
        return True  # No auth required
    auth_header = handler.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        handler._send_json({"error": "Authorization required"}, 401)
        return False
    token = auth_header[7:]  # Strip "Bearer "
    if token != expected_token:
        handler._send_json({"error": "Invalid token"}, 401)
        return False
    return True
```

**Integration point**: Call from `_validate_json_mutation_request()` or add to `do_POST()` before route dispatch.

### 5.3 Phase 3: Helm Chart Updates (Documentation)

**Files to modify**:
- `charts/k9b/values.yaml` - Add auth.token example
- `charts/k9b/README.md` - Add security hardening section

**Changes**:
```yaml
# values.yaml additions
ui:
  auth:
    token:
      # enabled: true
      # valueFrom: {}  # Secret reference
```

---

## 6. Configuration Surface

### 6.1 Environment Variables

| Variable | Purpose | Default | Required When |
|----------|---------|---------|---------------|
| `K9B_UI_TOKEN` | Bearer token for mutation auth | None | Binding to non-localhost |
| `K9B_UI_HOST` | Bind address | `127.0.0.1` | Changing bind address |
| `K9B_UI_PORT` | Listen port | `8080` | Changing port |

### 6.2 CLI Flags

| Flag | Purpose | Default |
|------|---------|---------|
| `--host` | Bind address | `127.0.0.1` |
| `--port` | Listen port | `8080` |
| `--unsafe-bind` | Allow non-localhost without token | `False` |
| `--auth-token` | Set bearer token (cli only) | From env |

### 6.3 Helm Values

| Value | Purpose | Default |
|-------|---------|---------|
| `ui.host` | Bind address | `127.0.0.1` |
| `ui.port` | Listen port | `8080` |
| `ui.auth.token.enabled` | Enable token auth | `false` |
| `ui.auth.token.existingSecret` | Secret name for token | `""` |

---

## 7. Test Plan

### 7.1 Unit Tests

| Test | Description | Expected Result |
|------|-------------|-----------------|
| `test_localhost_bind_no_warning` | Server starts on 127.0.0.1 without warning | No warning printed |
| `test_unsafe_bind_warning` | Server starts with --unsafe-bind on non-loopback | Warning printed |
| `test_token_validation_valid` | Request with valid Bearer token | 2xx response |
| `test_token_validation_missing` | Request without token when required | 401 response |
| `test_token_validation_invalid` | Request with invalid token | 401 response |
| `test_token_not_required_localhost` | Request without token on localhost | 2xx response |

### 7.2 Integration Tests

| Test | Description | Expected Result |
|------|-------------|-----------------|
| `test_mutation_without_token_rejected` | POST to exposed server without token | 401 Unauthorized |
| `test_mutation_with_valid_token` | POST to exposed server with valid token | 2xx response |
| `test_mutation_with_invalid_token` | POST to exposed server with wrong token | 401 Unauthorized |

### 7.3 Security Tests

| Test | Description | Expected Result |
|------|-------------|-----------------|
| `test_token_not_in_logs` | Verify token value not in startup logs | Token not logged |
| `test_token_not_in_error_messages` | Error messages don't leak token | Token masked in errors |
| `test_replay_attack_prevented` | Same token used twice | Both requests succeed (stateless OK) |

---

## 8. Rollout and Backward Compatibility

### 8.1 Backward Compatibility

| Scenario | Behavior | Migration Path |
|----------|----------|----------------|
| Existing CLI users | No change (localhost default) | None needed |
| Existing helm deployments | Continue working (no auth enabled) | Optional upgrade to add token |
| CI/test automation | Continue working (localhost) | None needed |
| Production (no token) | Unsafe mode required | Add warning, not breakage |

### 8.2 Migration Path

1. **Before**: Helm chart binds to `0.0.0.0` with no warning
2. **Phase 1**: Add `--unsafe-bind` flag and warning; helm default unchanged
3. **Phase 2**: Add token support; helm chart unchanged
4. **Phase 3**: Update helm default to `127.0.0.1` with unsafe-bind required for `0.0.0.0`

### 8.3 Breaking Changes

None in Phase 1 and 2:
- Localhost-first behavior preserved
- No token required by default
- Existing deployments continue working

Potential breaking change (Phase 3):
- Helm default change to `127.0.0.1` (can be reverted via values)

---

## 9. Implementation Backlog

### Priority 1 (Immediate)

| ID | Task | Effort | Files | Status |
|----|------|--------|-------|--------|
| AUTH-01 | Add `--unsafe-bind` flag to CLI | Low | cli.py | **DONE** |
| AUTH-02 | Add bind warning when exposing without token | Low | server.py | **DONE** |
| AUTH-03 | Update api-security-audit.md with AUTH-01/02 | Low | docs/ | **DONE** |

### Priority 2 (Next Sprint)

| ID | Task | Effort | Files | Status |
|----|------|--------|-------|--------|
| AUTH-04 | Add `_validate_bearer_token()` helper | Low | server_shared.py | **DONE** |
| AUTH-05 | Integrate token validation into do_POST() | Medium | server.py | **DONE** |
| AUTH-06 | Add unit tests for token validation | Low | tests/ | **DONE** |
| AUTH-07 | Update Helm chart README with auth docs | Low | charts/ | **DONE** |

### Priority 3 (Deferred)

| ID | Task | Effort | Files | Status |
|----|------|--------|-------|--------|
| AUTH-08 | GET endpoint protection (decision deferred) | TBD | TBD | DEFERRED |
| AUTH-09 | Full CSRF token (deferred, API-R2 sufficient) | TBD | TBD | DEFERRED |
| AUTH-10 | Helm default to 127.0.0.1 | Medium | charts/ | OPEN |

---

## 10. Verification

### 10.1 Verification Commands

```bash
# Run security-related tests
.venv/bin/python -m pytest tests/test_security_path_validation.py -v

# Verify ruff passes on auth-related files
.venv/bin/ruff check src/k8s_diag_agent/ui/server*.py --select=E,F,I

# Manual verification
python -m k8s_diag_agent health-ui --host 127.0.0.1 --port 8080
# Should start without warnings

python -m k8s_diag_agent health-ui --host 0.0.0.0 --unsafe-bind --port 8080
# Should print warning about unsafe binding

# Token validation test (requires K9B_UI_TOKEN set)
K9B_UI_TOKEN=test-token python -m k8s_diag_agent health-ui --host 0.0.0.0 --port 8080
curl -X POST http://localhost:8080/api/next-check-approval -H "Content-Type: application/json" -d '{}'
# Should return 401 without Authorization header
```

### 10.2 Success Criteria

1. **docs/security/operator-auth-design.md exists** ✅ (this document)
2. **CLI defaults to localhost** - Verified in cli.py
3. **Unsafe-bind flag exists** - Pending AUTH-01
4. **Warning printed for non-localhost** - Pending AUTH-02
5. **Bearer token validation works** - Pending AUTH-04-05
6. **Unit tests pass** - Pending AUTH-06
7. **No behavior change without code changes** - Default localhost preserved

---

## 11. Related Documents

| Document | Relationship |
|----------|--------------|
| `docs/security/api-security-audit.md` | Parent audit (AU-03) |
| `docs/security/threat-model.md` | RISK-05 documented here |
| `src/k8s_diag_agent/ui/server.py` | Implementation target |
| `src/k8s_diag_agent/ui/server_shared.py` | Shared validation helpers |
| `charts/k9b/values.yaml` | Helm configuration |

---

## 12. Open Questions

| ID | Question | Impact | Blocking |
|----|---------|--------|----------|
| Q1 | Should non-loopback binding require explicit `--unsafe-bind`, including Helm deployments? | Affects helm chart migration | YES |
| Q2 | Should GET endpoints also require token when exposed? | Affects scope | NO |
| Q3 | Should we support token via Kubernetes Secret in helm? | Affects helm implementation | NO |
| Q4 | What is the expected token format? (random hex, JWT, etc.) | Affects implementation | YES |

---

**Document End**