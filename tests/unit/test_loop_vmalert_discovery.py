"""Unit tests for vmalert health loop integration.

Tests cover:
- Health loop writes vmalert source artifact when discovery returns a source
- Health loop continues when vmalert discovery raises
- Health loop continues when vmalert verification marks source discovered-but-unverified
- Empty/no-vmalert behavior matches Alertmanager convention
- Existing Alertmanager discovery/artifact behavior remains unchanged
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.external_analysis.vmalert_discovery import (
    VmalertSource,
    VmalertSourceInventory,
    VmalertSourceOrigin,
    VmalertSourceState,
)

# --- Fixtures ---


@pytest.fixture
def sample_vmalert_source() -> VmalertSource:
    """A sample vmalert source for testing."""
    return VmalertSource(
        source_id="service:victoria-metrics-k8s-stack/vmalert-infra",
        endpoint="http://vmalert-infra.victoria-metrics-k8s-stack:8080",
        namespace="victoria-metrics-k8s-stack",
        name="vmalert-infra",
        origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
        state=VmalertSourceState.DISCOVERED,
        cluster_label="test-cluster",
        cluster_context="test-context",
    )


@pytest.fixture
def sample_inventory(sample_vmalert_source: VmalertSource) -> VmalertSourceInventory:
    """A sample inventory with one source."""
    inventory = VmalertSourceInventory()
    inventory.add_source(sample_vmalert_source)
    return inventory


@pytest.fixture
def temp_health_dir() -> Path:
    """Create a temporary directory simulating the health run directory."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# --- Test: Health loop runs vmalert discovery and persists artifact ---


def test_run_vmalert_discovery_writes_artifact(
    sample_vmalert_source: VmalertSource,
    temp_health_dir: Path,
) -> None:
    """Test that run_vmalert_discovery writes vmalert sources artifact."""
    from k8s_diag_agent.health.loop_vmalert_discovery import run_vmalert_discovery

    # Create a mock HealthSnapshotRecord
    mock_record = MagicMock()
    mock_record.target.context = "test-context"
    mock_record.target.label = "test-cluster"

    # Mock derive_cluster_uid
    with patch(
        "k8s_diag_agent.health.loop_vmalert_discovery.discover_vmalerts",
        return_value=VmalertSourceInventory(),
    ) as mock_discover:
        # Add a source to the returned inventory
        inventory = VmalertSourceInventory()
        inventory.add_source(sample_vmalert_source)
        mock_discover.return_value = inventory

        with patch(
            "k8s_diag_agent.health.loop_vmalert_discovery.verify_and_update_inventory",
            wraps=lambda inv: inv,  # Pass through
        ):
            # Track log events
            log_events: list[dict[str, Any]] = []

            def log_callback(component: str, severity: str, message: str, **metadata: Any) -> None:
                log_events.append({
                    "component": component,
                    "severity": severity,
                    "message": message,
                    "metadata": metadata,
                })

            directories = {"root": temp_health_dir}

            result = run_vmalert_discovery(
                records=[mock_record],
                directories=directories,
                log_event=log_callback,
                run_id="test-run-123",
            )

    # Verify artifact was written
    artifact_path = temp_health_dir / "test-run-123-vmalert-sources.json"
    assert artifact_path.exists(), f"Expected artifact at {artifact_path}"

    # Verify artifact contains the source
    import json

    with open(artifact_path) as f:
        data = json.load(f)

    assert data["source_count"] == 1
    assert len(data["sources"]) == 1
    assert data["sources"][0]["source_id"] == sample_vmalert_source.source_id

    # Verify result inventory
    assert len(result.sources) == 1


# --- Test: Health loop continues when vmalert discovery raises ---


def test_run_vmalert_discovery_continues_on_discovery_error(
    temp_health_dir: Path,
) -> None:
    """Test that vmalert discovery failures are non-fatal."""
    from k8s_diag_agent.health.loop_vmalert_discovery import run_vmalert_discovery

    mock_record = MagicMock()
    mock_record.target.context = "test-context"
    mock_record.target.label = "test-cluster"

    # Mock discover_vmalerts to raise an error
    with patch(
        "k8s_diag_agent.health.loop_vmalert_discovery.discover_vmalerts",
        side_effect=OSError("kubectl not found"),
    ):
        log_events: list[dict[str, Any]] = []

        def log_callback(component: str, severity: str, message: str, **metadata: Any) -> None:
            log_events.append({
                "component": component,
                "severity": severity,
                "message": message,
                "metadata": metadata,
            })

        directories = {"root": temp_health_dir}

        # Should not raise - discovery failure is non-fatal
        result = run_vmalert_discovery(
            records=[mock_record],
            directories=directories,
            log_event=log_callback,
            run_id="test-run-456",
        )

    # Verify we got an empty inventory
    assert len(result.sources) == 0

    # Verify warning was logged
    warning_events = [e for e in log_events if e["severity"] == "WARNING"]
    assert len(warning_events) > 0
    assert any("discovery failed" in e["message"].lower() for e in warning_events)


# --- Test: Health loop continues when vmalert verification fails ---


def test_run_vmalert_discovery_continues_on_verification_error(
    sample_vmalert_source: VmalertSource,
    temp_health_dir: Path,
) -> None:
    """Test that vmalert verification failures are non-fatal."""
    from k8s_diag_agent.health.loop_vmalert_discovery import run_vmalert_discovery

    mock_record = MagicMock()
    mock_record.target.context = "test-context"
    mock_record.target.label = "test-cluster"

    with patch(
        "k8s_diag_agent.health.loop_vmalert_discovery.discover_vmalerts",
        return_value=VmalertSourceInventory(),
    ) as mock_discover:
        # Add a source to the returned inventory
        inventory = VmalertSourceInventory()
        inventory.add_source(sample_vmalert_source)
        mock_discover.return_value = inventory

        # Mock verification to raise an error
        with patch(
            "k8s_diag_agent.health.loop_vmalert_discovery.verify_and_update_inventory",
            side_effect=RuntimeError("Network unreachable"),
        ):
            log_events: list[dict[str, Any]] = []

            def log_callback(component: str, severity: str, message: str, **metadata: Any) -> None:
                log_events.append({
                    "component": component,
                    "severity": severity,
                    "message": message,
                    "metadata": metadata,
                })

            directories = {"root": temp_health_dir}

            # Should not raise - verification failure is non-fatal
            result = run_vmalert_discovery(
                records=[mock_record],
                directories=directories,
                log_event=log_callback,
                run_id="test-run-789",
            )

    # Verify we still got the source (unverified)
    assert len(result.sources) == 1

    # Verify warning was logged about verification failure
    warning_events = [e for e in log_events if e["severity"] == "WARNING"]
    assert any("verification failed" in e["message"].lower() for e in warning_events)


# --- Test: Health loop marks source as discovered-but-unverified on probe failure ---


def test_run_vmalert_discovery_marks_unreachable_as_discovered_but_unverified(
    sample_vmalert_source: VmalertSource,
    temp_health_dir: Path,
) -> None:
    """Test that unreachable sources are marked as discovered-but-unverified."""
    from k8s_diag_agent.external_analysis.vmalert_discovery import (
        VerificationResult,
        verify_and_update_inventory,
    )
    from k8s_diag_agent.health.loop_vmalert_discovery import run_vmalert_discovery

    mock_record = MagicMock()
    mock_record.target.context = "test-context"
    mock_record.target.label = "test-cluster"

    # Source starts as DISCOVERED
    assert sample_vmalert_source.state == VmalertSourceState.DISCOVERED

    # Create inventory with source
    inventory = VmalertSourceInventory()
    inventory.add_source(sample_vmalert_source)

    # Mock verification to return unreachable result
    unreachable_result = VerificationResult(
        reachable=False,
        error="Connection refused",
    )

    def mock_verify(inv: VmalertSourceInventory) -> VmalertSourceInventory:
        # Apply the same logic as verify_and_update_inventory
        return verify_and_update_inventory(inv)

    with patch(
        "k8s_diag_agent.health.loop_vmalert_discovery.discover_vmalerts",
        return_value=inventory,
    ):
        with patch(
            "k8s_diag_agent.health.loop_vmalert_discovery.verify_and_update_inventory",
            side_effect=lambda inv: mock_verify(inv),
        ):
            with patch(
                "k8s_diag_agent.external_analysis.vmalert_discovery.verify_vmalert_endpoint",
                return_value=unreachable_result,
            ):
                directories = {"root": temp_health_dir}

                result = run_vmalert_discovery(
                    records=[mock_record],
                    directories=directories,
                    log_event=MagicMock(),
                    run_id="test-run-abc",
                )

    # Verify source is marked as discovered-but-unverified
    assert len(result.sources) == 1
    source = list(result.sources.values())[0]
    assert source.state == VmalertSourceState.DISCOVERED_BUT_UNVERIFIED
    assert source.last_error == "Connection refused"


# --- Test: Empty/no-vmalert behavior writes empty artifact (matches Alertmanager) ---


def test_run_vmalert_discovery_writes_empty_artifact(
    temp_health_dir: Path,
) -> None:
    """Test that empty inventory still writes artifact (matches Alertmanager convention)."""
    from k8s_diag_agent.health.loop_vmalert_discovery import run_vmalert_discovery

    mock_record = MagicMock()
    mock_record.target.context = "test-context"
    mock_record.target.label = "test-cluster"

    # Return empty inventory (no vmalerts found)
    with patch(
        "k8s_diag_agent.health.loop_vmalert_discovery.discover_vmalerts",
        return_value=VmalertSourceInventory(),
    ):
        directories = {"root": temp_health_dir}

        run_vmalert_discovery(
            records=[mock_record],
            directories=directories,
            log_event=MagicMock(),
            run_id="test-run-empty",
        )

    # Verify artifact was written even with empty inventory
    # This matches Alertmanager behavior
    artifact_path = temp_health_dir / "test-run-empty-vmalert-sources.json"
    assert artifact_path.exists(), "Empty inventory should still write artifact"

    # Verify artifact content
    import json

    with open(artifact_path) as f:
        data = json.load(f)

    assert data["source_count"] == 0
    assert data["sources"] == []


# --- Test: No records returns empty inventory without writing artifact ---


def test_run_vmalert_discovery_skips_when_no_records(
    temp_health_dir: Path,
) -> None:
    """Test that empty records list returns empty inventory."""
    from k8s_diag_agent.health.loop_vmalert_discovery import run_vmalert_discovery

    directories = {"root": temp_health_dir}

    result = run_vmalert_discovery(
        records=[],
        directories=directories,
        log_event=MagicMock(),
        run_id="test-run-no-records",
    )

    # Verify empty inventory returned
    assert len(result.sources) == 0

    # Verify no artifact was written (matches Alertmanager: no records = skip)
    artifact_path = temp_health_dir / "test-run-no-records-vmalert-sources.json"
    assert not artifact_path.exists(), "No artifact should be written with no records"


# --- Test: Artifact write failure is non-fatal ---


def test_run_vmalert_discovery_continues_on_write_error(
    sample_vmalert_source: VmalertSource,
    temp_health_dir: Path,
) -> None:
    """Test that artifact write failure is non-fatal.

    Patches at the health-loop boundary (write_vmalert_sources) to prove
    the health loop correctly handles artifact write failures.
    """
    from k8s_diag_agent.health.loop_vmalert_discovery import run_vmalert_discovery

    mock_record = MagicMock()
    mock_record.target.context = "test-context"
    mock_record.target.label = "test-cluster"

    # Create inventory with source inside the patch so mock returns it
    inventory = VmalertSourceInventory()
    inventory.add_source(sample_vmalert_source)

    with patch(
        "k8s_diag_agent.health.loop_vmalert_discovery.discover_vmalerts",
        return_value=inventory,
    ):
        with patch(
            "k8s_diag_agent.health.loop_vmalert_discovery.verify_and_update_inventory",
            wraps=lambda inv: inv,
        ):
            # Patch at the health-loop boundary for stronger test
            with patch(
                "k8s_diag_agent.health.loop_vmalert_discovery.write_vmalert_sources",
                side_effect=OSError("Permission denied"),
            ):
                log_events: list[dict[str, Any]] = []

                def log_callback(component: str, severity: str, message: str, **metadata: Any) -> None:
                    log_events.append({
                        "component": component,
                        "severity": severity,
                        "message": message,
                        "metadata": metadata,
                    })

                directories = {"root": temp_health_dir}

                # Should not raise - write failure is non-fatal
                result = run_vmalert_discovery(
                    records=[mock_record],
                    directories=directories,
                    log_event=log_callback,
                    run_id="test-run-write-fail",
                )

    # Verify we still got the source
    assert len(result.sources) == 1

    # Verify error was logged
    error_events = [e for e in log_events if e["severity"] == "ERROR"]
    assert any("write" in e["message"].lower() for e in error_events)


# --- Test: Multiple records aggregated correctly ---


def test_run_vmalert_discovery_aggregates_multiple_records(
    temp_health_dir: Path,
) -> None:
    """Test that vmalert discovery aggregates sources from multiple records."""
    from k8s_diag_agent.health.loop_vmalert_discovery import run_vmalert_discovery

    # Create two mock records for different clusters
    record1 = MagicMock()
    record1.target.context = "context-1"
    record1.target.label = "cluster-1"

    record2 = MagicMock()
    record2.target.context = "context-2"
    record2.target.label = "cluster-2"

    source1 = VmalertSource(
        source_id="service:ns1/vmalert1",
        endpoint="http://vmalert1.ns1:8080",
        namespace="ns1",
        name="vmalert1",
        origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
        state=VmalertSourceState.DISCOVERED,
    )

    source2 = VmalertSource(
        source_id="service:ns2/vmalert2",
        endpoint="http://vmalert2.ns2:8080",
        namespace="ns2",
        name="vmalert2",
        origin=VmalertSourceOrigin.VMALERT_CRD,
        state=VmalertSourceState.DISCOVERED,
    )

    call_count = 0

    def mock_discover(context: str | None = None, **kwargs: Any) -> VmalertSourceInventory:
        nonlocal call_count
        call_count += 1
        inventory = VmalertSourceInventory()
        # Return different source based on context
        if context == "context-1":
            inventory.add_source(source1)
        elif context == "context-2":
            inventory.add_source(source2)
        return inventory

    with patch(
        "k8s_diag_agent.health.loop_vmalert_discovery.discover_vmalerts",
        side_effect=mock_discover,
    ):
        with patch(
            "k8s_diag_agent.health.loop_vmalert_discovery.verify_and_update_inventory",
            wraps=lambda inv: inv,
        ):
            directories = {"root": temp_health_dir}

            result = run_vmalert_discovery(
                records=[record1, record2],
                directories=directories,
                log_event=MagicMock(),
                run_id="test-run-multi",
            )

    # Verify both sources were aggregated
    # After deduplication, we should have 2 sources
    assert len(result.sources) == 2

    # Verify artifact was written with both sources
    artifact_path = temp_health_dir / "test-run-multi-vmalert-sources.json"
    assert artifact_path.exists()

    import json

    with open(artifact_path) as f:
        data = json.load(f)

    assert data["source_count"] == 2


# --- Test: Deduplication preserves merged_provenances ---


def test_run_vmalert_discovery_deduplication_merges_provenances(
    temp_health_dir: Path,
) -> None:
    """Test that deduplication correctly merges provenances from multiple discovery strategies."""
    from k8s_diag_agent.health.loop_vmalert_discovery import run_vmalert_discovery

    mock_record = MagicMock()
    mock_record.target.context = "test-context"
    mock_record.target.label = "test-cluster"

    # Same source discovered via CRD and service heuristic (same namespace/name)
    crd_source = VmalertSource(
        source_id="crd:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
        origin=VmalertSourceOrigin.VMALERT_CRD,
        state=VmalertSourceState.DISCOVERED,
    )

    service_source = VmalertSource(
        source_id="service:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
        origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
        state=VmalertSourceState.DISCOVERED,
    )

    def mock_discover(context: str | None = None, **kwargs: Any) -> VmalertSourceInventory:
        # Return both sources in one call - simulates discover_vmalerts finding
        # the same endpoint via both CRD and service heuristic strategies
        inventory = VmalertSourceInventory()
        inventory.add_source(crd_source)
        inventory.add_source(service_source)
        return inventory

    with patch(
        "k8s_diag_agent.health.loop_vmalert_discovery.discover_vmalerts",
        side_effect=mock_discover,
    ):
        with patch(
            "k8s_diag_agent.health.loop_vmalert_discovery.verify_and_update_inventory",
            wraps=lambda inv: inv,
        ):
            directories = {"root": temp_health_dir}

            result = run_vmalert_discovery(
                records=[mock_record],
                directories=directories,
                log_event=MagicMock(),
                run_id="test-run-dedup",
            )

    # After deduplication, we should have 1 source
    assert len(result.sources) == 1

    source = list(result.sources.values())[0]
    # CRD should win (higher priority)
    assert source.origin == VmalertSourceOrigin.VMALERT_CRD
    # But merged_provenances should include both
    assert VmalertSourceOrigin.VMALERT_CRD in source.merged_provenances
    assert VmalertSourceOrigin.SERVICE_HEURISTIC in source.merged_provenances


# --- Test: Cluster provenance tagging ---


def test_run_vmalert_discovery_tags_sources_with_cluster_provenance(
    temp_health_dir: Path,
) -> None:
    """Test that sources are tagged with cluster_label and cluster_context."""
    from k8s_diag_agent.health.loop_vmalert_discovery import run_vmalert_discovery

    mock_record = MagicMock()
    mock_record.target.context = "my-kube-context"
    mock_record.target.label = "production-cluster"

    # Create source and inventory inside the patch so discover_vmalerts returns it
    source = VmalertSource(
        source_id="service:ns/vmalert",
        endpoint="http://vmalert.ns:8080",
        namespace="ns",
        name="vmalert",
        origin=VmalertSourceOrigin.SERVICE_HEURISTIC,
        state=VmalertSourceState.DISCOVERED,
    )
    inventory = VmalertSourceInventory()
    inventory.add_source(source)

    with patch(
        "k8s_diag_agent.health.loop_vmalert_discovery.discover_vmalerts",
        return_value=inventory,
    ):
        with patch(
            "k8s_diag_agent.health.loop_vmalert_discovery.verify_and_update_inventory",
            wraps=lambda inv: inv,
        ):
            directories = {"root": temp_health_dir}

            result = run_vmalert_discovery(
                records=[mock_record],
                directories=directories,
                log_event=MagicMock(),
                run_id="test-run-provenance",
            )

    # Verify sources are tagged with cluster provenance
    assert len(result.sources) == 1
    source = list(result.sources.values())[0]
    assert source.cluster_label == "production-cluster"
    assert source.cluster_context == "my-kube-context"
