"""Compatibility tests for model_feedback imports via ui.model re-exports.

These tests verify that FeedbackSummaryView, FeedbackAdaptationProvenanceView,
and their builder functions can be imported from the ui.model module after the
model_feedback.py extraction.
"""

import unittest


class FeedbackImportCompatibilityTests(unittest.TestCase):
    """Verify feedback views and builders are importable from ui.model."""

    def test_feedback_summary_view_importable(self) -> None:
        """FeedbackSummaryView should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import FeedbackSummaryView  # noqa: F401

    def test_feedback_adaptation_provenance_view_importable(self) -> None:
        """FeedbackAdaptationProvenanceView should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import FeedbackAdaptationProvenanceView  # noqa: F401

    def test_build_feedback_summary_view_importable(self) -> None:
        """_build_feedback_summary_view should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import _build_feedback_summary_view  # noqa: F401

    def test_build_feedback_adaptation_provenance_view_importable(self) -> None:
        """_build_feedback_adaptation_provenance_view should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import _build_feedback_adaptation_provenance_view  # noqa: F401

    def test_feedback_summary_view_instantiation(self) -> None:
        """FeedbackSummaryView should be instantiable."""
        from k8s_diag_agent.ui.model import FeedbackSummaryView

        view = FeedbackSummaryView(
            total_entries=5,
            namespaces_with_feedback=("ns-a", "ns-b"),
            clusters_with_feedback=("cluster-1",),
            services_with_feedback=("svc-x",),
        )
        self.assertEqual(view.total_entries, 5)
        self.assertEqual(view.namespaces_with_feedback, ("ns-a", "ns-b"))
        self.assertEqual(view.clusters_with_feedback, ("cluster-1",))
        self.assertEqual(view.services_with_feedback, ("svc-x",))

    def test_feedback_summary_view_default_values(self) -> None:
        """FeedbackSummaryView should have correct defaults."""
        from k8s_diag_agent.ui.model import FeedbackSummaryView

        view = FeedbackSummaryView()
        self.assertEqual(view.total_entries, 0)
        self.assertEqual(view.namespaces_with_feedback, ())
        self.assertEqual(view.clusters_with_feedback, ())
        self.assertEqual(view.services_with_feedback, ())
        self.assertIsNone(view.summary_text)

    def test_build_feedback_summary_view_null_input(self) -> None:
        """_build_feedback_summary_view should return None for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_feedback_summary_view

        result = _build_feedback_summary_view(None)
        self.assertIsNone(result)

        result = _build_feedback_summary_view("not a mapping")
        self.assertIsNone(result)

    def test_build_feedback_summary_view_valid_input(self) -> None:
        """_build_feedback_summary_view should build FeedbackSummaryView correctly."""
        from k8s_diag_agent.ui.model import FeedbackSummaryView, _build_feedback_summary_view

        raw = {
            "total_entries": 10,
            "namespaces_with_feedback": ["ns-a", "ns-b"],
            "clusters_with_feedback": ["cluster-1", "cluster-2"],
            "services_with_feedback": ["svc-x"],
        }
        result = _build_feedback_summary_view(raw)
        self.assertIsNotNone(result)
        assert isinstance(result, FeedbackSummaryView)
        self.assertEqual(result.total_entries, 10)
        self.assertEqual(result.namespaces_with_feedback, ("ns-a", "ns-b"))
        self.assertEqual(result.clusters_with_feedback, ("cluster-1", "cluster-2"))
        self.assertEqual(result.services_with_feedback, ("svc-x",))

    def test_build_feedback_summary_view_camelcase_input(self) -> None:
        """_build_feedback_summary_view should handle camelCase keys."""
        from k8s_diag_agent.ui.model import FeedbackSummaryView, _build_feedback_summary_view

        raw = {
            "totalEntries": 7,
            "namespacesWithFeedback": ["ns-c"],
            "clustersWithFeedback": ["cluster-3"],
            "servicesWithFeedback": ["svc-y", "svc-z"],
        }
        result = _build_feedback_summary_view(raw)
        self.assertIsNotNone(result)
        assert isinstance(result, FeedbackSummaryView)
        self.assertEqual(result.total_entries, 7)
        self.assertEqual(result.namespaces_with_feedback, ("ns-c",))
        self.assertEqual(result.clusters_with_feedback, ("cluster-3",))
        self.assertEqual(result.services_with_feedback, ("svc-y", "svc-z"))


if __name__ == "__main__":
    unittest.main()
