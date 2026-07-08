"""Tool Output Reducers for k9b incident workbench.

This module provides server-side reducers that transform raw tool output into
bounded, schema-stable, LLM-visible artifacts with explicit provenance tracking.

Reference: META-K9B-HOLMESGPT-FACTORY-TRANSFER01 / ACT-K9B-TOOL-OUTPUT-REDUCERS01
"""
from __future__ import annotations

from typing import Any

from .tool_reducer_protocol import (
    REDUCER_SCHEMA_VERSION,
    ToolOutputReducer,
    ToolReducedOutput,
)


def _reduce_string_fallback(
    raw_output: str,
    max_bytes: int,
    source_tool: str,
    raw_artifact_id: str | None,
    reason: str,
) -> ToolReducedOutput:
    """Fallback reducer for non-reducible content."""
    output_bytes = len(raw_output.encode("utf-8"))
    truncated = output_bytes > max_bytes

    if truncated:
        limit = int(max_bytes * 0.95)
        visible = raw_output[:limit]
    else:
        visible = raw_output

    return ToolReducedOutput(
        schema_version=REDUCER_SCHEMA_VERSION,
        source_tool=source_tool,
        raw_artifact_id=raw_artifact_id,
        reduction_policy="string_fallback",
        counts={
            "raw_items": 1,
            "visible_items": 1 if not truncated else 0,
            "omitted_items": 1 if truncated else 0,
        },
        truncated=truncated,
        redacted=False,
        llm_visible={"text": visible, "bytes": len(visible.encode("utf-8"))},
        truncation_reason=reason if truncated else None,
    )


class JsonTreeReducer(ToolOutputReducer):
    """Reducer for JSON-structured tool output.

    This reducer:
    - Traverses JSON trees
    - Limits item counts in arrays
    - Truncates long string values
    - Preserves structure with count metadata
    - Reports what was omitted
    """

    def __init__(
        self,
        *,
        max_items_per_array: int = 100,
        max_string_length: int = 2000,
        max_depth: int = 10,
    ) -> None:
        self.max_items_per_array = max_items_per_array
        self.max_string_length = max_string_length
        self.max_depth = max_depth

    def reduce(
        self,
        raw_output: str | dict[str, Any],
        *,
        max_bytes: int,
        source_tool: str,
        raw_artifact_id: str | None = None,
    ) -> ToolReducedOutput:
        """Reduce JSON output by limiting array sizes and truncating strings."""
        if isinstance(raw_output, str):
            try:
                import json
                data = json.loads(raw_output)
            except (json.JSONDecodeError, ValueError):
                return _reduce_string_fallback(
                    raw_output, max_bytes, source_tool, raw_artifact_id, "json_parse_error"
                )
        else:
            data = raw_output

        raw_count = self._count_items(data)
        reduced, visible_count = self._reduce_structure(data, self.max_depth)

        import json
        reduced_json = json.dumps(reduced)
        if len(reduced_json.encode("utf-8")) > max_bytes:
            reduced = self._truncate_to_bytes(reduced, max_bytes)
            reduced_json = json.dumps(reduced)
            visible_count = self._count_items(reduced)

        return ToolReducedOutput(
            schema_version=REDUCER_SCHEMA_VERSION,
            source_tool=source_tool,
            raw_artifact_id=raw_artifact_id,
            reduction_policy="json_tree",
            counts={
                "raw_items": raw_count,
                "visible_items": visible_count,
                "omitted_items": max(0, raw_count - visible_count),
            },
            truncated=len(reduced_json.encode("utf-8")) < len(json.dumps(data).encode("utf-8")),
            redacted=False,
            llm_visible={"data": reduced, "bytes": len(reduced_json.encode("utf-8"))},
        )

    def _count_items(self, data: Any) -> int:
        """Count total items in data structure."""
        if isinstance(data, list):
            return len(data) + sum(self._count_items(item) for item in data)
        elif isinstance(data, dict):
            return len(data) + sum(self._count_items(v) for v in data.values())
        return 1

    def _reduce_structure(self, data: Any, depth: int) -> tuple[Any, int]:
        """Recursively reduce structure, returning (reduced, visible_count)."""
        if depth <= 0:
            return None, 0

        if isinstance(data, list):
            result: list[Any] = []
            visible = 0
            for i, item in enumerate(data):
                if i >= self.max_items_per_array:
                    break
                reduced_item, item_count = self._reduce_structure(item, depth - 1)
                if reduced_item is not None:
                    result.append(reduced_item)
                    visible += item_count
                else:
                    visible += 1
            return result, visible
        elif isinstance(data, dict):
            result: dict[str, Any] = {}  # type: ignore[no-redef]
            visible = 0
            for key, value in list(data.items())[: self.max_items_per_array]:
                reduced_value, value_count = self._reduce_structure(value, depth - 1)
                if reduced_value is not None:
                    result[key] = reduced_value
                    visible += value_count
                else:
                    visible += 1
            return result, visible
        elif isinstance(data, str):
            if len(data) > self.max_string_length:
                return data[: self.max_string_length - 3] + "...", 1
            return data, 1
        return data, 1

    def _truncate_to_bytes(self, data: Any, max_bytes: int) -> Any:
        """Truncate data structure to fit within max_bytes."""
        import json
        max_string_length = self.max_string_length // 2
        while max_string_length > 10:
            test_data = self._apply_string_limit(data, max_string_length)
            test_json = json.dumps(test_data)
            if len(test_json.encode("utf-8")) <= max_bytes:
                return test_data
            max_string_length //= 2
        return self._apply_string_limit(data, 10)

    def _apply_string_limit(self, data: Any, max_length: int) -> Any:
        """Apply string length limit to all strings in data."""
        if isinstance(data, list):
            return [self._apply_string_limit(item, max_length) for item in data]
        elif isinstance(data, dict):
            return {k: self._apply_string_limit(v, max_length) for k, v in data.items()}
        elif isinstance(data, str):
            if len(data) > max_length:
                return data[: max_length - 3] + "..."
            return data
        return data


class LineOrientedReducer(ToolOutputReducer):
    """Reducer for line-oriented output (logs, events).

    This reducer:
    - Splits output into lines
    - Limits number of lines
    - Optionally filters by pattern
    - Reports total line count and what was omitted
    """

    def __init__(
        self,
        *,
        max_lines: int = 500,
        max_line_length: int = 500,
        include_header: bool = True,
    ) -> None:
        self.max_lines = max_lines
        self.max_line_length = max_line_length
        self.include_header = include_header

    def reduce(
        self,
        raw_output: str | dict[str, Any],
        *,
        max_bytes: int,
        source_tool: str,
        raw_artifact_id: str | None = None,
    ) -> ToolReducedOutput:
        """Reduce line-oriented output."""
        if isinstance(raw_output, dict):
            text = raw_output.get("text") or raw_output.get("message") or raw_output.get("content")
            if text:
                raw_output = str(text)
            else:
                import json
                raw_output = json.dumps(raw_output, indent=2)

        text = str(raw_output)
        lines = text.splitlines()
        total_lines = len(lines)
        visible_lines = 0

        result_lines = []
        for i, line in enumerate(lines):
            if i >= self.max_lines:
                break
            if len(line) > self.max_line_length:
                line = line[: self.max_line_length - 3] + "..."
            result_lines.append(line)
            visible_lines += 1

        omitted_lines = total_lines - visible_lines
        result_text = "\n".join(result_lines)
        result_bytes = len(result_text.encode("utf-8"))

        if result_bytes > max_bytes:
            limit = int(max_bytes * 0.9)
            result_text = result_text[:limit]
            result_bytes = len(result_text.encode("utf-8"))

        return ToolReducedOutput(
            schema_version=REDUCER_SCHEMA_VERSION,
            source_tool=source_tool,
            raw_artifact_id=raw_artifact_id,
            reduction_policy="line_oriented",
            counts={
                "raw_items": total_lines,
                "visible_items": visible_lines,
                "omitted_items": omitted_lines,
            },
            truncated=result_bytes > max_bytes or omitted_lines > 0,
            redacted=False,
            llm_visible={"text": result_text, "bytes": result_bytes},
            truncation_reason=f"limited to {self.max_lines} lines" if omitted_lines > 0 else None,
        )


class CountPreservingReducer(ToolOutputReducer):
    """Reducer that preserves item counts but truncates content.

    This reducer:
    - Shows item counts without full content
    - Shows first N items in full
    - Shows last N items in full
    - Reports counts for omitted items
    """

    def __init__(
        self,
        *,
        head_items: int = 20,
        tail_items: int = 10,
        max_item_content: int = 500,
    ) -> None:
        self.head_items = head_items
        self.tail_items = tail_items
        self.max_item_content = max_item_content

    def reduce(
        self,
        raw_output: str | dict[str, Any],
        *,
        max_bytes: int,
        source_tool: str,
        raw_artifact_id: str | None = None,
    ) -> ToolReducedOutput:
        """Reduce with head/tail preservation."""
        if isinstance(raw_output, str):
            try:
                import json
                data = json.loads(raw_output)
            except (json.JSONDecodeError, ValueError):
                reducer = LineOrientedReducer(max_lines=self.head_items + self.tail_items)
                return reducer.reduce(
                    raw_output, max_bytes=max_bytes, source_tool=source_tool, raw_artifact_id=raw_artifact_id
                )
        else:
            data = raw_output

        if isinstance(data, list):
            total_items = len(data)
            head = data[: self.head_items]
            tail = data[-self.tail_items :] if len(data) > self.head_items else []

            if len(head) + len(tail) > total_items:
                tail = data[-self.tail_items :]

            head = self._truncate_items(head)
            tail = self._truncate_items(tail)

            omitted_items = max(0, total_items - len(head) - len(tail))

            result = {
                "head": head,
                "tail": tail if tail != head else [],
                "total_count": total_items,
                "omitted_count": omitted_items,
            }

            import json
            result_json = json.dumps(result)
            if len(result_json.encode("utf-8")) > max_bytes:
                result = {"total_count": total_items, "omitted_count": omitted_items}

            return ToolReducedOutput(
                schema_version=REDUCER_SCHEMA_VERSION,
                source_tool=source_tool,
                raw_artifact_id=raw_artifact_id,
                reduction_policy="count_preserving",
                counts={
                    "raw_items": total_items,
                    "visible_items": len(head) + len(tail),
                    "omitted_items": omitted_items,
                },
                truncated=omitted_items > 0,
                redacted=False,
                llm_visible=result,
            )

        reducer = LineOrientedReducer(max_lines=self.head_items + self.tail_items)
        return reducer.reduce(raw_output, max_bytes=max_bytes, source_tool=source_tool, raw_artifact_id=raw_artifact_id)

    def _truncate_items(self, items: list[Any]) -> list[Any]:
        """Truncate content in items."""
        result: list[Any] = []
        for item in items:
            if isinstance(item, str):
                if len(item) > self.max_item_content:
                    result.append(item[: self.max_item_content - 3] + "...")
                else:
                    result.append(item)
            elif isinstance(item, dict):
                result.append(self._truncate_dict(item))
            elif isinstance(item, list):
                result.append(self._truncate_items(item))
            else:
                result.append(item)
        return result

    def _truncate_dict(self, d: dict[str, Any]) -> dict[str, Any]:
        """Truncate values in dict."""
        return {k: self._truncate_items([v])[0] if isinstance(v, (str, list)) else v for k, v in d.items()}


class OmittedFieldReporter:
    """Utility to track and report omitted fields."""

    def __init__(self) -> None:
        self.omitted_fields: list[str] = []
        self.truncated_fields: dict[str, int] = {}
        self.redacted_values: dict[str, int] = {}

    def add_omitted(self, field_path: str) -> None:
        """Record an omitted field."""
        self.omitted_fields.append(field_path)

    def add_truncated(self, field_path: str, original_length: int) -> None:
        """Record a truncated field."""
        self.truncated_fields[field_path] = original_length

    def add_redacted(self, field_path: str) -> None:
        """Record a redacted field."""
        self.redacted_values[field_path] = self.redacted_values.get(field_path, 0) + 1

    def to_dict(self) -> dict[str, Any]:
        """Export tracking state."""
        return {
            "omitted_fields": self.omitted_fields,
            "truncated_fields": self.truncated_fields,
            "redacted_values": self.redacted_values,
            "total_omitted": len(self.omitted_fields),
            "total_truncated": len(self.truncated_fields),
            "total_redacted": sum(self.redacted_values.values()),
        }


def get_default_reducer(reducer_type: str = "auto") -> ToolOutputReducer:
    """Get appropriate reducer based on type.

    Args:
        reducer_type: One of "json", "line", "count", "auto"

    Returns:
        Appropriate reducer instance
    """
    if reducer_type == "json":
        return JsonTreeReducer()
    elif reducer_type == "line":
        return LineOrientedReducer()
    elif reducer_type == "count":
        return CountPreservingReducer()
    else:
        return JsonTreeReducer()


__all__ = [
    "REDUCER_SCHEMA_VERSION",
    "ToolReducedOutput",
    "ToolOutputReducer",
    "JsonTreeReducer",
    "LineOrientedReducer",
    "CountPreservingReducer",
    "OmittedFieldReporter",
    "get_default_reducer",
]
