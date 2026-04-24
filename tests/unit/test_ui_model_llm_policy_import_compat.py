"""Compatibility tests for model_llm_policy imports via ui.model re-exports.

These tests verify that LLMPolicyView, AutoDrilldownPolicyView, ProviderExecutionBranchView,
ProviderExecutionView, and their builder functions can be imported from both the ui.model
module (for backward compatibility) and the ui.model_llm_policy module (the new canonical location).
"""

import unittest


class LLMPolicyImportCompatibilityTests(unittest.TestCase):
    """Verify LLM policy views and builders are importable from ui.model."""

    def test_llm_policy_view_importable_from_model(self) -> None:
        """LLMPolicyView should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import LLMPolicyView  # noqa: F401

    def test_auto_drilldown_policy_view_importable_from_model(self) -> None:
        """AutoDrilldownPolicyView should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import AutoDrilldownPolicyView  # noqa: F401

    def test_provider_execution_branch_view_importable_from_model(self) -> None:
        """ProviderExecutionBranchView should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import ProviderExecutionBranchView  # noqa: F401

    def test_provider_execution_view_importable_from_model(self) -> None:
        """ProviderExecutionView should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import ProviderExecutionView  # noqa: F401

    def test_build_llm_policy_view_importable_from_model(self) -> None:
        """_build_llm_policy_view should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import _build_llm_policy_view  # noqa: F401

    def test_build_auto_drilldown_policy_view_importable_from_model(self) -> None:
        """_build_auto_drilldown_policy_view should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import _build_auto_drilldown_policy_view  # noqa: F401

    def test_build_provider_execution_view_importable_from_model(self) -> None:
        """_build_provider_execution_view should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import _build_provider_execution_view  # noqa: F401

    def test_build_execution_branch_view_importable_from_model(self) -> None:
        """_build_execution_branch_view should be importable from k8s_diag_agent.ui.model."""
        from k8s_diag_agent.ui.model import _build_execution_branch_view  # noqa: F401

    def test_llm_policy_view_importable_from_llm_policy_module(self) -> None:
        """LLMPolicyView should be importable from k8s_diag_agent.ui.model_llm_policy."""
        from k8s_diag_agent.ui.model_llm_policy import LLMPolicyView  # noqa: F401

    def test_auto_drilldown_policy_view_importable_from_llm_policy_module(self) -> None:
        """AutoDrilldownPolicyView should be importable from k8s_diag_agent.ui.model_llm_policy."""
        from k8s_diag_agent.ui.model_llm_policy import AutoDrilldownPolicyView  # noqa: F401

    def test_provider_execution_branch_view_importable_from_llm_policy_module(self) -> None:
        """ProviderExecutionBranchView should be importable from k8s_diag_agent.ui.model_llm_policy."""
        from k8s_diag_agent.ui.model_llm_policy import ProviderExecutionBranchView  # noqa: F401

    def test_provider_execution_view_importable_from_llm_policy_module(self) -> None:
        """ProviderExecutionView should be importable from k8s_diag_agent.ui.model_llm_policy."""
        from k8s_diag_agent.ui.model_llm_policy import ProviderExecutionView  # noqa: F401

    def test_build_llm_policy_view_importable_from_llm_policy_module(self) -> None:
        """_build_llm_policy_view should be importable from k8s_diag_agent.ui.model_llm_policy."""
        from k8s_diag_agent.ui.model_llm_policy import _build_llm_policy_view  # noqa: F401

    def test_build_auto_drilldown_policy_view_importable_from_llm_policy_module(self) -> None:
        """_build_auto_drilldown_policy_view should be importable from k8s_diag_agent.ui.model_llm_policy."""
        from k8s_diag_agent.ui.model_llm_policy import _build_auto_drilldown_policy_view  # noqa: F401

    def test_build_provider_execution_view_importable_from_llm_policy_module(self) -> None:
        """_build_provider_execution_view should be importable from k8s_diag_agent.ui.model_llm_policy."""
        from k8s_diag_agent.ui.model_llm_policy import _build_provider_execution_view  # noqa: F401

    def test_build_execution_branch_view_importable_from_llm_policy_module(self) -> None:
        """_build_execution_branch_view should be importable from k8s_diag_agent.ui.model_llm_policy."""
        from k8s_diag_agent.ui.model_llm_policy import _build_execution_branch_view  # noqa: F401


class LLMPolicyViewInstantiationTests(unittest.TestCase):
    """Tests for LLM policy view instantiation and behavior."""

    def test_auto_drilldown_policy_view_instantiation(self) -> None:
        """AutoDrilldownPolicyView should be instantiable."""
        from k8s_diag_agent.ui.model import AutoDrilldownPolicyView

        view = AutoDrilldownPolicyView(
            enabled=True,
            provider="openai",
            max_per_run=5,
            used_this_run=2,
            successful_this_run=1,
            failed_this_run=0,
            skipped_this_run=1,
            budget_exhausted=False,
        )
        self.assertEqual(view.enabled, True)
        self.assertEqual(view.provider, "openai")
        self.assertEqual(view.max_per_run, 5)
        self.assertEqual(view.used_this_run, 2)

    def test_auto_drilldown_policy_view_defaults(self) -> None:
        """AutoDrilldownPolicyView should handle None budget_exhausted."""
        from k8s_diag_agent.ui.model import AutoDrilldownPolicyView

        view = AutoDrilldownPolicyView(
            enabled=False,
            provider="-",
            max_per_run=0,
            used_this_run=0,
            successful_this_run=0,
            failed_this_run=0,
            skipped_this_run=0,
            budget_exhausted=None,
        )
        self.assertIsNone(view.budget_exhausted)

    def test_llm_policy_view_instantiation(self) -> None:
        """LLMPolicyView should be instantiable."""
        from k8s_diag_agent.ui.model import AutoDrilldownPolicyView, LLMPolicyView

        ad_policy = AutoDrilldownPolicyView(
            enabled=True,
            provider="openai",
            max_per_run=5,
            used_this_run=2,
            successful_this_run=1,
            failed_this_run=0,
            skipped_this_run=1,
            budget_exhausted=False,
        )
        view = LLMPolicyView(auto_drilldown=ad_policy)
        self.assertIsNotNone(view.auto_drilldown)
        self.assertEqual(view.auto_drilldown.provider, "openai")

    def test_llm_policy_view_null_auto_drilldown(self) -> None:
        """LLMPolicyView should allow None auto_drilldown."""
        from k8s_diag_agent.ui.model import LLMPolicyView

        view = LLMPolicyView(auto_drilldown=None)
        self.assertIsNone(view.auto_drilldown)


class ProviderExecutionViewInstantiationTests(unittest.TestCase):
    """Tests for provider execution view instantiation and behavior."""

    def test_provider_execution_branch_view_instantiation(self) -> None:
        """ProviderExecutionBranchView should be instantiable."""
        from k8s_diag_agent.ui.model import ProviderExecutionBranchView

        view = ProviderExecutionBranchView(
            enabled=True,
            eligible=10,
            provider="openai",
            max_per_run=5,
            attempted=3,
            succeeded=2,
            failed=1,
            skipped=0,
            unattempted=7,
            budget_limited=0,
            notes="test notes",
        )
        self.assertEqual(view.enabled, True)
        self.assertEqual(view.eligible, 10)
        self.assertEqual(view.attempted, 3)
        self.assertEqual(view.succeeded, 2)
        self.assertEqual(view.failed, 1)

    def test_provider_execution_branch_view_defaults(self) -> None:
        """ProviderExecutionBranchView should handle all optional fields as None."""
        from k8s_diag_agent.ui.model import ProviderExecutionBranchView

        view = ProviderExecutionBranchView(
            enabled=None,
            eligible=None,
            provider=None,
            max_per_run=None,
            attempted=0,
            succeeded=0,
            failed=0,
            skipped=0,
            unattempted=None,
            budget_limited=None,
            notes=None,
        )
        self.assertIsNone(view.enabled)
        self.assertIsNone(view.eligible)
        self.assertIsNone(view.provider)
        self.assertIsNone(view.notes)

    def test_provider_execution_view_instantiation(self) -> None:
        """ProviderExecutionView should be instantiable."""
        from k8s_diag_agent.ui.model import ProviderExecutionBranchView, ProviderExecutionView

        ad_branch = ProviderExecutionBranchView(
            enabled=True,
            eligible=10,
            provider="openai",
            max_per_run=5,
            attempted=3,
            succeeded=2,
            failed=1,
            skipped=0,
            unattempted=7,
            budget_limited=0,
            notes=None,
        )
        view = ProviderExecutionView(auto_drilldown=ad_branch, review_enrichment=None)
        self.assertIsNotNone(view.auto_drilldown)
        self.assertIsNone(view.review_enrichment)


class BuildLLMPolicyBuilderTests(unittest.TestCase):
    """Tests for _build_llm_policy_view() builder function behavior."""

    def test_build_llm_policy_view_null_input(self) -> None:
        """_build_llm_policy_view should return None for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_llm_policy_view

        result = _build_llm_policy_view(None)
        self.assertIsNone(result)

    def test_build_llm_policy_view_non_mapping_input(self) -> None:
        """_build_llm_policy_view should return None for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_llm_policy_view

        result = _build_llm_policy_view("not a mapping")
        self.assertIsNone(result)

    def test_build_llm_policy_view_empty_mapping(self) -> None:
        """_build_llm_policy_view should return LLMPolicyView with None auto_drilldown for empty mapping."""
        from k8s_diag_agent.ui.model import LLMPolicyView, _build_llm_policy_view

        result = _build_llm_policy_view({})
        self.assertIsInstance(result, LLMPolicyView)
        self.assertIsNone(result.auto_drilldown)

    def test_build_llm_policy_view_with_auto_drilldown(self) -> None:
        """_build_llm_policy_view should build with auto_drilldown data."""
        from k8s_diag_agent.ui.model import LLMPolicyView, _build_llm_policy_view

        raw = {
            "auto_drilldown": {
                "enabled": True,
                "provider": "openai",
                "maxPerRun": 5,
                "usedThisRun": 2,
                "successfulThisRun": 1,
                "failedThisRun": 0,
                "skippedThisRun": 1,
                "budgetExhausted": False,
            }
        }
        result = _build_llm_policy_view(raw)
        self.assertIsInstance(result, LLMPolicyView)
        self.assertIsNotNone(result.auto_drilldown)
        self.assertEqual(result.auto_drilldown.provider, "openai")
        self.assertEqual(result.auto_drilldown.max_per_run, 5)


class BuildAutoDrilldownPolicyBuilderTests(unittest.TestCase):
    """Tests for _build_auto_drilldown_policy_view() builder function behavior."""

    def test_build_auto_drilldown_policy_view_null_input(self) -> None:
        """_build_auto_drilldown_policy_view should return None for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_auto_drilldown_policy_view

        result = _build_auto_drilldown_policy_view(None)
        self.assertIsNone(result)

    def test_build_auto_drilldown_policy_view_non_mapping_input(self) -> None:
        """_build_auto_drilldown_policy_view should return None for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_auto_drilldown_policy_view

        result = _build_auto_drilldown_policy_view("not a mapping")
        self.assertIsNone(result)

    def test_build_auto_drilldown_policy_view_full_data(self) -> None:
        """_build_auto_drilldown_policy_view should build with full data."""
        from k8s_diag_agent.ui.model import AutoDrilldownPolicyView, _build_auto_drilldown_policy_view

        raw = {
            "enabled": True,
            "provider": "openai",
            "maxPerRun": 5,
            "usedThisRun": 2,
            "successfulThisRun": 1,
            "failedThisRun": 0,
            "skippedThisRun": 1,
            "budgetExhausted": False,
        }
        result = _build_auto_drilldown_policy_view(raw)
        self.assertIsInstance(result, AutoDrilldownPolicyView)
        self.assertEqual(result.enabled, True)
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.max_per_run, 5)
        self.assertEqual(result.used_this_run, 2)
        self.assertEqual(result.budget_exhausted, False)

    def test_build_auto_drilldown_policy_view_missing_keys(self) -> None:
        """_build_auto_drilldown_policy_view should default missing keys."""
        from k8s_diag_agent.ui.model import _build_auto_drilldown_policy_view

        raw: dict[str, object] = {}
        result = _build_auto_drilldown_policy_view(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result.enabled, False)  # bool(None) = False
        self.assertEqual(result.provider, "-")  # _coerce_str default
        self.assertEqual(result.max_per_run, 0)  # _coerce_int default
        self.assertEqual(result.budget_exhausted, None)  # _coerce_optional_bool with None

    def test_build_auto_drilldown_policy_view_int_coercion(self) -> None:
        """_build_auto_drilldown_policy_view should coerce int fields from strings."""
        from k8s_diag_agent.ui.model import _build_auto_drilldown_policy_view

        raw = {
            "enabled": "true",
            "provider": "openai",
            "maxPerRun": "5",
            "usedThisRun": "2",
            "successfulThisRun": "1",
            "failedThisRun": "0",
            "skippedThisRun": "1",
        }
        result = _build_auto_drilldown_policy_view(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result.max_per_run, 5)
        self.assertEqual(result.used_this_run, 2)


class BuildProviderExecutionViewBuilderTests(unittest.TestCase):
    """Tests for _build_provider_execution_view() builder function behavior."""

    def test_build_provider_execution_view_null_input(self) -> None:
        """_build_provider_execution_view should return None for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_provider_execution_view

        result = _build_provider_execution_view(None)
        self.assertIsNone(result)

    def test_build_provider_execution_view_non_mapping_input(self) -> None:
        """_build_provider_execution_view should return None for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_provider_execution_view

        result = _build_provider_execution_view("not a mapping")
        self.assertIsNone(result)

    def test_build_provider_execution_view_empty_mapping(self) -> None:
        """_build_provider_execution_view should return view with None branches for empty mapping."""
        from k8s_diag_agent.ui.model import ProviderExecutionView, _build_provider_execution_view

        result = _build_provider_execution_view({})
        self.assertIsInstance(result, ProviderExecutionView)
        assert result is not None  # satisfies mypy: result can't be None to access attributes
        self.assertIsNone(result.auto_drilldown)
        self.assertIsNone(result.review_enrichment)

    def test_build_provider_execution_view_with_branches(self) -> None:
        """_build_provider_execution_view should build with branch data."""
        from k8s_diag_agent.ui.model import ProviderExecutionView, _build_provider_execution_view

        raw = {
            "auto_drilldown": {
                "enabled": True,
                "eligible": 10,
                "provider": "openai",
                "maxPerRun": 5,
                "attempted": 3,
                "succeeded": 2,
                "failed": 1,
                "skipped": 0,
                "unattempted": 7,
                "budgetLimited": 0,
                "notes": "test",
            },
            "review_enrichment": {
                "enabled": False,
                "eligible": 20,
                "provider": "anthropic",
                "maxPerRun": 10,
                "attempted": 0,
                "succeeded": 0,
                "failed": 0,
                "skipped": 0,
                "unattempted": 20,
                "budgetLimited": 0,
                "notes": None,
            },
        }
        result = _build_provider_execution_view(raw)
        self.assertIsInstance(result, ProviderExecutionView)
        self.assertIsNotNone(result.auto_drilldown)
        self.assertIsNotNone(result.review_enrichment)
        self.assertEqual(result.auto_drilldown.provider, "openai")
        self.assertEqual(result.review_enrichment.provider, "anthropic")


class BuildExecutionBranchViewBuilderTests(unittest.TestCase):
    """Tests for _build_execution_branch_view() builder function behavior."""

    def test_build_execution_branch_view_null_input(self) -> None:
        """_build_execution_branch_view should return None for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_execution_branch_view

        result = _build_execution_branch_view(None)
        self.assertIsNone(result)

    def test_build_execution_branch_view_non_mapping_input(self) -> None:
        """_build_execution_branch_view should return None for non-Mapping input."""
        from k8s_diag_agent.ui.model import _build_execution_branch_view

        result = _build_execution_branch_view("not a mapping")
        self.assertIsNone(result)

    def test_build_execution_branch_view_full_data(self) -> None:
        """_build_execution_branch_view should build with full data."""
        from k8s_diag_agent.ui.model import ProviderExecutionBranchView, _build_execution_branch_view

        raw = {
            "enabled": True,
            "eligible": 10,
            "provider": "openai",
            "maxPerRun": 5,
            "attempted": 3,
            "succeeded": 2,
            "failed": 1,
            "skipped": 0,
            "unattempted": 7,
            "budgetLimited": 0,
            "notes": "test notes",
        }
        result = _build_execution_branch_view(raw)
        self.assertIsInstance(result, ProviderExecutionBranchView)
        if result is None:
            self.fail("Expected non-None result from _build_execution_branch_view")
        self.assertIsNotNone(result.enabled)
        self.assertIsNotNone(result.eligible)
        self.assertIsNotNone(result.provider)
        self.assertIsNotNone(result.max_per_run)
        self.assertIsNotNone(result.attempted)
        self.assertIsNotNone(result.succeeded)
        self.assertIsNotNone(result.failed)
        self.assertIsNotNone(result.unattempted)
        self.assertIsNotNone(result.notes)
        self.assertEqual(result.enabled, True)
        self.assertEqual(result.eligible, 10)
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.max_per_run, 5)
        self.assertEqual(result.attempted, 3)
        self.assertEqual(result.succeeded, 2)
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.unattempted, 7)
        self.assertEqual(result.notes, "test notes")

    def test_build_execution_branch_view_missing_keys(self) -> None:
        """_build_execution_branch_view should default missing optional keys."""
        from k8s_diag_agent.ui.model import ProviderExecutionBranchView, _build_execution_branch_view

        raw = {
            "attempted": 5,
            "succeeded": 3,
            "failed": 1,
            "skipped": 1,
        }
        result = _build_execution_branch_view(raw)
        self.assertIsInstance(result, ProviderExecutionBranchView)
        if result is None:
            self.fail("Expected non-None result from _build_execution_branch_view")
        self.assertIsNotNone(result.attempted)
        self.assertIsNotNone(result.succeeded)
        self.assertEqual(result.attempted, 5)
        self.assertEqual(result.succeeded, 3)
        self.assertIsNone(result.enabled)
        self.assertIsNone(result.provider)
        self.assertIsNone(result.notes)

    def test_build_execution_branch_view_int_coercion(self) -> None:
        """_build_execution_branch_view should coerce int fields from strings."""
        from k8s_diag_agent.ui.model import _build_execution_branch_view

        raw = {
            "enabled": "true",
            "eligible": "10",
            "provider": "openai",
            "maxPerRun": "5",
            "attempted": "3",
            "succeeded": "2",
            "failed": "1",
            "skipped": "0",
            "unattempted": "7",
            "budgetLimited": "0",
        }
        result = _build_execution_branch_view(raw)
        if result is None:
            self.fail("Expected non-None result from _build_execution_branch_view")
        self.assertIsNotNone(result.eligible)
        self.assertIsNotNone(result.max_per_run)
        self.assertIsNotNone(result.attempted)
        self.assertEqual(result.eligible, 10)
        self.assertEqual(result.max_per_run, 5)
        self.assertEqual(result.attempted, 3)


if __name__ == "__main__":
    unittest.main()
