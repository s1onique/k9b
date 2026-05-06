# API Security Audit (AU-03)

**Date**: 2026-05-06
**Scope**: k9b UI server (`src/k8s_diag_agent/ui/`)
**Objective**: Audit mutation surfaces, authorization assumptions, CSRF risks, and trust boundaries

---

## 1. Route Inventory

### 1.1 Read-Only Routes (GET)

| Method | Path | Handler | Request Params | Notes |
|--------|------|---------|----------------|-------|
| GET | `/api/runs` | `server_reads.handle_api` | `limit`, `include_status`, `include_expensive` | Returns runs list with optional batch eligibility |
| GET | `/api/notifications` | `server_reads.handle_api` | `kind`, `cluster_label`, `search`, `limit`, `page` | Notification query with caching |
| GET | `/api/run` | `server_reads.handle_api` | `run_id` (query param) | Full run payload, uses mtime-based caching |
| GET | `/api/fleet` | `server_reads.handle_api` | (none) | Fleet-level summary |
| GET | `/api/proposals` | `server_reads.handle_api` | (none) | Proposal status summary |
| GET | `/api/cluster-detail` | `server_reads.handle_api` | `cluster_label` (query param) | Cluster detail view |
| GET | `/` | `server_static.serve_static` | (path-based) | Static file serving from `frontend/dist` |
| GET | `/artifact` | `server_static.serve_artifact` | `path` (query param) | Artifact download with path validation |

### 1.2 Mutation Routes (POST)

| Method | Path | Handler | Request Body | Side Effects |
|--------|------|---------|--------------|--------------|
| POST | `/api/deterministic-next-check/promote` | `server_next_checks.handle_deterministic_promotion` | `clusterLabel`, `description`, `workstream`, `urgency`, `whyNow`, `topProblem`, `method`, `evidenceNeeded`, `priorityScore`, `context` | Writes promotion artifact, may touch ui-index |
| POST | `/api/next-check-execution` | `server_next_checks.handle_next_check_execution` | `candidateIndex`, `candidateId`, `clusterLabel`, `planArtifactPath` | Executes diagnostic command, writes execution artifact, refreshes diagnostic pack |
| POST | `/api/next-check-approval` | `server_next_checks.handle_next_check_approval` | `candidateIndex`, `candidateId`, `clusterLabel` | Writes approval artifact |
| POST | `/api/next-check-execution-usefulness` | `server_feedback.handle_usefulness_feedback` | `artifactPath`, `usefulnessClass`, `usefulnessSummary`, optional stage/context fields | Writes usefulness review artifact |
| POST | `/api/alertmanager-relevance-feedback` | `server_feedback.handle_alertmanager_relevance_feedback` | `artifactPath`, `alertmanagerRelevance`, `alertmanagerRelevanceSummary` | Writes Alertmanager relevance review artifact |
| POST | `/api/run-batch-next-check-execution` | `server._handle_run_batch_next_check_execution` | `runId`, `dryRun` | Batch execution of eligible candidates, writes execution artifacts |
| POST | `/api/runs/{run_id}/alertmanager-sources/{source_id}/action` | `server_alertmanager.handle_alertmanager_source_action` | `action` (`promote`/`disable`), `reason`, `clusterLabel` | Writes override artifact, updates registry |

---

## 2. Trust Boundaries

### 2.1 Network Trust Boundary

- **Default bind**: `127.0.0.1:8080` (localhost-only)
- **Configurable**: `start_ui_server(host, port, static_dir)` allows binding to other addresses
- **Assumption**: Server is not exposed directly to untrusted networks when using defaults

### 2.2 Artifact Path Trust

- Artifact paths from requests are validated via `runs_dir.resolve()` containment check
- `server_static.serve_artifact()`: validates `str(artifact_path).startswith(str(runs_dir.resolve()))`
- `server_feedback`: validates `(handler.runs_dir / artifact_path_rel).resolve()` is within `runs_dir`
- **Risk**: Path validation happens *after* path construction; malformed paths may cause exceptions

### 2.3 Run ID Trust

- `validate_run_id()` is called in:
  - `server_next_checks.find_candidate_in_all_plan_artifacts()`
  - `server_reads._build_external_analysis_count()` (via `safe_run_artifact_glob`)
  - `server_next_checks` module-level imports
- **Status**: Path traversal protection exists via regex + traversal check

### 2.4 Content-Type Handling

- **API-R1 implemented**: `_validate_json_mutation_request()` in `server_shared.py`
- Requires `Content-Type: application/json` (accepts charset parameter)
- Rejects missing/empty Content-Type with 415 Unsupported Media Type
- Rejects non-JSON Content-Types (text/plain, form-urlencoded, multipart) with 415
- All mutation handlers use shared validation helper for consistency

---

## 3. Mutation Endpoint Analysis

### 3.1 `/api/next-check-execution`

| Attribute | Status | Notes |
|-----------|--------|-------|
| Authn/Authz | None | Assumes localhost-only deployment |
| CSRF | Vulnerable | No CSRF token; state-changing GET also missing |
| Content-Type | Implicit JSON | No explicit validation |
| Field Validation | Partial | `candidateIndex` must be int; `clusterLabel` required; `candidateId` optional |
| run_id/Path | From context | `run_id` from `_load_context()`, not from request body |
| planArtifactPath | Optional, validated | Falls back to index path if invalid |
| Idempotency | Not enforced | Re-execution writes new artifact with new artifact_path |
| Audit Logging | Structured | Emits `next-check-execution` component logs |
| Failure Behavior | 400/500 | Returns JSON error; may leave partial state |

**Findings**:
- No authentication/authorization layer
- No CSRF protection (no token, no SameSite cookie, no Origin check)
- Path resolution has fallback behavior that could mask input errors

### 3.2 `/api/next-check-approval`

| Attribute | Status | Notes |
|-----------|--------|-------|
| Authn/Authz | None | Same as above |
| CSRF | Vulnerable | No CSRF protection |
| Content-Type | Implicit JSON | No explicit validation |
| Field Validation | Partial | `candidateIndex` must be int; `clusterLabel` required |
| Idempotency | Partial | `FileExistsError` on duplicate artifact write (409) |
| Audit Logging | Structured | `log_next_check_approval_event()` for requested/rejected |
| Failure Behavior | 400/500 | Returns JSON error |

**Findings**:
- Same auth/authz gaps as execution endpoint
- Idempotency handled at artifact write level (FileExistsError)

### 3.3 `/api/deterministic-next-check/promote`

| Attribute | Status | Notes |
|-----------|--------|-------|
| Authn/Authz | None | No auth |
| CSRF | Vulnerable | No CSRF protection |
| Content-Type | Implicit JSON | No explicit validation |
| Field Validation | Partial | `clusterLabel` and `description` required; other fields optional |
| clusterLabel | Validated | Checks existence in `context.clusters` |
| Idempotency | Yes | 409 on duplicate candidate_id |
| Audit Logging | Yes | `logger.info()` for promotion events |

**Findings**:
- Cluster label validation prevents promoting to non-existent clusters
- Duplicate detection via candidate_id hash (409 Conflict)

### 3.4 `/api/next-check-execution-usefulness`

| Attribute | Status | Notes |
|-----------|--------|-------|
| Authn/Authz | None | No auth |
| CSRF | Vulnerable | No CSRF protection |
| Content-Type | Implicit JSON | No explicit validation |
| Field Validation | Full | `artifactPath` required, `usefulnessClass` must be enum (`useful`/`partial`/`noisy`/`empty`) |
| Path Validation | Yes | Resolves and checks containment in `runs_dir` |
| Artifact Exists Check | Yes | 404 if execution artifact not found |
| Idempotency | No | Each feedback creates new review artifact (UUID) |
| Audit Logging | Partial | `logger.info()` without summary field |

**Findings**:
- Best validated mutation endpoint (enum validation, path containment, artifact existence)
- No idempotency (each POST creates new artifact)

### 3.5 `/api/alertmanager-relevance-feedback`

| Attribute | Status | Notes |
|-----------|--------|-------|
| Authn/Authz | None | No auth |
| CSRF | Vulnerable | No CSRF protection |
| Content-Type | Implicit JSON | No explicit validation |
| Field Validation | Full | `artifactPath` required, `alertmanagerRelevance` must be enum |
| Path Validation | Yes | Resolves and checks containment in `runs_dir` |
| Artifact Exists Check | Yes | 404 if execution artifact not found |
| Provenance | Server-owned | Reads from execution artifact, not from request |
| Idempotency | No | Each feedback creates new review artifact (UUID) |

**Findings**:
- Provenance integrity: reads from execution artifact, not client-supplied
- Same gaps as usefulness endpoint

### 3.6 `/api/run-batch-next-check-execution`

| Attribute | Status | Notes |
|-----------|--------|-------|
| Authn/Authz | None | No auth |
| CSRF | Vulnerable | No CSRF protection |
| Content-Type | Implicit JSON | No explicit validation |
| Field Validation | Partial | `runId` required; `dryRun` defaults to False |
| runId | Validated | Passed to `run_batch_next_checks()` which may validate |
| Idempotency | Partial | Individual candidates may be skipped if already executed |
| Audit Logging | Yes | Structured logs for parse, execution, result |
| Failure Behavior | Partial | Continues on individual failures, reports counts |

**Findings**:
- `dryRun` defaults to `False` (actual execution if omitted)
- Risk: malformed `runId` may cause unexpected failures

### 3.7 `/api/runs/{run_id}/alertmanager-sources/{source_id}/action`

| Attribute | Status | Notes |
|-----------|--------|-------|
| Authn/Authz | None | No auth |
| CSRF | Vulnerable | No CSRF protection |
| Content-Type | Implicit JSON | No explicit validation |
| Field Validation | Full | `action` must be `promote`/`disable`; `clusterLabel` required |
| Path Params | Partial | `source_id` URL-decoded and used in validation |
| sourceId Mismatch | Checked | Body `sourceId` must match path `source_id` |
| State Validation | Yes | Checks `can_promote`/`can_disable` before action |
| Idempotency | Partial | Overwrites existing override; no error on re-apply |
| Audit Logging | Yes | `logger.info()` for promote/disable actions |
| Failure Behavior | Partial | Override write is fatal; registry write is non-fatal (warning only) |

**Findings**:
- Strong validation of action against current source state
- Non-fatal failures logged but don't fail the request

---

## 4. Risk Table

| Risk | Severity | Affected Endpoints | Mitigation Status |
|------|----------|---------------------|-------------------|
| No authentication layer | HIGH | All POST endpoints | OPEN (assumes localhost-only) |
| No CSRF protection | HIGH | All POST endpoints | OPEN |
| CSRF on state-changing GET | MEDIUM | `/api/run?run_id=X` (cache invalidation) | OPEN |
| Path traversal via artifactPath | HIGH | Feedback endpoints | MITIGATED (containment check) |
| Path traversal via planArtifactPath | MEDIUM | Execution endpoint | MITIGATED (fallback to index) |
| run_id not validated in batch | MEDIUM | Batch execution | OPEN (depends on downstream) |
| Content-Type not enforced | LOW | All mutation endpoints | **MITIGATED by API-R1** |
| No rate limiting | MEDIUM | All endpoints | OPEN |
| **Request size limits** | MEDIUM | All mutation endpoints | **MITIGATED by API-R1 (1 MiB)** |
| No audit trail for reads | LOW | GET endpoints | OPEN |

---

## 5. Existing Controls

1. **Path containment validation**: `runs_dir.resolve()` containment checks prevent path traversal
2. **run_id validation**: `validate_run_id()` + `safe_run_artifact_glob()` prevent glob injection
3. **Enum validation**: `UsefulnessClass`, `AlertmanagerRelevanceClass`, `SourceAction` enforce allowed values
4. **State validation**: `can_promote`/`can_disable` checks prevent invalid state transitions
5. **Artifact existence checks**: 404 if source artifact not found
6. **Structured logging**: All mutation endpoints emit structured logs for observability
7. **Error handling**: All endpoints return JSON errors with appropriate HTTP codes

---

## 6. Security Gaps

### 6.1 Authentication / Authorization

**Gap**: No authentication or authorization layer on any endpoint.

**Impact**: Any client that can reach the server (localhost or exposed) can mutate state.

**Recommendation**: Add operator authentication (e.g., shared secret, mutual TLS, or reverse proxy auth).

### 6.2 CSRF Protection

**Gap**: No CSRF protection on any POST endpoint.

**Impact**: Browser-based attacks could trigger mutations via cross-origin requests.

**Recommendation**: 
- Add SameSite cookies for session management
- Add CSRF token validation for state-changing operations
- Consider Same-Origin policy enforcement via Origin header check

### 6.3 Request Validation

**Gap**: Content-Type not validated; request size not limited.

**Impact**: Malformed requests could cause unexpected behavior.

**Recommendation**: 
- Validate `Content-Type: application/json` header
- Add `Content-Length` upper bounds
- Add JSON body schema validation for each mutation

### 6.4 Idempotency

**Gap**: Most mutation endpoints are not idempotent; re-submission creates new artifacts.

**Impact**: Retry behavior may cause duplicate artifacts.

**Recommendation**: Consider idempotency keys for feedback endpoints.

### 6.5 Audit Trail

**Gap**: Read operations have no structured audit log; mutation audit is partial.

**Impact**: Hard to reconstruct operation history from logs.

**Recommendation**: Add consistent audit fields (operator, timestamp, run_id, action) to all mutation artifacts.

---

## 7. Remediation Backlog

| Priority | Issue | Effort | Status | Notes |
|----------|-------|--------|--------|-------|
| P0 | Add CSRF token validation | Medium | OPEN | Affects all POST endpoints |
| **P0** | **Add Content-Type validation** | Low | **DONE (API-R1)** | Validated via `_validate_json_mutation_request()` |
| **P1** | **Add request size limits** | Low | **DONE (API-R1)** | 1 MiB limit enforced |
| P1 | Add operator authentication | High | OPEN | Depends on deployment model |
| P2 | Add idempotency keys for feedback | Medium | OPEN | UUID already used; add client-provided key |
| P2 | Add audit fields to artifacts | Low | OPEN | Consistent timestamp/operator fields |
| P3 | Add rate limiting | Medium | OPEN | Per-IP or per-session |
| P3 | Add Origin header validation | Low | OPEN | Reject cross-origin requests |

---

## 8. Recommended First Remediation

**Action**: Add Content-Type and request size validation to all mutation endpoints.

**Rationale**: 
- Low effort (shared middleware pattern)
- Immediate reduction in malformed request attacks
- Doesn't change API contract
- Can be implemented incrementally

**Implementation sketch**:
```python
def _validate_json_request(handler) -> tuple[dict, int] | None:
    content_type = handler.headers.get("Content-Type", "")
    if not content_type.startswith("application/json"):
        return None, 415  # Unsupported Media Type
    
    content_length = int(handler.headers.get("Content-Length") or 0)
    if content_length > MAX_BODY_SIZE:  # e.g., 1MB
        return None, 413  # Payload Too Large
    
    # Parse body...
```

---

## 9. Verification

- All route handlers inspected manually
- Path validation patterns verified via grep
- CSRF protection gaps confirmed via code inspection
- Content-Type handling confirmed via code inspection
