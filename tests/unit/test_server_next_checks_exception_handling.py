"""Tests for server_next_checks.py exception handling hardening.

These tests verify that the mutation write paths in server_next_checks.py
handle exceptions explicitly rather than using broad `except Exception` catches.
"""

import unittest


class TestExceptionTypesAreExplicit(unittest.TestCase):
    """Tests verifying that exception handlers use explicit exception tuples."""

    def test_artifact_persistence_catches_specific_exceptions(self) -> None:
        """Verify artifact persistence handler catches OSError, JSON, TypeError."""
        import inspect

        from k8s_diag_agent.ui import server_next_checks

        source = inspect.getsource(server_next_checks.handle_next_check_execution)

        # The artifact persistence handler should use explicit exception tuple
        # It should use `except (OSError, json.JSONDecodeError, TypeError)`
        self.assertIn(
            'except (OSError, json.JSONDecodeError, TypeError)',
            source,
            "Artifact persistence handler should use explicit exception tuple: "
            "(OSError, json.JSONDecodeError, TypeError)"
        )

    def test_ui_index_write_catches_specific_exceptions(self) -> None:
        """Verify ui-index write handler catches OSError, JSON, ValueError."""
        import inspect

        from k8s_diag_agent.ui import server_next_checks

        source = inspect.getsource(server_next_checks.handle_next_check_execution)

        # Check for the explicit handler in the source
        self.assertIn(
            'except (OSError, json.JSONDecodeError, ValueError)',
            source,
            "ui-index write handler should use explicit exception tuple: "
            "(OSError, json.JSONDecodeError, ValueError)"
        )

    def test_deterministic_promotion_catches_file_exceptions(self) -> None:
        """Verify deterministic promotion handler catches FileExistsError, OSError."""
        import inspect

        from k8s_diag_agent.ui import server_next_checks

        source = inspect.getsource(server_next_checks.handle_deterministic_promotion)

        # Should NOT use bare `except Exception`
        # Should use explicit tuple for file write failures
        self.assertIn(
            'except (FileExistsError, OSError)',
            source,
            "Deterministic promotion handler should use explicit exception tuple: "
            "(FileExistsError, OSError)"
        )

    def test_approval_write_catches_file_exceptions(self) -> None:
        """Verify approval handler catches FileExistsError, OSError."""
        import inspect

        from k8s_diag_agent.ui import server_next_checks

        source = inspect.getsource(server_next_checks.handle_next_check_approval)

        # Should NOT use bare `except Exception`
        # Should use explicit tuple for file write failures
        self.assertIn(
            'except (FileExistsError, OSError)',
            source,
            "Approval handler should use explicit exception tuple: "
            "(FileExistsError, OSError)"
        )


class TestLoggingIncludesSafeMetadata(unittest.TestCase):
    """Tests verifying that error logs include safe metadata only."""

    def test_artifact_persistence_logs_safe_fields(self) -> None:
        """Verify artifact persistence logging uses safe metadata fields."""
        import inspect

        from k8s_diag_agent.ui import server_next_checks

        source = inspect.getsource(server_next_checks.handle_next_check_execution)

        # Should log: artifact (basename), run_id, error
        # Should NOT log: raw request payloads, artifact JSON content, secrets
        self.assertIn('"artifact":', source)
        self.assertIn('"run_id":', source)
        self.assertIn('"error":', source)

        # Should NOT log these sensitive fields in error logs
        self.assertNotIn('"rawPayload"', source)
        self.assertNotIn('"bearer_token"', source)
        self.assertNotIn('"kubeconfig"', source)

    def test_ui_index_logs_safe_fields(self) -> None:
        """Verify ui-index logging uses safe metadata fields."""
        import inspect

        from k8s_diag_agent.ui import server_next_checks

        source = inspect.getsource(server_next_checks.handle_next_check_execution)

        # Should log: ui_index (basename), run_id, candidate_index, error
        self.assertIn('"ui_index":', source)
        self.assertIn('"run_id":', source)

    def test_promotion_logs_safe_fields(self) -> None:
        """Verify promotion logging uses safe metadata fields."""
        import inspect

        from k8s_diag_agent.ui import server_next_checks

        source = inspect.getsource(server_next_checks.handle_deterministic_promotion)

        # Should log: run_id, candidate_id, cluster_label, error
        self.assertIn('"run_id":', source)
        self.assertIn('"candidate_id":', source)
        self.assertIn('"cluster_label":', source)

    def test_approval_logs_safe_fields(self) -> None:
        """Verify approval logging uses safe metadata fields."""
        import inspect

        from k8s_diag_agent.ui import server_next_checks

        source = inspect.getsource(server_next_checks.handle_next_check_approval)

        # Should log: run_id, candidate_id, candidate_index, cluster_label, error
        self.assertIn('"run_id":', source)
        self.assertIn('"candidate_id":', source)


class TestUiIndexNestedExceptionHandler(unittest.TestCase):
    """Tests for nested ui-index touch exception handler correctness."""

    def test_touch_handler_logs_touch_exception_not_write_exception(self) -> None:
        """Verify touch failure handler logs touch_exc, not the outer exc.

        The bug was: `except OSError:` logged `str(exc)` (the outer exception)
        instead of the touch exception. The fix uses `except OSError as touch_exc:`
        and logs `str(touch_exc)`.
        """
        import inspect
        from k8s_diag_agent.ui import server_next_checks

        source = inspect.getsource(server_next_checks.handle_next_check_execution)

        # The touch handler should capture the exception as touch_exc
        self.assertIn('as touch_exc', source)

        # Verify we don't have the bug: the touch handler should NOT log 'str(exc)'
        # Instead it should log 'str(touch_exc)'
        lines = source.split('\n')
        in_touch_handler = False
        for i, line in enumerate(lines):
            if 'except OSError as touch_exc' in line:
                in_touch_handler = True
            if in_touch_handler and '"error": str(' in line:
                # Inside touch handler, should log str(touch_exc), not str(exc)
                self.assertIn('str(touch_exc)', line,
                    f"Line {i}: touch handler should log str(touch_exc), not str(exc)")
                break

    def test_touch_handler_has_exc_info(self) -> None:
        """Verify touch failure handler includes exc_info=True for debugging."""
        import inspect
        from k8s_diag_agent.ui import server_next_checks

        source = inspect.getsource(server_next_checks.handle_next_check_execution)

        # The touch handler should have exc_info=True
        self.assertIn('exc_info=True', source)

    def test_outer_ui_index_handler_has_exc_info(self) -> None:
        """Verify outer ui-index write handler includes exc_info=True."""
        import inspect
        from k8s_diag_agent.ui import server_next_checks

        source = inspect.getsource(server_next_checks.handle_next_check_execution)

        # Count exc_info=True occurrences in the ui-index section
        # There should be at least 2: one for write failure, one for touch failure
        exc_info_count = source.count('exc_info=True')
        self.assertGreaterEqual(exc_info_count, 2,
            "Should have at least 2 exc_info=True: one for write failure, one for touch failure")


if __name__ == "__main__":
    unittest.main()