-- Content Index Schema
-- Version: k9b.content_index.v1
-- Format: SQLite
-- Purpose: Accelerate UI/backend read paths by precomputing projections

-- =============================================================================
-- Metadata Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS content_index_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Required metadata rows:
-- - schema_version: k9b.content_index.v1
-- - created_at: ISO timestamp of index creation
-- - indexed_at: ISO timestamp of last index update

-- =============================================================================
-- Content Item Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS content_item (
    content_id TEXT PRIMARY KEY,
    content_kind TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_path_kind TEXT NOT NULL,
    source_mtime_ns INTEGER NOT NULL,
    source_size_bytes INTEGER NOT NULL,
    source_sha256 TEXT NOT NULL,
    schema_version TEXT,
    indexed_at TEXT NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0,

    -- Constraints
    CONSTRAINT content_kind_check CHECK (
        content_kind IN (
            'incident',
            'evidence_link',
            'snapshot_bundle',
            'review_packet',
            'automatic_diagnosis_review',
            'diagnosis_loop_run',
            'diagnosis_loop_pass',
            'lab_result',
            'trace_capture_summary',
            'perf_baseline_summary'
        )
    ),
    CONSTRAINT source_path_kind_check CHECK (
        source_path_kind IN (
            'incident_store',
            'artifact',
            'lab',
            'trace_capture',
            'perf_baseline'
        )
    ),
    CONSTRAINT source_path_check CHECK (
        -- No absolute paths allowed
        NOT (source_path LIKE '/%' OR source_path LIKE '~/%')
    )
);

-- Index for faster lookups by content kind
CREATE INDEX IF NOT EXISTS idx_content_item_kind ON content_item(content_kind);

-- Index for faster lookups by source path kind
CREATE INDEX IF NOT EXISTS idx_content_item_path_kind ON content_item(source_path_kind);

-- Index for faster lookups by deleted status
CREATE INDEX IF NOT EXISTS idx_content_item_deleted ON content_item(deleted);

-- Index for freshness checks (mtime + size for quick freshness)
CREATE INDEX IF NOT EXISTS idx_content_item_freshness ON content_item(
    source_path,
    source_mtime_ns,
    source_size_bytes
);

-- =============================================================================
-- Content Projection Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS content_projection (
    content_id TEXT NOT NULL,
    projection_kind TEXT NOT NULL,
    projection_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    PRIMARY KEY (content_id, projection_kind),

    FOREIGN KEY (content_id) REFERENCES content_item(content_id)
        ON DELETE CASCADE
);

-- Index for faster lookups by projection kind
CREATE INDEX IF NOT EXISTS idx_content_projection_kind ON content_projection(projection_kind);

-- =============================================================================
-- Reserved: FTS5 Virtual Table (Optional - Not Required in v1)
-- =============================================================================

-- If FTS is added in a future version, it MUST NOT contain:
-- - Raw Kubernetes object JSON
-- - Raw provider prompts/responses
-- - Secrets, tokens, or credentials
-- - Absolute paths
--
-- Example reserved structure (commented out):
--
-- CREATE VIRTUAL TABLE IF NOT EXISTS content_fts USING fts5(
--     content_id,
--     safe_title,
--     safe_summary,
--     content='content_projection',
--     content_rowid='rowid'
-- );

-- =============================================================================
-- Schema Version Verification
-- =============================================================================

-- This view provides a convenient way to check schema version
CREATE VIEW IF NOT EXISTS schema_version_check AS
SELECT value AS schema_version
FROM content_index_metadata
WHERE key = 'schema_version';

-- =============================================================================
-- Freshness Summary View
-- =============================================================================

-- This view provides an overview of index freshness
CREATE VIEW IF NOT EXISTS freshness_summary AS
SELECT
    content_kind,
    COUNT(*) AS total_items,
    SUM(deleted) AS deleted_items,
    MAX(indexed_at) AS last_indexed_at
FROM content_item
GROUP BY content_kind;
