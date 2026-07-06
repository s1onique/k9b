"""Alertmanager webhook payload fixtures for testing.

This module provides fixtures for testing alert signal normalization.
It includes payloads for various alert scenarios.

FixturEs:
- Single firing alert
- Single resolved alert
- Grouped firing alerts
- Mixed firing/resolved group
- Missing optional fields
- Large labels/annotations requiring bounds
- Invalid payload

This module is a thin compatibility facade that re-exports fixtures from
specialized modules. For new code, import directly from the appropriate module:
- alertmanager_payload_basic_fixtures: single_firing_alert_payload, single_resolved_alert_payload
- alertmanager_payload_grouped_fixtures: grouped_firing_alerts_payload, mixed_firing_resolved_group_payload
- alertmanager_payload_invalid_fixtures: minimal_alert_payload, missing_alertname_payload, etc.
- alertmanager_payload_bounds_fixtures: large_labels_payload, large_value_payload, etc.
- alertmanager_payload_vmalert_fixtures: vmalert_firing_payload, vmalert_resolved_payload
"""

from __future__ import annotations

# Re-export from basic fixtures
from tests.fixtures.alertmanager_payload_basic_fixtures import (
    single_firing_alert_payload,
    single_resolved_alert_payload,
)

# Re-export from bounds fixtures
from tests.fixtures.alertmanager_payload_bounds_fixtures import (
    empty_labels_payload,
    large_labels_payload,
    large_value_payload,
    special_characters_payload,
)

# Re-export from grouped fixtures
from tests.fixtures.alertmanager_payload_grouped_fixtures import (
    grouped_firing_alerts_payload,
    mixed_firing_resolved_group_payload,
)

# Re-export from invalid fixtures
from tests.fixtures.alertmanager_payload_invalid_fixtures import (
    invalid_alerts_field_payload,
    invalid_status_payload,
    minimal_alert_payload,
    missing_alertname_payload,
    missing_alerts_field_payload,
    non_string_labels_payload,
)

# Re-export from vmalert fixtures
from tests.fixtures.alertmanager_payload_vmalert_fixtures import (
    vmalert_firing_payload,
    vmalert_resolved_payload,
)

__all__ = [
    # Basic
    "single_firing_alert_payload",
    "single_resolved_alert_payload",
    # Grouped
    "grouped_firing_alerts_payload",
    "mixed_firing_resolved_group_payload",
    # Invalid
    "minimal_alert_payload",
    "missing_alertname_payload",
    "missing_alerts_field_payload",
    "invalid_alerts_field_payload",
    "invalid_status_payload",
    "non_string_labels_payload",
    # Bounds
    "large_labels_payload",
    "large_value_payload",
    "empty_labels_payload",
    "special_characters_payload",
    # vmalert
    "vmalert_firing_payload",
    "vmalert_resolved_payload",
]
