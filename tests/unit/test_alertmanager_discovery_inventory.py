"""Unit tests for AlertmanagerSourceInventory.

Tests cover:
- Adding sources to inventory
- Precedence rules (manual > discovered)
- Origin and state filtering
- Serialization roundtrips
"""

from __future__ import annotations

from k8s_diag_agent.external_analysis.alertmanager_discovery import (
    AlertmanagerSource,
    AlertmanagerSourceInventory,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
)


class TestInventoryAddSource:
    """Tests for adding sources to inventory."""

    def test_inventory_add_source(self) -> None:
        """Test adding sources to inventory."""
        inventory = AlertmanagerSourceInventory()

        source = AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager:9093",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        )

        inventory.add_source(source)

        assert len(inventory.sources) == 1
        assert "crd:monitoring/main" in inventory.sources

    def test_inventory_large_source_count(self) -> None:
        """Test inventory with many sources (stress test)."""
        inventory = AlertmanagerSourceInventory()

        # Add 100 sources
        for i in range(100):
            source = AlertmanagerSource(
                source_id=f"crd:ns{i}/am{i}",
                endpoint=f"http://am{i}:9093",
                origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            )
            inventory.add_source(source)

        assert len(inventory.sources) == 100

        # Verify filtering still works
        crd_sources = inventory.get_by_origin(AlertmanagerSourceOrigin.ALERTMANAGER_CRD)
        assert len(crd_sources) == 100

        manual_sources = inventory.get_by_origin(AlertmanagerSourceOrigin.MANUAL)
        assert len(manual_sources) == 0


class TestInventoryPrecedence:
    """Tests for inventory precedence rules."""

    def test_inventory_manual_precedence(self) -> None:
        """Manual sources must not be overwritten by discovered sources."""
        inventory = AlertmanagerSourceInventory()

        # Add manual source first
        manual = AlertmanagerSource(
            source_id="manual:custom",
            endpoint="http://custom:9093",
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
        )
        inventory.add_source(manual)

        # Try to add a discovered source with the same identity
        discovered = AlertmanagerSource(
            source_id="manual:custom",
            endpoint="http://different:9093",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        )
        inventory.add_source(discovered)

        # Manual should still be there
        assert inventory.sources["manual:custom"].origin == AlertmanagerSourceOrigin.MANUAL
        assert inventory.sources["manual:custom"].endpoint == "http://custom:9093"

    def test_inventory_manual_replaces_discovered(self) -> None:
        """Manual sources should replace discovered sources with same identity."""
        inventory = AlertmanagerSourceInventory()

        # Add discovered source first
        discovered = AlertmanagerSource(
            source_id="test:same",
            endpoint="http://discovered:9093",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        )
        inventory.add_source(discovered)

        # Add manual source with same ID
        manual = AlertmanagerSource(
            source_id="test:same",
            endpoint="http://manual:9093",
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
        )
        inventory.add_source(manual)

        # Manual should win
        assert inventory.sources["test:same"].origin == AlertmanagerSourceOrigin.MANUAL

    def test_inventory_origin_priority(self) -> None:
        """Higher priority origin should replace lower priority."""
        inventory = AlertmanagerSourceInventory()

        # Add lower priority source (service heuristic)
        low_priority = AlertmanagerSource(
            source_id="test:priority",
            endpoint="http://low:9093",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
        )
        inventory.add_source(low_priority)

        # Add higher priority source (CRD)
        high_priority = AlertmanagerSource(
            source_id="test:priority",
            endpoint="http://high:9093",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
        )
        inventory.add_source(high_priority)

        # CRD should win
        assert inventory.sources["test:priority"].origin == AlertmanagerSourceOrigin.ALERTMANAGER_CRD


class TestInventoryFiltering:
    """Tests for inventory filtering methods."""

    def test_inventory_get_by_origin(self) -> None:
        """Test filtering sources by origin."""
        inventory = AlertmanagerSourceInventory()

        sources = [
            AlertmanagerSource(
                source_id="crd:test",
                endpoint="http://crd:9093",
                origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            ),
            AlertmanagerSource(
                source_id="manual:test",
                endpoint="http://manual:9093",
                origin=AlertmanagerSourceOrigin.MANUAL,
            ),
            AlertmanagerSource(
                source_id="service:test",
                endpoint="http://service:9093",
                origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            ),
        ]

        for s in sources:
            inventory.add_source(s)

        crd_sources = inventory.get_by_origin(AlertmanagerSourceOrigin.ALERTMANAGER_CRD)
        assert len(crd_sources) == 1
        assert crd_sources[0].source_id == "crd:test"

    def test_inventory_get_by_state(self) -> None:
        """Test filtering sources by state."""
        inventory = AlertmanagerSourceInventory()

        sources = [
            AlertmanagerSource(
                source_id="test:auto",
                endpoint="http://auto:9093",
                state=AlertmanagerSourceState.AUTO_TRACKED,
            ),
            AlertmanagerSource(
                source_id="test:manual",
                endpoint="http://manual:9093",
                state=AlertmanagerSourceState.MANUAL,
            ),
            AlertmanagerSource(
                source_id="test:degraded",
                endpoint="http://degraded:9093",
                state=AlertmanagerSourceState.DEGRADED,
            ),
        ]

        for s in sources:
            inventory.add_source(s)

        auto_sources = inventory.get_by_state(AlertmanagerSourceState.AUTO_TRACKED)
        assert len(auto_sources) == 1
        assert auto_sources[0].source_id == "test:auto"

    def test_inventory_get_auto_tracked(self) -> None:
        """Test getting all tracked sources."""
        inventory = AlertmanagerSourceInventory()

        sources = [
            AlertmanagerSource(
                source_id="test:auto",
                endpoint="http://auto:9093",
                state=AlertmanagerSourceState.AUTO_TRACKED,
            ),
            AlertmanagerSource(
                source_id="test:manual",
                endpoint="http://manual:9093",
                state=AlertmanagerSourceState.MANUAL,
            ),
            AlertmanagerSource(
                source_id="test:degraded",
                endpoint="http://degraded:9093",
                state=AlertmanagerSourceState.DEGRADED,
            ),
        ]

        for s in sources:
            inventory.add_source(s)

        tracked = inventory.get_auto_tracked()
        assert len(tracked) == 2
        tracked_ids = {s.source_id for s in tracked}
        assert "test:auto" in tracked_ids
        assert "test:manual" in tracked_ids
        assert "test:degraded" not in tracked_ids


class TestInventorySerialization:
    """Tests for inventory serialization."""

    def test_inventory_to_dict_roundtrip(self) -> None:
        """Test inventory serialization and deserialization."""
        inventory = AlertmanagerSourceInventory(cluster_context="prod-cluster")

        source = AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager:9093",
            namespace="monitoring",
            name="main",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        )
        inventory.add_source(source)

        serialized = inventory.to_dict()
        restored = AlertmanagerSourceInventory.from_dict(serialized)

        assert len(restored.sources) == 1
        assert restored.cluster_context == "prod-cluster"
        assert "crd:monitoring/main" in restored.sources

    def test_inventory_empty_state(self) -> None:
        """Test that empty inventory has empty dicts."""
        inventory = AlertmanagerSourceInventory()

        assert len(inventory.sources) == 0
        assert inventory.get_by_origin(AlertmanagerSourceOrigin.MANUAL) == ()
        assert inventory.get_by_state(AlertmanagerSourceState.AUTO_TRACKED) == ()

    def test_missing_source_returns_empty_tuple(self) -> None:
        """Test that querying for non-existent sources returns empty tuple."""
        inventory = AlertmanagerSourceInventory()

        crd_sources = inventory.get_by_origin(AlertmanagerSourceOrigin.ALERTMANAGER_CRD)
        assert crd_sources == ()

        state_sources = inventory.get_by_state(AlertmanagerSourceState.AUTO_TRACKED)
        assert state_sources == ()

    def test_inventory_from_empty_dict(self) -> None:
        """Test that inventory from empty dict has empty sources."""
        inventory = AlertmanagerSourceInventory.from_dict({})

        assert len(inventory.sources) == 0
        assert inventory.cluster_context is None

    def test_inventory_from_dict_missing_fields(self) -> None:
        """Test that inventory handles missing fields gracefully."""
        data = {
            "sources": [
                {
                    "source_id": "test:source",
                    "endpoint": "http://test:9093",
                }
            ]
        }

        inventory = AlertmanagerSourceInventory.from_dict(data)

        assert len(inventory.sources) == 1
        source = inventory.sources["test:source"]
        # Should have defaults for missing fields
        assert source.origin == AlertmanagerSourceOrigin.SERVICE_HEURISTIC
        assert source.state == AlertmanagerSourceState.DISCOVERED


class TestDuplicateSources:
    """Tests for duplicate source handling."""

    def test_duplicate_same_origin_same_id(self) -> None:
        """Test that same source from same origin updates state correctly."""
        inventory = AlertmanagerSourceInventory()

        # Add first source (discovered state)
        inventory.add_source(AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager1:9093",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.DISCOVERED,
        ))

        # Add same source (auto-tracked state should replace)
        inventory.add_source(AlertmanagerSource(
            source_id="crd:monitoring/main",
            endpoint="http://alertmanager2:9093",
            origin=AlertmanagerSourceOrigin.ALERTMANAGER_CRD,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        ))

        # Should prefer AUTO_TRACKED state from same origin
        assert inventory.sources["crd:monitoring/main"].state == AlertmanagerSourceState.AUTO_TRACKED

    def test_duplicate_different_origins_manual_always_wins(self) -> None:
        """Test that manual always wins regardless of state."""
        inventory = AlertmanagerSourceInventory()

        # Add service heuristic first
        inventory.add_source(AlertmanagerSource(
            source_id="service:monitoring/alertmanager",
            endpoint="http://heuristic:9093",
            origin=AlertmanagerSourceOrigin.SERVICE_HEURISTIC,
            state=AlertmanagerSourceState.AUTO_TRACKED,
        ))

        # Add manual source with similar identity
        inventory.add_source(AlertmanagerSource(
            source_id="service:monitoring/alertmanager",
            endpoint="http://manual:9093",
            origin=AlertmanagerSourceOrigin.MANUAL,
            state=AlertmanagerSourceState.MANUAL,
        ))

        # Manual should win
        assert inventory.sources["service:monitoring/alertmanager"].origin == AlertmanagerSourceOrigin.MANUAL
