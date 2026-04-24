"""Compatibility tests for model_notifications imports via ui.model re-exports.

These tests verify that NotificationView, _build_notification_history,
and _build_notification_details can be imported from the ui.model module
after the model_notifications.py extraction.
"""

import unittest


class NotificationImportCompatibilityTests(unittest.TestCase):
    """Verify notification views and builders are importable from ui.model."""

    def test_notification_view_importable_from_model(self) -> None:
        """NotificationView should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import NotificationView  # noqa: F401

    def test_notification_view_importable_from_notifications_module(self) -> None:
        """NotificationView should be importable from k8s_diag_agent.ui.model_notifications."""
        from k8s_diag_agent.ui.model_notifications import NotificationView  # noqa: F401

    def test_build_notification_history_importable_from_model(self) -> None:
        """_build_notification_history should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import _build_notification_history  # noqa: F401

    def test_build_notification_history_importable_from_notifications_module(self) -> None:
        """_build_notification_history should be importable from k8s_diag_agent.ui.model_notifications."""
        from k8s_diag_agent.ui.model_notifications import _build_notification_history  # noqa: F401

    def test_build_notification_details_importable_from_model(self) -> None:
        """_build_notification_details should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import _build_notification_details  # noqa: F401

    def test_build_notification_details_importable_from_notifications_module(self) -> None:
        """_build_notification_details should be importable from k8s_diag_agent.ui.model_notifications."""
        from k8s_diag_agent.ui.model_notifications import _build_notification_details  # noqa: F401

    def test_notification_view_instantiation(self) -> None:
        """NotificationView should be instantiable with required fields."""
        from k8s_diag_agent.ui.model import NotificationView

        view = NotificationView(
            kind="warning",
            summary="Test notification",
            timestamp="2026-01-01T00:00:00Z",
            run_id="run-1",
            cluster_label="cluster-a",
            context="Test context",
            details=(("key1", "value1"), ("key2", "value2")),
            artifact_path="/path/to/artifact.json",
        )
        self.assertEqual(view.kind, "warning")
        self.assertEqual(view.summary, "Test notification")
        self.assertEqual(view.timestamp, "2026-01-01T00:00:00Z")
        self.assertEqual(view.run_id, "run-1")
        self.assertEqual(view.cluster_label, "cluster-a")
        self.assertEqual(view.context, "Test context")
        self.assertEqual(view.details, (("key1", "value1"), ("key2", "value2")))
        self.assertEqual(view.artifact_path, "/path/to/artifact.json")
        self.assertIsNone(view.artifact_id)

    def test_notification_view_with_optional_fields(self) -> None:
        """NotificationView should accept optional fields including artifact_id."""
        from k8s_diag_agent.ui.model import NotificationView

        view = NotificationView(
            kind="info",
            summary="Another notification",
            timestamp="2026-04-24T10:00:00Z",
            run_id=None,
            cluster_label=None,
            context=None,
            details=(),
            artifact_path=None,
            artifact_id="01HX1234567890ABCDEFGHIJK",
        )
        self.assertIsNone(view.run_id)
        self.assertIsNone(view.cluster_label)
        self.assertIsNone(view.context)
        self.assertEqual(view.details, ())
        self.assertIsNone(view.artifact_path)
        self.assertEqual(view.artifact_id, "01HX1234567890ABCDEFGHIJK")

    def test_build_notification_history_null_input(self) -> None:
        """_build_notification_history should return empty tuple for null input."""
        from k8s_diag_agent.ui.model import _build_notification_history

        result = _build_notification_history(None)
        self.assertEqual(result, ())

    def test_build_notification_history_non_sequence_input(self) -> None:
        """_build_notification_history should return empty tuple for non-Sequence input."""
        from k8s_diag_agent.ui.model import _build_notification_history

        result = _build_notification_history("not a sequence")
        self.assertEqual(result, ())

        result = _build_notification_history(123)
        self.assertEqual(result, ())

        result = _build_notification_history({"key": "value"})
        self.assertEqual(result, ())

    def test_build_notification_history_valid_input(self) -> None:
        """_build_notification_history should build NotificationView tuple correctly."""
        from k8s_diag_agent.ui.model import NotificationView, _build_notification_history

        raw = [
            {
                "kind": "warning",
                "summary": "Cluster health degraded",
                "timestamp": "2026-01-01T12:00:00Z",
                "run_id": "run-1",
                "cluster_label": "cluster-a",
                "context": "Multiple pods failing",
                "details": [{"label": "reason", "value": "eviction"}],
                "artifact_path": "notifications/warning.json",
                "artifact_id": "01HX1234567890ABCDEFGHIJK",
            },
            {
                "kind": "info",
                "summary": "Check completed",
                "timestamp": "2026-01-01T12:30:00Z",
            },
        ]
        result = _build_notification_history(raw)
        self.assertEqual(len(result), 2)

        # First notification
        n1 = result[0]
        assert isinstance(n1, NotificationView)
        self.assertEqual(n1.kind, "warning")
        self.assertEqual(n1.summary, "Cluster health degraded")
        self.assertEqual(n1.timestamp, "2026-01-01T12:00:00Z")
        self.assertEqual(n1.run_id, "run-1")
        self.assertEqual(n1.cluster_label, "cluster-a")
        self.assertEqual(n1.context, "Multiple pods failing")
        self.assertEqual(n1.details, (("reason", "eviction"),))
        self.assertEqual(n1.artifact_path, "notifications/warning.json")
        self.assertEqual(n1.artifact_id, "01HX1234567890ABCDEFGHIJK")

        # Second notification with defaults
        n2 = result[1]
        assert isinstance(n2, NotificationView)
        self.assertEqual(n2.kind, "info")
        self.assertEqual(n2.summary, "Check completed")
        self.assertEqual(n2.timestamp, "2026-01-01T12:30:00Z")
        self.assertIsNone(n2.run_id)
        self.assertIsNone(n2.cluster_label)
        self.assertIsNone(n2.context)
        self.assertEqual(n2.details, ())
        self.assertIsNone(n2.artifact_path)
        self.assertIsNone(n2.artifact_id)

    def test_build_notification_history_skips_non_mapping_entries(self) -> None:
        """_build_notification_history should skip non-Mapping entries."""
        from k8s_diag_agent.ui.model import _build_notification_history

        raw = [
            {"kind": "warning", "summary": "Valid", "timestamp": "2026-01-01T00:00:00Z"},
            "not a mapping",
            None,
            123,
            {"kind": "info", "summary": "Also valid", "timestamp": "2026-01-01T00:00:00Z"},
        ]
        result = _build_notification_history(raw)
        self.assertEqual(len(result), 2)

    def test_build_notification_details_null_input(self) -> None:
        """_build_notification_details should return empty tuple for null input."""
        from k8s_diag_agent.ui.model import _build_notification_details

        result = _build_notification_details(None)
        self.assertEqual(result, ())

    def test_build_notification_details_non_sequence_input(self) -> None:
        """_build_notification_details should return empty tuple for non-Sequence input."""
        from k8s_diag_agent.ui.model import _build_notification_details

        result = _build_notification_details("not a sequence")
        self.assertEqual(result, ())

        result = _build_notification_details(123)
        self.assertEqual(result, ())

        result = _build_notification_details({"key": "value"})
        self.assertEqual(result, ())

    def test_build_notification_details_valid_input(self) -> None:
        """_build_notification_details should build tuple of (label, value) tuples correctly."""
        from k8s_diag_agent.ui.model import _build_notification_details

        raw = [
            {"label": "cluster", "value": "cluster-a"},
            {"label": "namespace", "value": "default"},
            {"label": "count", "value": "42"},
        ]
        result = _build_notification_details(raw)
        self.assertEqual(
            result,
            (("cluster", "cluster-a"), ("namespace", "default"), ("count", "42")),
        )

    def test_build_notification_details_skips_non_mapping_entries(self) -> None:
        """_build_notification_details should skip non-Mapping entries."""
        from k8s_diag_agent.ui.model import _build_notification_details

        raw = [
            {"label": "key1", "value": "value1"},
            "not a mapping",
            None,
            123,
            {"label": "key2", "value": "value2"},
        ]
        result = _build_notification_details(raw)
        self.assertEqual(result, (("key1", "value1"), ("key2", "value2")))

    def test_build_notification_details_coerces_non_string_values(self) -> None:
        """_build_notification_details should coerce non-string values to strings."""
        from k8s_diag_agent.ui.model import _build_notification_details

        raw = [
            {"label": "count", "value": 42},
            {"label": "enabled", "value": True},
            {"label": "ratio", "value": 3.14},
        ]
        result = _build_notification_details(raw)
        self.assertEqual(result[0], ("count", "42"))
        self.assertEqual(result[1], ("enabled", "True"))
        self.assertEqual(result[2], ("ratio", "3.14"))


if __name__ == "__main__":
    unittest.main()
