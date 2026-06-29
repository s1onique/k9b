"""Shared fixture builders for alertmanager sources API tests.

This module contains reusable test helpers extracted from
test_ui_server_api_alertmanager_sources.py to avoid duplication across
thematic test modules.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import urllib.error
import urllib.request
from datetime import UTC, datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import cast

from k8s_diag_agent.external_analysis.alertmanager_source_models import (
    AlertmanagerSourceRegistry,
)
from k8s_diag_agent.external_analysis.alertmanager_source_registry import (
    read_source_registry,
)
from k8s_diag_agent.external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from k8s_diag_agent.external_analysis.config import (
    ExternalAnalysisSettings,
    ReviewEnrichmentPolicy,
)
from k8s_diag_agent.health.ui import write_health_ui_index
from tests.helpers.ui_test_harness import (
    shutdown_test_server,
    start_ui_test_server_without_auth,
)

__all__ = [
    "build_artifact",
    "build_health_dirs",
    "build_index_with_sources",
    "build_sources_artifact",
    "build_compact_artifact",
    "build_sources_with_canonical_identity",
    "post_source_action",
    "fetch_run_payload",
    "read_registry",
    "shutdown_test_server",
    "start_ui_test_server_without_auth",
]


# ---------------------------------------------------------------------------
# Shared source payload builders
# ---------------------------------------------------------------------------


def build_sources_artifact(
    sources: list[dict[str, object]],
    cluster_context: str = "test-cluster",
) -> dict[str, object]:
    """Build a sources artifact dict from a list of source records."""
    return {
        "sources": sources,
        "total_count": len(sources),
        "discovery_timestamp": datetime.now(UTC).isoformat(),
        "cluster_context": cluster_context,
    }


def build_compact_artifact(
    cluster_context: str = "test-cluster",
    alert_count: int = 5,
) -> dict[str, object]:
    """Build a compact alert artifact dict with sensible defaults."""
    return {
        "status": "healthy",
        "alert_count": alert_count,
        "severity_counts": {"critical": 1, "warning": max(0, alert_count - 1)},
        "state_counts": {"firing": 3, "pending": 2},
        "top_alert_names": ["PodNotReady", "HighCPUUsage"],
        "affected_namespaces": ["monitoring", "default"],
        "affected_clusters": [cluster_context],
        "affected_services": ["api-service"],
        "truncated": False,
        "captured_at": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Artifact builders
# ---------------------------------------------------------------------------


def build_artifact(
    run_id: str,
    status: ExternalAnalysisStatus,
    purpose: ExternalAnalysisPurpose = ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
    timestamp: datetime | None = None,
) -> ExternalAnalysisArtifact:
    """Build an ExternalAnalysisArtifact with test defaults."""
    return ExternalAnalysisArtifact(
        tool_name="reviewer",
        run_id=run_id,
        run_label=run_id,
        cluster_label="review",
        summary=f"Test artifact for {run_id}",
        status=status,
        provider="reviewer",
        purpose=purpose,
        timestamp=datetime.now(UTC) if timestamp is None else timestamp,
    )


def build_health_dirs(health_dir: Path, run_id: str) -> None:
    """Create all required health subdirectories for a run."""
    health_dir.mkdir(parents=True, exist_ok=True)
    (health_dir / "reviews").mkdir(parents=True, exist_ok=True)
    (health_dir / "assessments").mkdir(parents=True, exist_ok=True)
    (health_dir / "drilldowns").mkdir(parents=True, exist_ok=True)
    (health_dir / "proposals").mkdir(parents=True, exist_ok=True)
    (health_dir / "external-analysis").mkdir(parents=True, exist_ok=True)


def build_review_artifact(health_dir: Path, run_id: str) -> Path:
    """Write a minimal review artifact file and return its path."""
    review_data = {
        "run_id": run_id,
        "run_label": run_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "collector_version": "tests",
        "selected_drilldowns": [],
        "clusters": [],
        "assessments": [],
        "health_rating": "healthy",
        "warnings": 0,
        "external_analysis_settings": {
            "review_enrichment": {"enabled": True, "provider": "reviewer"}
        },
    }
    review_path = health_dir / "reviews" / f"{run_id}-review.json"
    review_path.write_text(json.dumps(review_data, indent=2), encoding="utf-8")
    return review_path


# ---------------------------------------------------------------------------
# Index / context builders
# ---------------------------------------------------------------------------


def build_index_with_sources(
    health_dir: Path,
    run_id: str,
    sources: list[dict[str, object]],
    cluster_context: str = "test-cluster",
    alert_count: int = 5,
) -> None:
    """Write all artifacts and ui-index.json for a run with alertmanager sources.

    This is the canonical way to set up a test run with sources data.
    Creates subdirectories, review artifact, sources artifact, compact artifact,
    and ui-index.json with embedded source/compact data.
    """
    build_health_dirs(health_dir, run_id)

    # Write review artifact
    build_review_artifact(health_dir, run_id)

    # Write sources artifact
    sources_artifact = build_sources_artifact(sources, cluster_context)
    sources_path = health_dir / f"{run_id}-alertmanager-sources.json"
    sources_path.write_text(json.dumps(sources_artifact, indent=2), encoding="utf-8")

    # Write compact artifact
    compact_artifact = build_compact_artifact(cluster_context, alert_count)
    compact_path = health_dir / f"{run_id}-alertmanager-compact.json"
    compact_path.write_text(json.dumps(compact_artifact, indent=2), encoding="utf-8")

    # Write ui-index.json with embedded sources
    artifact = build_artifact(
        run_id=run_id,
        status=ExternalAnalysisStatus.SUCCESS,
        timestamp=datetime.now(UTC),
    )
    settings = ExternalAnalysisSettings(
        review_enrichment=ReviewEnrichmentPolicy(
            enabled=True,
            provider=artifact.provider or "reviewer",
        )
    )
    write_health_ui_index(
        health_dir,
        run_id=artifact.run_id,
        run_label=artifact.run_label or artifact.run_id,
        collector_version="tests",
        records=(),
        assessments=(),
        drilldowns=(),
        proposals=(),
        external_analysis=(artifact,),
        notifications=(),
        external_analysis_settings=settings,
    )
    # Post-process: inject alertmanager data into ui-index.json
    index_path = health_dir / "ui-index.json"
    if index_path.exists():
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
        run_entry = index_data.get("run") or {}
        run_entry["alertmanager_sources"] = sources_artifact
        run_entry["alertmanager_compact"] = compact_artifact
        index_data["run"] = run_entry
        index_path.write_text(json.dumps(index_data, indent=2), encoding="utf-8")


def build_sources_with_canonical_identity(
    health_dir: Path,
    run_id: str,
    source_id: str,
    endpoint: str,
    canonical_identity: str,
    origin: str = "alertmanager-crd",
    state: str = "auto-tracked",
    cluster_context: str = "test-cluster",
) -> None:
    """Write artifacts with explicit canonical_identity for cross-run matching tests.

    Simulates what the health loop discovery produces, with explicit
    canonical_identity for cross-run registry lookups.
    """
    build_health_dirs(health_dir, run_id)
    build_review_artifact(health_dir, run_id)

    # Parse namespace and name from canonical_identity for proper model behavior
    if "/" in canonical_identity:
        name_parts = canonical_identity.rsplit("/", 1)
        ns = name_parts[0]
        name = name_parts[1]
    else:
        ns = "monitoring"
        name = endpoint

    sources = [
        {
            "source_id": source_id,
            "endpoint": endpoint,
            "namespace": ns,
            "name": name,
            "origin": origin,
            "state": state,
            "canonical_identity": canonical_identity,
            "matching_key": endpoint,
            "discovered_at": "2026-01-01T00:00:00Z",
            "verified_at": "2026-01-01T00:01:00Z",
            "last_check": "2026-01-01T01:00:00Z",
            "last_error": None,
            "verified_version": "0.27.0",
            "confidence_hints": ["crd_discovery"],
        },
    ]
    sources_artifact = build_sources_artifact(sources, cluster_context)  # type: ignore[arg-type]
    sources_path = health_dir / f"{run_id}-alertmanager-sources.json"
    sources_path.write_text(json.dumps(sources_artifact, indent=2), encoding="utf-8")

    compact_artifact = build_compact_artifact(cluster_context)
    compact_path = health_dir / f"{run_id}-alertmanager-compact.json"
    compact_path.write_text(json.dumps(compact_artifact, indent=2), encoding="utf-8")

    # Write full ui-index.json directly
    index_data: dict[str, object] = {
        "run": {
            "run_id": run_id,
            "run_label": run_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "collector_version": "tests",
            "cluster_count": 1,
            "drilldown_count": 0,
            "proposal_count": 0,
            "external_analysis_count": 1,
            "notification_count": 0,
            "alertmanager_sources": sources_artifact,
            "alertmanager_compact": compact_artifact,
        },
        "clusters": [],
        "proposals": [],
        "latest_assessment": None,
        "latest_findings": None,
        "run_stats": {"total_runs": 1},
        "auto_drilldown_interpretations": {},
        "external_analysis": {"count": 1, "status_counts": [], "artifacts": []},
        "drilldown_availability": {
            "total_clusters": 0,
            "available": 0,
            "missing": 0,
            "missing_clusters": [],
            "coverage": [],
        },
        "proposal_status_summary": {"status_counts": []},
        "notification_history": [],
    }
    index_path = health_dir / "ui-index.json"
    index_path.write_text(json.dumps(index_data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def fetch_run_payload(
    server: ThreadingHTTPServer,
    run_id: str | None = None,
) -> dict[str, object]:
    """Fetch /api/run payload, optionally with run_id query parameter."""
    address = server.server_address
    host_address, port, *_ = address
    host = host_address.decode("utf-8") if isinstance(host_address, bytes) else host_address

    if run_id:
        url = f"http://{host}:{port}/api/run?run_id={run_id}"
    else:
        url = f"http://{host}:{port}/api/run"

    with urllib.request.urlopen(url, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
        assert isinstance(payload, dict)
        return cast(dict[str, object], payload)


def post_source_action(
    server: ThreadingHTTPServer,
    run_id: str,
    source_id: str,
    action: str,
    cluster_label: str = "test-cluster",
    reason: str = "test",
) -> dict[str, object]:
    """POST to the source action endpoint and return parsed JSON response."""
    address = server.server_address
    host_address, port, *_ = address
    host = host_address.decode("utf-8") if isinstance(host_address, bytes) else host_address

    from urllib.parse import quote

    encoded_source_id = quote(source_id, safe="")
    url = f"http://{host}:{port}/api/runs/{run_id}/alertmanager-sources/{encoded_source_id}/action"

    payload = json.dumps({
        "action": action,
        "clusterLabel": cluster_label,
        "reason": reason,
    }).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return cast(dict[str, object], json.loads(response.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8") if exc.fp else ""
        raise AssertionError(
            f"HTTP {exc.code}: {exc.reason}. Error body: {error_body}"
        ) from exc


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def read_registry(health_dir: Path) -> AlertmanagerSourceRegistry | None:
    """Read and return the source registry from health_dir."""
    return read_source_registry(health_dir)


# ---------------------------------------------------------------------------
# Temp directory helpers
# ---------------------------------------------------------------------------


def make_test_dirs() -> tuple[Path, Path, Path]:
    """Create a temporary directory tree for tests.

    Returns:
        (tmpdir, runs_dir, health_dir, static_dir)
    """
    tmpdir = Path(tempfile.mkdtemp()).resolve()
    runs_dir = (tmpdir / "runs").resolve()
    health_dir = runs_dir / "health"
    static_dir = tmpdir / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    return tmpdir, runs_dir, health_dir


def cleanup_test_dir(tmpdir: Path) -> None:
    """Remove a temporary test directory tree."""
    shutil.rmtree(tmpdir, ignore_errors=True)
