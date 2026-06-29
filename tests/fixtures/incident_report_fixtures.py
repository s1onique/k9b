"""Compatibility facade for incident report test fixtures.

This module re-exports all fixtures from the split fixture modules for backward compatibility.
Tests should migrate to importing directly from the appropriate fixture module.

Fixture ownership:
- incident_report_fixtures_base: _freshness helper
- incident_report_fixtures_golden: _fixture_healthy_no_incident, _fixture_degraded_single_cluster,
                                   _fixture_stale_provider_enriched_degraded
- incident_report_fixtures_feedback_useful: _fixture_useful_result_hypothesis_strengthened
- incident_report_fixtures_feedback_action: _fixture_executed_result_promotes_action,
                                          _fixture_executed_result_deprioritizes_action
- incident_report_fixtures_feedback_noisy: _fixture_noisy_result_no_material_change,
                                          _fixture_partial_result_unknown_resolved
- incident_report_fixtures_worklist_*: worklist fixtures
- incident_report_fixtures_temporal: _fixture_multi_signal_stale_with_enrichment
"""

from __future__ import annotations

from tests.fixtures.incident_report_fixtures_base import _freshness
from tests.fixtures.incident_report_fixtures_feedback_action import (
    _fixture_executed_result_deprioritizes_action,
    _fixture_executed_result_promotes_action,
)
from tests.fixtures.incident_report_fixtures_feedback_noisy import (
    _fixture_noisy_result_no_material_change,
    _fixture_partial_result_unknown_resolved,
)
from tests.fixtures.incident_report_fixtures_feedback_useful import (
    _fixture_useful_result_hypothesis_strengthened,
)
from tests.fixtures.incident_report_fixtures_golden import (
    _fixture_degraded_single_cluster,
    _fixture_healthy_no_incident,
    _fixture_stale_provider_enriched_degraded,
)
from tests.fixtures.incident_report_fixtures_temporal import (
    _fixture_multi_signal_stale_with_enrichment,
)
from tests.fixtures.incident_report_fixtures_worklist import (
    _fixture_approval_needed_item,
    _fixture_deterministic_only_no_command,
    _fixture_duplicate_candidates,
    _fixture_executed_with_usefulness,
    _fixture_multi_signal_executed_with_pending,
    _fixture_multi_signal_warnings_pods_missing,
    _fixture_queue_with_command,
)

__all__ = [
    "_fixture_approval_needed_item",
    "_fixture_degraded_single_cluster",
    "_fixture_deterministic_only_no_command",
    "_fixture_duplicate_candidates",
    "_fixture_executed_result_deprioritizes_action",
    "_fixture_executed_result_promotes_action",
    "_fixture_executed_with_usefulness",
    "_fixture_healthy_no_incident",
    "_fixture_multi_signal_executed_with_pending",
    "_fixture_multi_signal_stale_with_enrichment",
    "_fixture_multi_signal_warnings_pods_missing",
    "_fixture_noisy_result_no_material_change",
    "_fixture_partial_result_unknown_resolved",
    "_fixture_queue_with_command",
    "_fixture_stale_provider_enriched_degraded",
    "_fixture_useful_result_hypothesis_strengthened",
    "_freshness",
]
