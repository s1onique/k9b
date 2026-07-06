#!/usr/bin/env python3
"""Seed incident content into a content index SQLite database.

This script creates test incident data and adds it to the content index
for proving the content_index read path works correctly.

Usage:
    python scripts/seed_incident_index.py --index-db /tmp/content-index.sqlite

Exit codes:
    0 - Successfully seeded incidents
    1 - Failed to seed incidents
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def seed_incidents_to_index(db_path: Path, num_incidents: int = 3) -> int:
    """Seed incident content into the content index.

    Args:
        db_path: Path to the SQLite content index database
        num_incidents: Number of test incidents to create

    Returns:
        Number of incidents seeded
    """
    if not db_path.exists():
        print(f"ERROR: Index DB not found: {db_path}")
        return 0

    conn = sqlite3.connect(str(db_path))
    now_iso = datetime.now(UTC).isoformat()
    # Use current time in nanoseconds for mtime
    now_ns = int(datetime.now(UTC).timestamp() * 1e9)

    incidents_created = 0
    for i in range(1, num_incidents + 1):
        incident_id = f"test-incident-{i:03d}"
        
        # Create content_item for incident
        # Note: content_id must match what the readpath queries (just incident_id, not "incident:xxx")
        content_id = incident_id
        source_path = f"incidents/{incident_id}/incident.json"
        
        # Create mock incident JSON to compute hash and size
        mock_incident = {"incident_id": incident_id, "test": True}
        incident_json = json.dumps(mock_incident, separators=(",", ":"))
        source_sha256 = hashlib.sha256(incident_json.encode()).hexdigest()
        source_size_bytes = len(incident_json)
        
        conn.execute(
            """
            INSERT OR REPLACE INTO content_item 
            (content_id, content_kind, source_path, source_path_kind, source_mtime_ns, 
             source_size_bytes, source_sha256, schema_version, indexed_at, deleted)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (content_id, "incident", source_path, "incident_store", now_ns,
             source_size_bytes, source_sha256, "k9b.incident.v1", now_iso),
        )

        # Create API summary projection
        summary = {
            "schema_version": "k9b.api.incident.summary.v1",
            "incident_id": incident_id,
            "source_candidate_id": f"candidate-{incident_id}",
            "namespace": "default" if i % 2 == 0 else "k9b",
            "object_kind": "Pod",
            "object_name": f"test-pod-{i}",
            "candidate_class": "readiness_probe_failure" if i % 2 == 0 else "crash_loop_backoff",
            "severity": "high" if i == 1 else "medium",
            "status": "open",
            "first_observed_at": now_iso,
            "last_observed_at": now_iso,
            "summary": f"Test incident {i}: Detected {('readiness probe failure' if i % 2 == 0 else 'CrashLoopBackOff')} in namespace {'default' if i % 2 == 0 else 'k9b'}",
        }
        conn.execute(
            """
            INSERT OR REPLACE INTO content_projection (content_id, projection_kind, projection_json, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (content_id, "api_summary", json.dumps(summary), now_iso),
        )

        # Create API detail projection
        detail = {
            "schema_version": "k9b.api.incident.detail.v1",
            **summary,
            "events": [
                {
                    "timestamp": now_iso,
                    "event_type": "incident_created",
                    "description": "Incident detected via health loop",
                },
            ],
            "evidence_links": [],
            "symptoms": [
                {
                    "symptom_type": "readiness_probe_failure" if i % 2 == 0 else "crash_loop_backoff",
                    "count": i * 2,
                }
            ],
        }
        conn.execute(
            """
            INSERT OR REPLACE INTO content_projection (content_id, projection_kind, projection_json, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (content_id, "api_detail", json.dumps(detail), now_iso),
        )

        incidents_created += 1
        print(f"  Seeded: {incident_id} ({summary['candidate_class']})")

    conn.commit()
    conn.close()

    return incidents_created


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Seed incident content into content index",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--index-db",
        type=Path,
        required=True,
        help="Path to the SQLite content index database",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Number of incidents to create (default: 3)",
    )

    args = parser.parse_args()

    print(f"Seeding {args.count} incidents into {args.index_db}...")
    count = seed_incidents_to_index(args.index_db, args.count)
    
    if count > 0:
        print(f"Successfully seeded {count} incidents")
        return 0
    else:
        print("Failed to seed incidents")
        return 1


if __name__ == "__main__":
    sys.exit(main())
