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

# Module: model_external_analysis
# Slice: M-06

r'''Import compatibility tests for model_external_analysis modularization.

These tests verify that external-analysis-related symbols remain importable
from k8s_diag_agent.ui.model after extraction to model_external_analysis.py.

Scope:
- ExternalAnalysisView
- ExternalAnalysisSummary
- _build_external_analysis
- _build_external_analysis_view
'''

from __future__ import annotations

import unittest
from collections.abc import Mapping


class TestExternalAnalysisReExportedFromModel(unittest.TestCase):
    '''Verify external-analysis symbols are importable from model.py (re-export compatibility).'''

    def test_external_analysis_view_importable(self) -> None:
        '''ExternalAnalysisView should be importable from model.'''
        from k8s_diag_agent.ui.model import ExternalAnalysisView
        assert ExternalAnalysisView is not None

    def test_external_analysis_summary_importable(self) -> None:
        '''ExternalAnalysisSummary should be importable from model.'''
        from k8s_diag_agent.ui.model import ExternalAnalysisSummary
        assert ExternalAnalysisSummary is not None

    def test_build_external_analysis_importable(self) -> None:
        '''_build_external_analysis should be importable from model.'''
        from k8s_diag_agent.ui.model import _build_external_analysis
        assert _build_external_analysis is not None
        assert callable(_build_external_analysis)

    def test_build_external_analysis_view_importable(self) -> None:
        '''_build_external_analysis_view should be importable from model.'''
        from k8s_diag_agent.ui.model import _build_external_analysis_view
        assert _build_external_analysis_view is not None
        assert callable(_build_external_analysis_view)


class TestExternalAnalysisImportableFromModule(unittest.TestCase):
    '''Verify external-analysis symbols are importable directly from model_external_analysis.py.'''

    def test_external_analysis_view_from_module(self) -> None:
        '''ExternalAnalysisView should be importable from model_external_analysis.'''
        from k8s_diag_agent.ui.model_external_analysis import ExternalAnalysisView
        assert ExternalAnalysisView is not None

    def test_external_analysis_summary_from_module(self) -> None:
        '''ExternalAnalysisSummary should be importable from model_external_analysis.'''
        from k8s_diag_agent.ui.model_external_analysis import ExternalAnalysisSummary
        assert ExternalAnalysisSummary is not None

    def test_build_external_analysis_from_module(self) -> None:
        '''_build_external_analysis should be importable from model_external_analysis.'''
        from k8s_diag_agent.ui.model_external_analysis import _build_external_analysis
        assert _build_external_analysis is not None
        assert callable(_build_external_analysis)

    def test_build_external_analysis_view_from_module(self) -> None:
        '''_build_external_analysis_view should be importable from model_external_analysis.'''
        from k8s_diag_agent.ui.model_external_analysis import _build_external_analysis_view
        assert _build_external_analysis_view is not None
        assert callable(_build_external_analysis_view)


class TestExternalAnalysisViewInstantiation(unittest.TestCase):
    '''Verify ExternalAnalysisView can be instantiated correctly.'''

    def test_view_minimal(self) -> None:
        '''ExternalAnalysisView should be instantiable with required fields.'''
        from k8s_diag_agent.ui.model_external_analysis import ExternalAnalysisView

        view = ExternalAnalysisView(
            tool_name='k8sgpt',
            cluster_label='prod-cluster',
            status='success',
            summary='Analysis complete',
            findings=('finding1', 'finding2'),
            suggested_next_checks=('check1',),
            timestamp='2026-01-01T00:00:00Z',
            artifact_path='/path/to/artifact.json',
        )
        assert view.tool_name == 'k8sgpt'
        assert view.cluster_label == 'prod-cluster'
        assert view.status == 'success'
        assert view.summary == 'Analysis complete'
        assert view.findings == ('finding1', 'finding2')
        assert view.suggested_next_checks == ('check1',)
        assert view.timestamp == '2026-01-01T00:00:00Z'
        assert view.artifact_path == '/path/to/artifact.json'

    def test_view_with_null_optional_fields(self) -> None:
        '''ExternalAnalysisView should handle null optional fields.'''
        from k8s_diag_agent.ui.model_external_analysis import ExternalAnalysisView

        view = ExternalAnalysisView(
            tool_name='llamacpp',
            cluster_label=None,
            status='skipped',
            summary=None,
            findings=(),
            suggested_next_checks=(),
            timestamp='2026-01-01T00:00:00Z',
            artifact_path=None,
        )
        assert view.tool_name == 'llamacpp'
        assert view.cluster_label is None
        assert view.status == 'skipped'
        assert view.summary is None
        assert view.findings == ()
        assert view.suggested_next_checks == ()
        assert view.artifact_path is None


class TestExternalAnalysisSummaryInstantiation(unittest.TestCase):
    '''Verify ExternalAnalysisSummary can be instantiated correctly.'''

    def test_summary_empty(self) -> None:
        '''ExternalAnalysisSummary should be instantiable with empty values.'''
        from k8s_diag_agent.ui.model_external_analysis import ExternalAnalysisSummary

        view = ExternalAnalysisSummary(
            count=0,
            status_counts=(),
            artifacts=(),
        )
        assert view.count == 0
        assert view.status_counts == ()
        assert view.artifacts == ()

    def test_summary_with_data(self) -> None:
        '''ExternalAnalysisSummary should hold multiple artifacts.'''
        from k8s_diag_agent.ui.model_external_analysis import (
            ExternalAnalysisSummary,
            ExternalAnalysisView,
        )

        artifact = ExternalAnalysisView(
            tool_name='k8sgpt',
            cluster_label='cluster-a',
            status='success',
            summary='Test',
            findings=('finding',),
            suggested_next_checks=('check',),
            timestamp='2026-01-01T00:00:00Z',
            artifact_path='/path.json',
        )
        view = ExternalAnalysisSummary(
            count=1,
            status_counts=(('success', 1),),
            artifacts=(artifact,),
        )
        assert view.count == 1
        assert len(view.status_counts) == 1
        assert view.status_counts[0] == ('success', 1)
        assert len(view.artifacts) == 1
        assert view.artifacts[0].tool_name == 'k8sgpt'


class TestBuildExternalAnalysisViewBuilder(unittest.TestCase):
    '''Verify _build_external_analysis_view builder function works correctly.'''

    def test_builder_with_valid_data(self) -> None:
        '''_build_external_analysis_view should build view correctly from snake_case data.'''
        from k8s_diag_agent.ui.model_external_analysis import (
            ExternalAnalysisView,
            _build_external_analysis_view,
        )

        raw: Mapping[str, object] = {
            'tool_name': 'llamacpp',
            'cluster_label': 'test-cluster',
            'status': 'success',
            'summary': 'Analysis complete',
            'findings': ['finding1', 'finding2'],
            'suggested_next_checks': ['kubectl get pods'],
            'timestamp': '2026-04-24T00:00:00Z',
            'artifact_path': '/path/to/result.json',
        }
        result = _build_external_analysis_view(raw)
        assert isinstance(result, ExternalAnalysisView)
        assert result.tool_name == 'llamacpp'
        assert result.cluster_label == 'test-cluster'
        assert result.status == 'success'
        assert result.summary == 'Analysis complete'
        assert result.findings == ('finding1', 'finding2')
        assert result.suggested_next_checks == ('kubectl get pods',)
        assert result.timestamp == '2026-04-24T00:00:00Z'
        assert result.artifact_path == '/path/to/result.json'

    def test_builder_missing_optional_fields(self) -> None:
        '''_build_external_analysis_view should use defaults for missing fields.'''
        from k8s_diag_agent.ui.model_external_analysis import (
            ExternalAnalysisView,
            _build_external_analysis_view,
        )

        raw: Mapping[str, object] = {
            'tool_name': 'k8sgpt',
            'status': 'pending',
            'timestamp': '2026-01-01T00:00:00Z',
        }
        result = _build_external_analysis_view(raw)
        assert isinstance(result, ExternalAnalysisView)
        assert result.tool_name == 'k8sgpt'
        assert result.cluster_label is None
        assert result.status == 'pending'
        assert result.summary is None
        assert result.findings == ()
        assert result.suggested_next_checks == ()
        assert result.timestamp == '2026-01-01T00:00:00Z'
        assert result.artifact_path is None


class TestBuildExternalAnalysisBuilder(unittest.TestCase):
    '''Verify _build_external_analysis builder function works correctly.'''

    def test_builder_with_valid_data(self) -> None:
        '''_build_external_analysis should build summary from full data.'''
        from k8s_diag_agent.ui.model_external_analysis import (
            ExternalAnalysisSummary,
            _build_external_analysis,
        )

        raw: Mapping[str, object] = {
            'count': 3,
            'status_counts': [
                {'status': 'success', 'count': 2},
                {'status': 'failed', 'count': 1},
            ],
            'artifacts': [
                {
                    'tool_name': 'k8sgpt',
                    'cluster_label': 'cluster-1',
                    'status': 'success',
                    'summary': 'Good',
                    'findings': [],
                    'suggested_next_checks': [],
                    'timestamp': '2026-01-01T00:00:00Z',
                    'artifact_path': '/a.json',
                },
            ],
        }
        result = _build_external_analysis(raw)
        assert isinstance(result, ExternalAnalysisSummary)
        assert result.count == 3
        assert len(result.status_counts) == 2
        assert result.status_counts[0] == ('success', 2)
        assert result.status_counts[1] == ('failed', 1)
        assert len(result.artifacts) == 1

    def test_builder_non_mapping_returns_defaults(self) -> None:
        '''_build_external_analysis should return defaults for non-Mapping input.'''
        from k8s_diag_agent.ui.model_external_analysis import (
            ExternalAnalysisSummary,
            _build_external_analysis,
        )

        result = _build_external_analysis(None)
        assert isinstance(result, ExternalAnalysisSummary)
        assert result.count == 0
        assert result.status_counts == ()
        assert result.artifacts == ()

        result = _build_external_analysis('not a mapping')
        assert isinstance(result, ExternalAnalysisSummary)
        assert result.count == 0

        result = _build_external_analysis([1, 2, 3])
        assert isinstance(result, ExternalAnalysisSummary)
        assert result.count == 0

    def test_builder_skips_invalid_status_counts(self) -> None:
        '''_build_external_analysis should skip non-Mapping entries in status_counts.'''
        from k8s_diag_agent.ui.model_external_analysis import _build_external_analysis

        raw: Mapping[str, object] = {
            'count': 1,
            'status_counts': [
                {'status': 'success', 'count': 1},
                'invalid',
                None,
                123,
            ],
            'artifacts': [],
        }
        result = _build_external_analysis(raw)
        assert len(result.status_counts) == 1
        assert result.status_counts[0] == ('success', 1)

    def test_builder_skips_invalid_artifacts(self) -> None:
        '''_build_external_analysis should skip non-Mapping entries in artifacts.'''
        from k8s_diag_agent.ui.model_external_analysis import _build_external_analysis

        raw: Mapping[str, object] = {
            'count': 1,
            'status_counts': [],
            'artifacts': [
                {
                    'tool_name': 'k8sgpt',
                    'status': 'success',
                    'timestamp': '2026-01-01T00:00:00Z',
                },
                'invalid',
                None,
                [],
            ],
        }
        result = _build_external_analysis(raw)
        assert len(result.artifacts) == 1
        assert result.artifacts[0].tool_name == 'k8sgpt'

    def test_builder_with_empty_lists(self) -> None:
        '''_build_external_analysis should handle empty lists.'''
        from k8s_diag_agent.ui.model_external_analysis import _build_external_analysis

        raw: Mapping[str, object] = {
            'count': 0,
            'status_counts': [],
            'artifacts': [],
        }
        result = _build_external_analysis(raw)
        assert result.count == 0
        assert result.status_counts == ()
        assert result.artifacts == ()


if __name__ == '__main__':
    unittest.main()