"""Regression tests for ExecutionHistoryPanel split.

Ensures the split execution history components remain LLM-friendly
(i.e., all files are under the size threshold to avoid regression).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# LLM-friendly size threshold (lines)
LLM_FRIENDLY_LINE_LIMIT = 500


class TestExecutionHistoryLLMFriendly:
    """Regression tests to ensure ExecutionHistoryPanel split remains LLM-friendly."""

    @pytest.mark.parametrize(
        "path",
        [
            "frontend/src/components/ExecutionHistoryPanel.tsx",
            "frontend/src/components/executionHistory/index.ts",
            "frontend/src/components/executionHistory/executionHistoryTypes.ts",
            "frontend/src/components/executionHistory/executionHistoryFiltersData.ts",
            "frontend/src/components/executionHistory/executionHistorySummary.ts",
            "frontend/src/components/executionHistory/executionHistoryKeys.ts",
            "frontend/src/components/executionHistory/executionHistoryFormat.ts",
            "frontend/src/components/executionHistory/ExecutionHistoryEmptyState.tsx",
            "frontend/src/components/executionHistory/ExecutionHistoryFilters.tsx",
            "frontend/src/components/executionHistory/ExecutionHistoryRow.tsx",
            "frontend/src/components/executionHistory/ExecutionHistorySummaryStrip.tsx",
            "frontend/src/components/executionHistory/UsefulnessFeedbackControl.tsx",
            "frontend/src/components/executionHistory/AlertmanagerRelevanceFeedbackControl.tsx",
        ],
        ids=lambda p: Path(p).name,
    )
    def test_execution_history_file_under_llm_friendly_limit(self, path: str) -> None:
        """Each execution history file must be under the LLM-friendly line limit.

        This prevents regression where files grow beyond the threshold after changes.
        """
        file_path = Path(path)
        assert file_path.exists(), f"File does not exist: {path}"

        content = file_path.read_text(encoding="utf-8")
        line_count = len(content.splitlines())

        assert line_count <= LLM_FRIENDLY_LINE_LIMIT, (
            f"{path} has {line_count} lines, exceeding the LLM-friendly limit of {LLM_FRIENDLY_LINE_LIMIT}. "
            "Consider splitting this file further."
        )

    def test_execution_history_panel_thin_container(self) -> None:
        """ExecutionHistoryPanel.tsx should remain a thin container.

        It should primarily import and compose child components,
        not contain the bulk of the implementation.
        """
        path = Path("frontend/src/components/ExecutionHistoryPanel.tsx")
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Thin container should be well under the limit
        assert len(lines) <= 200, (
            f"ExecutionHistoryPanel.tsx has {len(lines)} lines, which is too large for a thin container. "
            "Expected ~150 lines maximum."
        )

    def test_legacy_execution_history_filters_utility_file_does_not_exist(self) -> None:
        """Guard against re-creation of executionHistoryFilters.ts.

        On case-insensitive filesystems (macOS), executionHistoryFilters.ts collides
        with ExecutionHistoryFilters.tsx, causing ambiguous resolution and circular
        imports. The utility file was renamed to executionHistoryFiltersData.ts.
        """
        legacy_path = (
            Path("frontend/src/components/executionHistory")
            / "executionHistoryFilters.ts"
        )

        assert not legacy_path.exists(), (
            "Do not recreate executionHistoryFilters.ts; it collides by name with "
            "ExecutionHistoryFilters.tsx on case-insensitive filesystems. Use "
            "executionHistoryFiltersData.ts instead."
        )

    def test_execution_history_filters_component_imports_runtime_filter_options_from_data_module(
        self,
    ) -> None:
        """ExecutionHistoryFilters.tsx must import filter options as runtime values.

        This guards against a regression where filter option arrays are only
        re-exported (not imported), causing ReferenceError at runtime:
        'EXECUTION_OUTCOME_FILTER_OPTIONS is not defined'

        The component uses these values in JSX (e.g., map over them to render
        <option> elements), so they must be in the local module scope.

        Note: Type-only imports (import type { ... } from "...") would also be wrong
        because TypeScript erases import type from emitted JavaScript.
        """
        component = Path(
            "frontend/src/components/executionHistory/ExecutionHistoryFilters.tsx"
        ).read_text(encoding="utf-8")

        # Must have an actual runtime import statement (not just re-export)
        runtime_import = re.search(
            r"import\s*\{(?P<body>[^}]+)\}\s*from\s*[\"']\.\/executionHistoryFiltersData[\"']",
            component,
            flags=re.MULTILINE | re.DOTALL,
        )

        assert runtime_import is not None, (
            "ExecutionHistoryFilters.tsx must import filter option arrays as runtime "
            "values from executionHistoryFiltersData; re-export-only is not enough."
        )

        imported_names = runtime_import.group("body")

        assert "EXECUTION_OUTCOME_FILTER_OPTIONS" in imported_names, (
            "EXECUTION_OUTCOME_FILTER_OPTIONS must be in the runtime import statement"
        )
        assert "USEFULNESS_REVIEW_FILTER_OPTIONS" in imported_names, (
            "USEFULNESS_REVIEW_FILTER_OPTIONS must be in the runtime import statement"
        )

        # Must NOT import from the old colliding names
        assert (
            'from "./executionHistoryFilters"' not in component
        ), "Do not import from executionHistoryFilters (collides with ExecutionHistoryFilters.tsx)"
        assert (
            'from "./ExecutionHistoryFilters"' not in component
        ), "ExecutionHistoryFilters.tsx cannot import from itself"

    def test_execution_history_panel_reexports_build_execution_entry_key(self) -> None:
        """ExecutionHistoryPanel.tsx must re-export buildExecutionEntryKey.

        This guards against a regression where the facade drops named exports
        after splitting modules. The hook useAppNavigationHighlights.ts imports
        this function from the facade, so it must remain available.
        """
        panel = Path("frontend/src/components/ExecutionHistoryPanel.tsx")
        content = panel.read_text(encoding="utf-8")

        # Must export the function (on its own line in the multi-line export block)
        assert "buildExecutionEntryKey," in content and content.count("buildExecutionEntryKey") >= 2, (
            "ExecutionHistoryPanel.tsx must both import and re-export buildExecutionEntryKey "
            "for backward compatibility with useAppNavigationHighlights.ts"
        )

        # Must import from executionHistory submodule
        assert "./executionHistory" in content, (
            "buildExecutionEntryKey must come from the executionHistory module"
        )

    def test_app_navigation_highlight_import_contract_is_preserved(self) -> None:
        """useAppNavigationHighlights.ts must be able to import buildExecutionEntryKey.

        This is the consumer-side contract that must not break.
        """
        hook = Path("frontend/src/hooks/useAppNavigationHighlights.ts")
        panel = Path("frontend/src/components/ExecutionHistoryPanel.tsx")

        hook_content = hook.read_text(encoding="utf-8")
        panel_content = panel.read_text(encoding="utf-8")

        # The hook imports from the facade
        assert 'from "../components/ExecutionHistoryPanel"' in hook_content, (
            "useAppNavigationHighlights.ts should import from ExecutionHistoryPanel facade"
        )

        # The facade must export the function
        assert "buildExecutionEntryKey" in panel_content, (
            "buildExecutionEntryKey must be present in ExecutionHistoryPanel.tsx"
        )
