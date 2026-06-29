"""Regression tests for ExecutionHistoryPanel split.

Ensures the split execution history components remain LLM-friendly
(i.e., all files are under the size threshold to avoid regression).
"""

from __future__ import annotations

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
