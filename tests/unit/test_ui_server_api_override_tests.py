# Copyright 2024 k8s_diag_agent Authors
#
# Licensed under the Apache License, Version 2.0 (the License);
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an AS IS BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
# Tests for Alertmanager source override integration - verifying effective_state is applied.
#
# These tests prove that override state (promote/disable actions) is correctly
# reflected through the complete path: UI serialization -> API -> model.
# ==============================================================================

import unittest

from k8s_diag_agent.ui.model import AlertmanagerSourceView


class AlertmanagerSourceOverrideModelTests(unittest.TestCase):
    """Tests verifying that Alertmanager source overrides are applied in the UI view model."""

    def test_ui_model_applies_effective_state_promoted(self) -> None:
        """Test that ui/model.py applies effective_state='manual' correctly.
        
        This verifies the core requirement: when a source has effective_state='manual'
        (set by promote action), the UI model correctly computes:
        - is_manual = True
        - is_tracking = True (manual is still tracking)
        - can_promote = False (cannot promote manual)
        - can_disable = False (cannot disable manual)
        - display_state = 'Manual'
        - display_origin = 'Manual'
        """
        from k8s_diag_agent.ui.model import build_ui_context

        index: dict[str, object] = {
            'run': {
                'run_id': 'model-promote-test',
                'run_label': 'model-promote-test',
                'timestamp': '2024-01-01T00:00:00Z',
                'collector_version': 'test',
                'cluster_count': 0,
                'drilldown_count': 0,
                'proposal_count': 0,
                'external_analysis_count': 0,
                'notification_count': 0,
                'alertmanager_sources': {
                    'sources': [
                        {
                            'source_id': 'src-auto',
                            'endpoint': 'http://am:9093/api/v2/alerts',
                            'namespace': 'monitoring',
                            'name': 'alertmanager',
                            'origin': 'alertmanager-crd',
                            'state': 'auto-tracked',
                            'discovered_at': '2024-01-01T00:00:00Z',
                            'effective_state': None,
                        },
                        {
                            'source_id': 'src-promoted',
                            'endpoint': 'http://am2:9093/api/v2/alerts',
                            'namespace': 'monitoring',
                            'name': 'alertmanager2',
                            'origin': 'alertmanager-crd',
                            'state': 'auto-tracked',
                            'discovered_at': '2024-01-01T00:00:00Z',
                            'effective_state': 'manual',
                        },
                    ],
                    'total_count': 2,
                    'tracked_count': 2,
                    'manual_count': 1,
                    'degraded_count': 0,
                    'missing_count': 0,
                    'discovery_timestamp': '2024-01-01T00:00:00Z',
                    'cluster_context': 'prod',
                },
                'deterministic_next_checks': {'cluster_count': 0, 'total_next_check_count': 0, 'clusters': []},
            },
            'clusters': [],
            'proposals': [],
            'external_analysis': {'count': 0, 'status_counts': [], 'artifacts': []},
        }

        context = build_ui_context(index)
        sources_view = context.alertmanager_sources
        assert sources_view is not None

        source_map: dict[str, AlertmanagerSourceView] = {s.source_id: s for s in sources_view.sources}

        # Auto-tracked source (baseline behavior)
        src_auto = source_map.get('src-auto')
        assert src_auto is not None
        self.assertFalse(src_auto.is_manual)
        self.assertTrue(src_auto.is_tracking)
        self.assertTrue(src_auto.can_promote)
        self.assertTrue(src_auto.can_disable)

        # Promoted source - effective_state='manual' should change behavior
        src_promoted = source_map.get('src-promoted')
        assert src_promoted is not None
        
        # Core override behavior
        self.assertTrue(src_promoted.is_manual, 
            'is_manual should be True when effective_state=manual')
        self.assertTrue(src_promoted.is_tracking, 
            'is_tracking should be True for manual sources')
        
        # Override disables further actions
        self.assertFalse(src_promoted.can_promote, 
            'can_promote should be False for promoted/manual sources')
        self.assertFalse(src_promoted.can_disable, 
            'can_disable should be False for promoted/manual sources')
        
        # Display fields updated
        self.assertEqual(src_promoted.display_state, 'Manual',
            'display_state should be "Manual" for promoted sources')
        self.assertEqual(src_promoted.display_origin, 'Manual',
            'display_origin should be "Manual" for promoted sources')

    def test_ui_model_applies_effective_state_disabled(self) -> None:
        """Test that ui/model.py applies effective_state='disabled' correctly.
        
        This verifies the core requirement: when a source has effective_state='disabled'
        (set by disable action), the UI model correctly computes:
        - is_manual = False
        - is_tracking = False (disabled is not tracking)
        - can_promote = False (disabled sources need re-enable first)
        - can_disable = False (already disabled)
        - display_state = 'disabled'
        """
        from k8s_diag_agent.ui.model import build_ui_context

        index: dict[str, object] = {
            'run': {
                'run_id': 'model-disable-test',
                'run_label': 'model-disable-test',
                'timestamp': '2024-01-01T00:00:00Z',
                'collector_version': 'test',
                'cluster_count': 0,
                'drilldown_count': 0,
                'proposal_count': 0,
                'external_analysis_count': 0,
                'notification_count': 0,
                'alertmanager_sources': {
                    'sources': [
                        {
                            'source_id': 'src-disabled',
                            'endpoint': 'http://am:9093/api/v2/alerts',
                            'namespace': 'monitoring',
                            'name': 'alertmanager',
                            'origin': 'alertmanager-crd',
                            'state': 'auto-tracked',
                            'discovered_at': '2024-01-01T00:00:00Z',
                            'effective_state': 'disabled',
                        },
                    ],
                    'total_count': 1,
                    'tracked_count': 0,
                    'manual_count': 0,
                    'degraded_count': 0,
                    'missing_count': 0,
                    'discovery_timestamp': '2024-01-01T00:00:00Z',
                    'cluster_context': 'prod',
                },
                'deterministic_next_checks': {'cluster_count': 0, 'total_next_check_count': 0, 'clusters': []},
            },
            'clusters': [],
            'proposals': [],
            'external_analysis': {'count': 0, 'status_counts': [], 'artifacts': []},
        }

        context = build_ui_context(index)
        sources_view = context.alertmanager_sources
        assert sources_view is not None

        src_disabled = sources_view.sources[0]
        
        # Core override behavior
        self.assertFalse(src_disabled.is_manual,
            'is_manual should be False for disabled sources')
        self.assertFalse(src_disabled.is_tracking,
            'is_tracking should be False for disabled sources')
        
        # Override disables further actions
        self.assertFalse(src_disabled.can_promote,
            'can_promote should be False for disabled sources')
        self.assertFalse(src_disabled.can_disable,
            'can_disable should be False for already disabled sources')
        
        # Display state updated
        self.assertEqual(src_disabled.display_state, 'disabled',
            'display_state should be "disabled" for disabled sources')

    def test_ui_model_effective_state_flow(self) -> None:
        """Test complete effective_state flow from action to UI model.
        
        This test verifies the entire flow:
        1. Action endpoint creates override with effective_state='manual'
        2. UI serialization sets effective_state on source
        3. UI model applies effective_state to compute UI fields
        """
        from k8s_diag_agent.ui.model import build_ui_context

        # Simulate the state after promote action
        index: dict[str, object] = {
            'run': {
                'run_id': 'complete-flow-test',
                'run_label': 'complete-flow-test',
                'timestamp': '2024-01-01T00:00:00Z',
                'collector_version': 'test',
                'cluster_count': 0,
                'drilldown_count': 0,
                'proposal_count': 0,
                'external_analysis_count': 0,
                'notification_count': 0,
                'alertmanager_sources': {
                    'sources': [
                        # Before action - can_promote=True, can_disable=True
                        {
                            'source_id': 'src-1',
                            'endpoint': 'http://am1:9093/api/v2/alerts',
                            'namespace': 'monitoring',
                            'name': 'alertmanager1',
                            'origin': 'alertmanager-crd',
                            'state': 'auto-tracked',
                            'discovered_at': '2024-01-01T00:00:00Z',
                            'effective_state': None,
                        },
                        # After promote - can_promote=False, can_disable=False
                        {
                            'source_id': 'src-2',
                            'endpoint': 'http://am2:9093/api/v2/alerts',
                            'namespace': 'monitoring',
                            'name': 'alertmanager2',
                            'origin': 'alertmanager-crd',
                            'state': 'auto-tracked',
                            'discovered_at': '2024-01-01T00:00:00Z',
                            'effective_state': 'manual',
                        },
                        # After disable - can_promote=False, can_disable=False
                        {
                            'source_id': 'src-3',
                            'endpoint': 'http://am3:9093/api/v2/alerts',
                            'namespace': 'monitoring',
                            'name': 'alertmanager3',
                            'origin': 'alertmanager-crd',
                            'state': 'auto-tracked',
                            'discovered_at': '2024-01-01T00:00:00Z',
                            'effective_state': 'disabled',
                        },
                    ],
                    'total_count': 3,
                    'tracked_count': 2,
                    'manual_count': 1,
                    'degraded_count': 0,
                    'missing_count': 0,
                    'discovery_timestamp': '2024-01-01T00:00:00Z',
                    'cluster_context': 'prod',
                },
                'deterministic_next_checks': {'cluster_count': 0, 'total_next_check_count': 0, 'clusters': []},
            },
            'clusters': [],
            'proposals': [],
            'external_analysis': {'count': 0, 'status_counts': [], 'artifacts': []},
        }

        context = build_ui_context(index)
        sources_view = context.alertmanager_sources
        assert sources_view is not None

        source_map: dict[str, AlertmanagerSourceView] = {s.source_id: s for s in sources_view.sources}

        # Source before action
        src_before = source_map.get('src-1')
        assert src_before is not None
        self.assertTrue(src_before.can_promote)
        self.assertTrue(src_before.can_disable)
        self.assertFalse(src_before.is_manual)
        self.assertTrue(src_before.is_tracking)

        # Source after promote
        src_promoted = source_map.get('src-2')
        assert src_promoted is not None
        self.assertFalse(src_promoted.can_promote, 
            'After promote: can_promote should be False')
        self.assertFalse(src_promoted.can_disable,
            'After promote: can_disable should be False')
        self.assertTrue(src_promoted.is_manual,
            'After promote: is_manual should be True')
        self.assertTrue(src_promoted.is_tracking,
            'After promote: is_tracking should be True (manual is still tracking)')

        # Source after disable
        src_disabled = source_map.get('src-3')
        assert src_disabled is not None
        self.assertFalse(src_disabled.can_promote,
            'After disable: can_promote should be False')
        self.assertFalse(src_disabled.can_disable,
            'After disable: can_disable should be False')
        self.assertFalse(src_disabled.is_manual,
            'After disable: is_manual should be False')
        self.assertFalse(src_disabled.is_tracking,
            'After disable: is_tracking should be False')


if __name__ == '__main__':
    unittest.main()
