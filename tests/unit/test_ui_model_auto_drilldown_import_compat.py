# Copyright 2025 Sputnik Systems (https://sputnik.systems)
#
# Licensed under the Apache License, Version 2.0 (the License);
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an AS IS BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Module: model_auto_drilldown
# Slice: M-07

r'''Import compatibility tests for model_auto_drilldown modularization.

These tests verify that auto-drilldown-interpretation-related symbols remain importable
from k8s_diag_agent.ui.model after extraction to model_auto_drilldown.py.

Scope:
- AutoDrilldownInterpretationView
- _build_auto_drilldown_interpretations
'''

from __future__ import annotations

import unittest
from collections.abc import Mapping


class TestAutoDrilldownReExportedFromModel(unittest.TestCase):
    '''Verify auto-drilldown symbols are importable from model.py (re-export compatibility).'''

    def test_auto_drilldown_interpretation_view_importable(self) -> None:
        '''AutoDrilldownInterpretationView should be importable from model.'''
        from k8s_diag_agent.ui.model import AutoDrilldownInterpretationView
        assert AutoDrilldownInterpretationView is not None

    def test_build_auto_drilldown_interpretations_importable(self) -> None:
        '''_build_auto_drilldown_interpretations should be importable from model.'''
        from k8s_diag_agent.ui.model import _build_auto_drilldown_interpretations
        assert _build_auto_drilldown_interpretations is not None
        assert callable(_build_auto_drilldown_interpretations)


class TestAutoDrilldownImportableFromModule(unittest.TestCase):
    '''Verify auto-drilldown symbols are importable directly from model_auto_drilldown.py.'''

    def test_auto_drilldown_interpretation_view_from_module(self) -> None:
        '''AutoDrilldownInterpretationView should be importable from model_auto_drilldown.'''
        from k8s_diag_agent.ui.model_auto_drilldown import AutoDrilldownInterpretationView
        assert AutoDrilldownInterpretationView is not None

    def test_build_auto_drilldown_interpretations_from_module(self) -> None:
        '''_build_auto_drilldown_interpretations should be importable from model_auto_drilldown.'''
        from k8s_diag_agent.ui.model_auto_drilldown import _build_auto_drilldown_interpretations
        assert _build_auto_drilldown_interpretations is not None
        assert callable(_build_auto_drilldown_interpretations)


class TestAutoDrilldownInterpretationViewInstantiation(unittest.TestCase):
    '''Verify AutoDrilldownInterpretationView can be instantiated correctly.'''

    def test_view_minimal(self) -> None:
        '''AutoDrilldownInterpretationView should be instantiable with required fields.'''
        from k8s_diag_agent.ui.model_auto_drilldown import AutoDrilldownInterpretationView

        view = AutoDrilldownInterpretationView(
            adapter='k8sgpt',
            status='success',
            summary='Analysis complete',
            timestamp='2026-01-01T00:00:00Z',
            artifact_path='/path/to/artifact.json',
            provider='openai',
            duration_ms=1500,
            payload={'key': 'value'},
            error_summary=None,
            skip_reason=None,
        )
        assert view.adapter == 'k8sgpt'
        assert view.status == 'success'
        assert view.summary == 'Analysis complete'
        assert view.timestamp == '2026-01-01T00:00:00Z'
        assert view.artifact_path == '/path/to/artifact.json'
        assert view.provider == 'openai'
        assert view.duration_ms == 1500
        assert view.payload == {'key': 'value'}
        assert view.error_summary is None
        assert view.skip_reason is None

    def test_view_with_null_optional_fields(self) -> None:
        '''AutoDrilldownInterpretationView should handle null optional fields.'''
        from k8s_diag_agent.ui.model_auto_drilldown import AutoDrilldownInterpretationView

        view = AutoDrilldownInterpretationView(
            adapter='llamacpp',
            status='skipped',
            summary=None,
            timestamp='2026-01-01T00:00:00Z',
            artifact_path=None,
            provider=None,
            duration_ms=None,
            payload=None,
            error_summary=None,
            skip_reason='No clusters available',
        )
        assert view.adapter == 'llamacpp'
        assert view.status == 'skipped'
        assert view.summary is None
        assert view.timestamp == '2026-01-01T00:00:00Z'
        assert view.artifact_path is None
        assert view.provider is None
        assert view.duration_ms is None
        assert view.payload is None
        assert view.error_summary is None
        assert view.skip_reason == 'No clusters available'


class TestBuildAutoDrilldownInterpretationsBuilder(unittest.TestCase):
    '''Verify _build_auto_drilldown_interpretations builder function works correctly.'''

    def test_builder_with_valid_data(self) -> None:
        '''_build_auto_drilldown_interpretations should build mapping correctly from snake_case data.'''
        from k8s_diag_agent.ui.model_auto_drilldown import (  # noqa: F401 - used for type verification
            AutoDrilldownInterpretationView,
            _build_auto_drilldown_interpretations,
        )

        raw: Mapping[str, object] = {
            'cluster-a': {
                'adapter': 'k8sgpt',
                'status': 'success',
                'summary': 'Analysis complete',
                'timestamp': '2026-04-24T00:00:00Z',
                'artifact_path': '/path/to/result.json',
                'provider': 'openai',
                'duration_ms': 1500,
                'payload': {'findings': ['finding1', 'finding2']},
                'error_summary': None,
                'skip_reason': None,
            },
            'cluster-b': {
                'adapter': 'llamacpp',
                'status': 'failed',
                'summary': None,
                'timestamp': '2026-04-24T00:01:00Z',
                'artifact_path': None,
                'provider': None,
                'duration_ms': None,
                'payload': None,
                'error_summary': 'Connection timeout',
                'skip_reason': None,
            },
        }
        result = _build_auto_drilldown_interpretations(raw)
        assert isinstance(result, Mapping)
        assert len(result) == 2
        assert 'cluster-a' in result
        assert 'cluster-b' in result
        assert result['cluster-a'].adapter == 'k8sgpt'
        assert result['cluster-a'].status == 'success'
        assert result['cluster-b'].status == 'failed'
        assert result['cluster-b'].error_summary == 'Connection timeout'

    def test_builder_non_mapping_returns_empty_dict(self) -> None:
        '''_build_auto_drilldown_interpretations should return empty dict for non-Mapping input.'''
        from k8s_diag_agent.ui.model_auto_drilldown import _build_auto_drilldown_interpretations

        result = _build_auto_drilldown_interpretations(None)
        assert isinstance(result, Mapping)
        assert len(result) == 0

        result = _build_auto_drilldown_interpretations('not a mapping')
        assert isinstance(result, Mapping)
        assert len(result) == 0

        result = _build_auto_drilldown_interpretations([1, 2, 3])
        assert isinstance(result, Mapping)
        assert len(result) == 0

    def test_builder_skips_invalid_entries(self) -> None:
        '''_build_auto_drilldown_interpretations should skip entries where value is not a Mapping.'''
        from k8s_diag_agent.ui.model_auto_drilldown import _build_auto_drilldown_interpretations

        raw: Mapping[str, object] = {
            'valid-cluster': {
                'adapter': 'k8sgpt',
                'status': 'success',
                'timestamp': '2026-01-01T00:00:00Z',
            },
            'invalid-value-entry': 'not a mapping',  # invalid value (string, not Mapping)
            'another-valid': {
                'adapter': 'llamacpp',
                'status': 'skipped',
                'timestamp': '2026-01-01T00:00:00Z',
            },
        }

        result = _build_auto_drilldown_interpretations(raw)
        assert len(result) == 2
        assert 'valid-cluster' in result
        assert 'another-valid' in result
        assert 'invalid-value-entry' not in result

    def test_builder_with_empty_mapping(self) -> None:
        '''_build_auto_drilldown_interpretations should handle empty mapping.'''
        from k8s_diag_agent.ui.model_auto_drilldown import _build_auto_drilldown_interpretations

        raw: Mapping[str, object] = {}
        result = _build_auto_drilldown_interpretations(raw)
        assert isinstance(result, Mapping)
        assert len(result) == 0

    def test_builder_preserves_order(self) -> None:
        '''_build_auto_drilldown_interpretations should preserve iteration order.'''
        from k8s_diag_agent.ui.model_auto_drilldown import _build_auto_drilldown_interpretations

        raw: Mapping[str, object] = {
            'first': {'adapter': 'a', 'status': 'x', 'timestamp': 'x'},
            'second': {'adapter': 'b', 'status': 'x', 'timestamp': 'x'},
            'third': {'adapter': 'c', 'status': 'x', 'timestamp': 'x'},
        }
        result = _build_auto_drilldown_interpretations(raw)
        keys = list(result.keys())
        assert keys == ['first', 'second', 'third']

    def test_builder_missing_optional_fields(self) -> None:
        '''_build_auto_drilldown_interpretations should use defaults for missing optional fields.'''
        from k8s_diag_agent.ui.model_auto_drilldown import _build_auto_drilldown_interpretations

        raw: Mapping[str, object] = {
            'cluster': {
                'adapter': 'k8sgpt',
                'status': 'pending',
                'timestamp': '2026-01-01T00:00:00Z',
            }
        }
        result = _build_auto_drilldown_interpretations(raw)
        assert len(result) == 1
        view = result['cluster']
        assert view.adapter == 'k8sgpt'
        assert view.status == 'pending'
        assert view.summary is None
        assert view.artifact_path is None
        assert view.provider is None
        assert view.duration_ms is None
        assert view.payload is None
        assert view.error_summary is None
        assert view.skip_reason is None

    def test_builder_payload_handling(self) -> None:
        '''_build_auto_drilldown_interpretations should preserve payload when it's a Mapping.'''
        from k8s_diag_agent.ui.model_auto_drilldown import _build_auto_drilldown_interpretations

        raw: Mapping[str, object] = {
            'cluster': {
                'adapter': 'k8sgpt',
                'status': 'success',
                'timestamp': '2026-01-01T00:00:00Z',
                'payload': {'nested': {'data': 'value'}, 'list': [1, 2, 3]},
            }
        }
        result = _build_auto_drilldown_interpretations(raw)
        assert result['cluster'].payload == {'nested': {'data': 'value'}, 'list': [1, 2, 3]}

    def test_builder_payload_non_mapping_becomes_none(self) -> None:
        '''_build_auto_drilldown_interpretations should set payload to None when not a Mapping.'''
        from k8s_diag_agent.ui.model_auto_drilldown import _build_auto_drilldown_interpretations

        raw: Mapping[str, object] = {
            'cluster': {
                'adapter': 'k8sgpt',
                'status': 'success',
                'timestamp': '2026-01-01T00:00:00Z',
                'payload': 'string payload',
            }
        }
        result = _build_auto_drilldown_interpretations(raw)
        assert result['cluster'].payload is None


if __name__ == '__main__':
    unittest.main()
