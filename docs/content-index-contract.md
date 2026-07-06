# Content Index Contract

**Contract ID**: `k9b.content_index.v1`  
**Status**: Active  
**Owner**: Backend Platform Team  
**Epic**: `EPIC-K9B-BACKEND-OTEL-INDEXED-CONTENT01`

---

## Purpose

This contract defines the schema, freshness rules, and API compatibility guarantees for the k9b on-disk content index. The index accelerates UI/backend read paths by precomputing projections from source artifacts.

The index is an **acceleration layer only**. It must not change existing API response schemas or introduce new failure modes for callers.

---

## Indexed Content Kinds

The index MUST support indexing these content kinds where they exist in the repository:

| Content Kind | Description |
|--------------|-------------|
| `incident` | Incident records stored in incident store |
| `evidence_link` | Links between incidents and evidence artifacts |
| `snapshot_bundle` | Cluster snapshot bundles |
| `review_packet` | Diagnosis review packets |
| `automatic_diagnosis_review` | Auto diagnosis review results |
| `diagnosis_loop_run` | Full diagnosis loop run records |
| `diagnosis_loop_pass` | Individual diagnosis loop pass records |
| `lab_result` | Lab execution results |
| `trace_capture_summary` | OTel trace capture summaries |
| `perf_baseline_summary` | Performance baseline summaries |

---

## Schema Version

| Element | Value |
|---------|-------|
| Content Index Schema Version | `k9b.content_index.v1` |
| Index Format | SQLite |
| FTS Reserved | FTS5 (optional, not required in this contract) |

The schema version MUST be stored in `content_index_metadata` table and validated before reading.

---

## Source Paths and Categories

| Path Kind | Description |
|-----------|-------------|
| `incident_store` | Incident store directory |
| `artifact` | General artifact directory |
| `lab` | Lab execution output |
| `trace_capture` | Trace capture output |
| `perf_baseline` | Performance baseline artifacts |

Source paths are **never stored as absolute paths** in projections. Only `source_path_kind` plus relative paths are used.

---

## SQL Schema

### Table: `content_index_metadata`

```sql
CREATE TABLE content_index_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

**Required rows**:
- `schema_version` = `k9b.content_index.v1`
- `created_at` = ISO timestamp
- `indexed_at` = ISO timestamp of last index update

### Table: `content_item`

```sql
CREATE TABLE content_item (
  content_id TEXT PRIMARY KEY,
  content_kind TEXT NOT NULL,
  source_path TEXT NOT NULL,
  source_path_kind TEXT NOT NULL,
  source_mtime_ns INTEGER NOT NULL,
  source_size_bytes INTEGER NOT NULL,
  source_sha256 TEXT NOT NULL,
  schema_version TEXT,
  indexed_at TEXT NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0
);
```

**Constraints**:
- `content_kind` MUST be one of the indexed content kinds
- `source_path_kind` MUST be one of the defined path kinds
- `deleted = 1` indicates a tombstone (source file removed)

### Table: `content_projection`

```sql
CREATE TABLE content_projection (
  content_id TEXT NOT NULL,
  projection_kind TEXT NOT NULL,
  projection_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (content_id, projection_kind),
  FOREIGN KEY (content_id) REFERENCES content_item(content_id)
);
```

**Constraints**:
- `projection_json` MUST contain valid JSON
- `projection_kind` maps to existing API response models
- No raw secrets, tokens, or credentials in projections

### Reserved: FTS Table (Optional)

```sql
-- Reserved for future FTS5 search
-- CREATE VIRTUAL TABLE content_fts USING fts5(...);
```

If FTS is added later:
- MUST NOT contain raw Kubernetes object JSON
- MUST NOT contain raw provider prompts/responses
- MUST NOT contain secrets, tokens, or credentials
- MUST follow privacy/safety rules defined below

---

## Freshness Rules

A content item is considered **fresh** when ALL of the following are true:

| Condition | Description |
|-----------|-------------|
| `source_mtime_ns` matches | File modification time unchanged |
| `source_size_bytes` matches | File size unchanged |
| `source_sha256` matches | Content hash unchanged |
| `schema_version` current | No schema migration needed |
| `index_schema_version` matches | Index schema is compatible |

### Freshness Decision Tree

```
same path + same mtime + same size + same sha256 = FRESH
                                                        ↓
                                          re-projection NOT required
                                                          
missing source file = TOMBSTONE
                    (mark deleted=1, retain metadata)

changed mtime OR changed size → re-hash required
                               ↓
                  sha256 changed = RE-PROJECT
                  sha256 same    = FRESH (no content change)

unknown schema version = BLOCK
                         (do not index silently as current)

index_schema_version mismatch = REBUILD REQUIRED
                                (corrupt/missing index)

corrupt SQLite = SAFE REBUILD
                (do not read partial data)
```

---

## Invalidation Rules

| Event | Action |
|-------|--------|
| Source file deleted | Tombstone: set `deleted=1`, retain for grace period |
| Source file modified | Re-hash, update if content changed |
| Schema version bump | Full rebuild required |
| Index corruption detected | Safe rebuild from source |
| Path kind change | Re-index affected content |

---

## Corruption Handling

| Corruption Type | Handling |
|-----------------|----------|
| Missing SQLite file | Treat as empty index, rebuild |
| Schema version mismatch | Safe rebuild required |
| Invalid JSON in projection | Delete projection, rebuild |
| Missing required columns | Safe rebuild required |
| Foreign key violation | Safe rebuild required |
| Disk I/O error | Fallback to direct read path |

**Rule**: Never read partial/corrupt index data as if fresh. Fall back to direct read path.

---

## Privacy/Safety Rules

### Index MAY Store

- IDs already exposed by API
- Content kind
- Bounded counts
- Status/severity/class
- Timestamps
- Schema versions
- Safe display titles
- Safe summary fields
- Relative/source path kind
- SHA256 hash
- Size/mtime metadata

### Index MUST NOT Store

- Raw Kubernetes object JSON
- Raw provider prompts
- Raw provider responses
- Raw logs
- Secrets
- Tokens
- Bearer values
- Cookies
- Auth headers
- Kubeconfigs
- Absolute local paths
- Raw artifact payloads

### Path Handling

- Never expose absolute paths in projections
- Use `source_path_kind` plus repo-relative path
- Never expose local home directories in API projections

---

## API Compatibility Rules

### Core Rules

1. **Existing API schemas remain unchanged**
2. **Index projections MUST map to existing API response models**
3. **When index is disabled, current read path is used**
4. **When index is missing/stale/corrupt, fallback to current read path**
5. **No API may return partial stale index data as if fresh**

### Feature Flag

```
K9B_CONTENT_INDEX_ENABLED=false  # Default: disabled
```

This flag is reserved for ACT-K9B-CONTENT-INDEXER01.

### Fallback Behavior

When fallback occurs:
1. Log a warning with reason
2. Use direct read path
3. Do not return stale data

---

## Migration/Versioning Rules

| Scenario | Action |
|----------|--------|
| Schema version bump | Increment `index_schema_version` |
| Incompatible change | Require safe rebuild |
| Backward-compatible change | Allow incremental migration |
| Unknown schema version | Block read, require rebuild |

---

## Verifier Expectations

The verifier MUST check:

1. Doc exists at `docs/content-index-contract.md`
2. Schema module exists at `src/k8s_diag_agent/content_index/schema.py`
3. SQL schema exists at `src/k8s_diag_agent/content_index/schema.sql`
4. Required tables present: `content_item`, `content_projection`, `content_index_metadata`
5. Required columns present in each table
6. Required content kinds defined in schema module
7. Forbidden field names absent from SQL/projection contract
8. Feature flag default documented as `K9B_CONTENT_INDEX_ENABLED=false`
9. Tests exist at `tests/unit/test_content_index_schema_contract.py`
10. In-memory SQLite validation of SQL schema executes without error

---

## Contract Version History

| Version | Date | Change |
|---------|------|--------|
| k9b.content_index.v1 | 2026-06-07 | Initial contract definition |

---

## Related Documents

- `EPIC-K9B-BACKEND-OTEL-INDEXED-CONTENT01` - Parent epic
- `ACT-K9B-CONTENT-INDEXER01` - Next ACT (indexer implementation)
- `src/k8s_diag_agent/content_index/schema.py` - Schema module
- `src/k8s_diag_agent/content_index/schema.sql` - SQL definitions
- `tests/unit/test_content_index_schema_contract.py` - Contract tests
- `scripts/verify_content_index_contract.py` - Contract verifier
