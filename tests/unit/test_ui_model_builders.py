"""Tests for ui/model.py builder/helper functions."""

import unittest

from k8s_diag_agent.ui.model import (
    LLMStatsView,
    RunStatsView,
    _build_llm_stats_view,
    _build_optional_llm_stats_view,
    _build_run_stats_view,
    _coerce_int,
    _coerce_optional_bool,
    _coerce_optional_int,
    _coerce_optional_str,
    _coerce_sequence,
    _coerce_str,
    _coerce_str_tuple,
    _serialize_map,
    _stringify,
    _value_from_mapping,
)


class CoerceStrTests(unittest.TestCase):
    """Tests for _coerce_str() function."""

    def test_none_returns_dash(self) -> None:
        """None values should return '-'."""
        result = _coerce_str(None)
        self.assertEqual(result, "-")

    def test_string_passthrough(self) -> None:
        """String values should be returned unchanged."""
        result = _coerce_str("hello")
        self.assertEqual(result, "hello")

    def test_empty_string(self) -> None:
        """Empty strings should be returned unchanged."""
        result = _coerce_str("")
        self.assertEqual(result, "")

    def test_int_converted(self) -> None:
        """Integer values should be converted to string."""
        result = _coerce_str(42)
        self.assertEqual(result, "42")

    def test_float_converted(self) -> None:
        """Float values should be converted to string."""
        result = _coerce_str(3.14)
        self.assertEqual(result, "3.14")

    def test_bool_true_converted(self) -> None:
        """True boolean should be converted to string."""
        result = _coerce_str(True)
        self.assertEqual(result, "True")

    def test_bool_false_converted(self) -> None:
        """False boolean should be converted to string."""
        result = _coerce_str(False)
        self.assertEqual(result, "False")

    def test_list_converted(self) -> None:
        """List values should be converted to string representation."""
        result = _coerce_str([1, 2, 3])
        self.assertEqual(result, "[1, 2, 3]")

    def test_dict_converted(self) -> None:
        """Dict values should be converted to string representation."""
        result = _coerce_str({"key": "value"})
        self.assertEqual(result, "{'key': 'value'}")


class CoerceOptionalStrTests(unittest.TestCase):
    """Tests for _coerce_optional_str() function."""

    def test_none_returns_none(self) -> None:
        """None values should return None."""
        result = _coerce_optional_str(None)
        self.assertIsNone(result)

    def test_string_passthrough(self) -> None:
        """String values should be returned unchanged."""
        result = _coerce_optional_str("hello")
        self.assertEqual(result, "hello")

    def test_empty_string(self) -> None:
        """Empty strings should be returned unchanged."""
        result = _coerce_optional_str("")
        self.assertEqual(result, "")

    def test_int_converted(self) -> None:
        """Integer values should be converted to string."""
        result = _coerce_optional_str(42)
        self.assertEqual(result, "42")


class CoerceStrTupleTests(unittest.TestCase):
    """Tests for _coerce_str_tuple() function."""

    def test_none_returns_empty_tuple(self) -> None:
        """None should return empty tuple."""
        result = _coerce_str_tuple(None)
        self.assertEqual(result, ())

    def test_list_of_strings(self) -> None:
        """List of strings should be converted to tuple of strings."""
        result = _coerce_str_tuple(["a", "b", "c"])
        self.assertEqual(result, ("a", "b", "c"))

    def test_list_of_mixed_types(self) -> None:
        """List with mixed types should convert each to string."""
        result = _coerce_str_tuple(["a", 1, 2.5, True])
        self.assertEqual(result, ("a", "1", "2.5", "True"))

    def test_single_string_wrapped(self) -> None:
        """Single non-sequence value should be wrapped in tuple."""
        result = _coerce_str_tuple("single")
        self.assertEqual(result, ("single",))

    def test_single_int_wrapped(self) -> None:
        """Single integer should be converted and wrapped in tuple."""
        result = _coerce_str_tuple(42)
        self.assertEqual(result, ("42",))

    def test_empty_list_returns_empty_tuple(self) -> None:
        """Empty list should return empty tuple."""
        result = _coerce_str_tuple([])
        self.assertEqual(result, ())

    def test_bytes_not_treated_as_sequence(self) -> None:
        """Bytes should be converted as single value, not as sequence."""
        result = _coerce_str_tuple(b"test")
        self.assertEqual(result, ("b'test'",))


class CoerceIntTests(unittest.TestCase):
    """Tests for _coerce_int() function."""

    def test_none_returns_zero(self) -> None:
        """None should return 0."""
        result = _coerce_int(None)
        self.assertEqual(result, 0)

    def test_integer_passthrough(self) -> None:
        """Integer values should be returned unchanged."""
        result = _coerce_int(42)
        self.assertEqual(result, 42)

    def test_negative_integer(self) -> None:
        """Negative integers should be returned unchanged."""
        result = _coerce_int(-10)
        self.assertEqual(result, -10)

    def test_zero(self) -> None:
        """Zero should return 0."""
        result = _coerce_int(0)
        self.assertEqual(result, 0)

    def test_string_integer(self) -> None:
        """String integer should be converted."""
        result = _coerce_int("42")
        self.assertEqual(result, 42)

    def test_string_negative_integer(self) -> None:
        """String negative integer should be converted."""
        result = _coerce_int("-10")
        self.assertEqual(result, -10)

    def test_string_zero(self) -> None:
        """String zero should be converted."""
        result = _coerce_int("0")
        self.assertEqual(result, 0)

    def test_invalid_string_returns_zero(self) -> None:
        """Invalid string should return 0."""
        result = _coerce_int("not a number")
        self.assertEqual(result, 0)

    def test_float_truncated(self) -> None:
        """Float should be truncated to int."""
        result = _coerce_int(3.9)
        self.assertEqual(result, 3)

    def test_string_float_returns_zero(self) -> None:
        """String float cannot be directly converted - returns 0 (int() raises ValueError)."""
        # Python's int() raises ValueError for "3.9", so the function catches it and returns 0
        result = _coerce_int("3.9")
        self.assertEqual(result, 0)

    def test_bool_true_returns_one(self) -> None:
        """True boolean should return 1."""
        result = _coerce_int(True)
        self.assertEqual(result, 1)

    def test_bool_false_returns_zero(self) -> None:
        """False boolean should return 0."""
        result = _coerce_int(False)
        self.assertEqual(result, 0)

    def test_float_object_with_truediv(self) -> None:
        """Numeric objects should be converted."""
        result = _coerce_int(42.0)
        self.assertEqual(result, 42)

    def test_empty_string_returns_zero(self) -> None:
        """Empty string should return 0."""
        result = _coerce_int("")
        self.assertEqual(result, 0)


class CoerceOptionalIntTests(unittest.TestCase):
    """Tests for _coerce_optional_int() function."""

    def test_none_returns_none(self) -> None:
        """None should return None."""
        result = _coerce_optional_int(None)
        self.assertIsNone(result)

    def test_integer_passthrough(self) -> None:
        """Integer values should be returned unchanged."""
        result = _coerce_optional_int(42)
        self.assertEqual(result, 42)

    def test_negative_integer(self) -> None:
        """Negative integers should be returned unchanged."""
        result = _coerce_optional_int(-10)
        self.assertEqual(result, -10)

    def test_zero(self) -> None:
        """Zero should return 0."""
        result = _coerce_optional_int(0)
        self.assertEqual(result, 0)

    def test_string_integer(self) -> None:
        """String integer should be converted."""
        result = _coerce_optional_int("42")
        self.assertEqual(result, 42)

    def test_string_negative_integer(self) -> None:
        """String negative integer should be converted."""
        result = _coerce_optional_int("-10")
        self.assertEqual(result, -10)

    def test_string_zero(self) -> None:
        """String zero should be converted."""
        result = _coerce_optional_int("0")
        self.assertEqual(result, 0)

    def test_invalid_string_returns_none(self) -> None:
        """Invalid string should return None (not 0)."""
        result = _coerce_optional_int("not a number")
        self.assertIsNone(result)

    def test_empty_string_returns_none(self) -> None:
        """Empty string should return None (not 0)."""
        result = _coerce_optional_int("")
        self.assertIsNone(result)

    def test_float_truncated(self) -> None:
        """Float should be truncated to int."""
        result = _coerce_optional_int(3.9)
        self.assertEqual(result, 3)

    def test_string_float_returns_none(self) -> None:
        """String float cannot be directly converted - returns None (int() raises ValueError)."""
        # Python's int() raises ValueError for "3.9", so the function catches it and returns None
        result = _coerce_optional_int("3.9")
        self.assertIsNone(result)

    def test_bool_true_returns_one(self) -> None:
        """True boolean should return 1."""
        result = _coerce_optional_int(True)
        self.assertEqual(result, 1)

    def test_bool_false_returns_zero(self) -> None:
        """False boolean should return 0."""
        result = _coerce_optional_int(False)
        self.assertEqual(result, 0)


class CoerceOptionalBoolTests(unittest.TestCase):
    """Tests for _coerce_optional_bool() function."""

    def test_none_returns_none(self) -> None:
        """None should return None."""
        result = _coerce_optional_bool(None)
        self.assertIsNone(result)

    def test_true_passthrough(self) -> None:
        """True boolean should return True."""
        result = _coerce_optional_bool(True)
        self.assertEqual(result, True)

    def test_false_passthrough(self) -> None:
        """False boolean should return False."""
        result = _coerce_optional_bool(False)
        self.assertEqual(result, False)

    def test_string_true_lowercase(self) -> None:
        """String 'true' should return True."""
        result = _coerce_optional_bool("true")
        self.assertEqual(result, True)

    def test_string_true_uppercase(self) -> None:
        """String 'TRUE' should return True."""
        result = _coerce_optional_bool("TRUE")
        self.assertEqual(result, True)

    def test_string_one(self) -> None:
        """String '1' should return True."""
        result = _coerce_optional_bool("1")
        self.assertEqual(result, True)

    def test_string_yes(self) -> None:
        """String 'yes' should return True."""
        result = _coerce_optional_bool("yes")
        self.assertEqual(result, True)

    def test_string_on(self) -> None:
        """String 'on' should return True."""
        result = _coerce_optional_bool("on")
        self.assertEqual(result, True)

    def test_string_false_lowercase(self) -> None:
        """String 'false' should return False."""
        result = _coerce_optional_bool("false")
        self.assertEqual(result, False)

    def test_string_zero(self) -> None:
        """String '0' should return False."""
        result = _coerce_optional_bool("0")
        self.assertEqual(result, False)

    def test_string_no(self) -> None:
        """String 'no' should return False."""
        result = _coerce_optional_bool("no")
        self.assertEqual(result, False)

    def test_string_off(self) -> None:
        """String 'off' should return False."""
        result = _coerce_optional_bool("off")
        self.assertEqual(result, False)

    def test_string_invalid_returns_none(self) -> None:
        """Invalid string should return None."""
        result = _coerce_optional_bool("unknown")
        self.assertIsNone(result)

    def test_string_with_whitespace(self) -> None:
        """String with whitespace should be trimmed."""
        result = _coerce_optional_bool("  true  ")
        self.assertEqual(result, True)

    def test_int_one_returns_true(self) -> None:
        """Integer 1 should return True."""
        result = _coerce_optional_bool(1)
        self.assertEqual(result, True)

    def test_int_zero_returns_false(self) -> None:
        """Integer 0 should return False."""
        result = _coerce_optional_bool(0)
        self.assertEqual(result, False)


class CoerceSequenceTests(unittest.TestCase):
    """Tests for _coerce_sequence() function."""

    def test_none_returns_empty_tuple(self) -> None:
        """None should return empty tuple."""
        result = _coerce_sequence(None)
        self.assertEqual(result, ())

    def test_list_of_strings(self) -> None:
        """List of strings should be converted to tuple of strings."""
        result = _coerce_sequence(["a", "b", "c"])
        self.assertEqual(result, ("a", "b", "c"))

    def test_list_of_mixed_types(self) -> None:
        """List with mixed types should convert each to string."""
        result = _coerce_sequence(["a", 1, 2.5, True])
        self.assertEqual(result, ("a", "1", "2.5", "True"))

    def test_single_string_wrapped(self) -> None:
        """Single non-sequence value should be wrapped in tuple."""
        result = _coerce_sequence("single")
        self.assertEqual(result, ("single",))

    def test_single_int_wrapped(self) -> None:
        """Single integer should be converted and wrapped in tuple."""
        result = _coerce_sequence(42)
        self.assertEqual(result, ("42",))

    def test_empty_list_returns_empty_tuple(self) -> None:
        """Empty list should return empty tuple."""
        result = _coerce_sequence([])
        self.assertEqual(result, ())

    def test_bytes_not_treated_as_sequence(self) -> None:
        """Bytes should be converted as single value, not as sequence."""
        result = _coerce_sequence(b"test")
        self.assertEqual(result, ("b'test'",))


class SerializeMapTests(unittest.TestCase):
    """Tests for _serialize_map() function."""

    def test_none_returns_empty_tuple(self) -> None:
        """None should return empty tuple."""
        result = _serialize_map(None)
        self.assertEqual(result, ())

    def test_empty_dict_returns_empty_tuple(self) -> None:
        """Empty dict should return empty tuple."""
        result = _serialize_map({})
        self.assertEqual(result, ())

    def test_simple_dict(self) -> None:
        """Simple dict should be serialized."""
        result = _serialize_map({"key": "value"})
        self.assertEqual(result, (("key", "value"),))

    def test_numeric_keys_and_values(self) -> None:
        """Numeric keys and values should be converted to strings."""
        result = _serialize_map({1: 2, 3: 4})
        self.assertEqual(result, (("1", "2"), ("3", "4")))

    def test_mixed_types(self) -> None:
        """Mixed types should be stringified."""
        result = _serialize_map({"str_key": 42, "int_key": "str_val"})
        self.assertEqual(result, (("str_key", "42"), ("int_key", "str_val")))

    def test_list_value_json_serialized(self) -> None:
        """List values should be JSON serialized."""
        result = _serialize_map({"key": [1, 2, 3]})
        self.assertEqual(result, (("key", "[1, 2, 3]"),))

    def test_non_mapping_returns_empty(self) -> None:
        """Non-mapping values should return empty tuple."""
        result = _serialize_map("not a dict")
        self.assertEqual(result, ())

    def test_list_returns_empty(self) -> None:
        """List should return empty tuple (not a mapping)."""
        result = _serialize_map([{"key": "value"}])
        self.assertEqual(result, ())


class StringifyTests(unittest.TestCase):
    """Tests for _stringify() function."""

    def test_none_returns_dash(self) -> None:
        """None should return '-'."""
        result = _stringify(None)
        self.assertEqual(result, "-")

    def test_string_passthrough(self) -> None:
        """String values should be returned unchanged."""
        result = _stringify("hello")
        self.assertEqual(result, "hello")

    def test_empty_string(self) -> None:
        """Empty strings should be returned unchanged."""
        result = _stringify("")
        self.assertEqual(result, "")

    def test_int_converted(self) -> None:
        """Integer should be converted to string."""
        result = _stringify(42)
        self.assertEqual(result, "42")

    def test_float_converted(self) -> None:
        """Float should be converted to string."""
        result = _stringify(3.14)
        self.assertEqual(result, "3.14")

    def test_bool_converted(self) -> None:
        """Boolean should be converted to string (JSON style lowercase)."""
        # json.dumps returns lowercase "true"/"false"
        result = _stringify(True)
        self.assertEqual(result, "true")

    def test_list_json_serialized(self) -> None:
        """List should be JSON serialized."""
        result = _stringify([1, 2, 3])
        self.assertEqual(result, "[1, 2, 3]")

    def test_dict_json_serialized(self) -> None:
        """Dict should be JSON serialized."""
        result = _stringify({"key": "value"})
        self.assertEqual(result, '{"key": "value"}')

    def test_complex_object_fallback_to_str(self) -> None:
        """Non-JSON-serializable objects should fall back to str()."""
        class NonSerializable:
            def __str__(self) -> str:
                return "custom_str"

        result = _stringify(NonSerializable())
        self.assertEqual(result, "custom_str")


class ValueFromMappingTests(unittest.TestCase):
    """Tests for _value_from_mapping() function."""

    def test_none_returns_none(self) -> None:
        """None should return None."""
        result = _value_from_mapping(None, "key")
        self.assertIsNone(result)

    def test_dict_returns_value(self) -> None:
        """Dict should return the value for the key."""
        result = _value_from_mapping({"key": "value"}, "key")
        self.assertEqual(result, "value")

    def test_dict_missing_key_returns_none(self) -> None:
        """Dict with missing key should return None."""
        result = _value_from_mapping({"other_key": "value"}, "key")
        self.assertIsNone(result)

    def test_non_mapping_returns_none(self) -> None:
        """Non-mapping values should return None."""
        result = _value_from_mapping("not a dict", "key")
        self.assertIsNone(result)

    def test_list_returns_none(self) -> None:
        """List should return None (not a mapping)."""
        result = _value_from_mapping([{"key": "value"}], "key")
        self.assertIsNone(result)


class BuildRunStatsViewTests(unittest.TestCase):
    """Tests for _build_run_stats_view() function."""

    def test_none_returns_defaults(self) -> None:
        """None should return RunStatsView with default values."""
        result = _build_run_stats_view(None)
        self.assertIsInstance(result, RunStatsView)
        self.assertIsNone(result.last_run_duration_seconds)
        self.assertEqual(result.total_runs, 0)
        self.assertIsNone(result.p50_run_duration_seconds)
        self.assertIsNone(result.p95_run_duration_seconds)
        self.assertIsNone(result.p99_run_duration_seconds)

    def test_non_mapping_returns_defaults(self) -> None:
        """Non-mapping values should return defaults."""
        result = _build_run_stats_view("not a dict")
        self.assertIsInstance(result, RunStatsView)
        self.assertEqual(result.total_runs, 0)

    def test_full_data(self) -> None:
        """Full data should populate all fields."""
        raw = {
            "last_run_duration_seconds": 42,
            "total_runs": 10,
            "p50_run_duration_seconds": 30,
            "p95_run_duration_seconds": 40,
            "p99_run_duration_seconds": 50,
        }
        result = _build_run_stats_view(raw)
        self.assertEqual(result.last_run_duration_seconds, 42)
        self.assertEqual(result.total_runs, 10)
        self.assertEqual(result.p50_run_duration_seconds, 30)
        self.assertEqual(result.p95_run_duration_seconds, 40)
        self.assertEqual(result.p99_run_duration_seconds, 50)

    def test_partial_data(self) -> None:
        """Partial data should populate available fields with defaults for missing."""
        raw = {
            "last_run_duration_seconds": 42,
            "total_runs": 10,
        }
        result = _build_run_stats_view(raw)
        self.assertEqual(result.last_run_duration_seconds, 42)
        self.assertEqual(result.total_runs, 10)
        self.assertIsNone(result.p50_run_duration_seconds)
        self.assertIsNone(result.p95_run_duration_seconds)
        self.assertIsNone(result.p99_run_duration_seconds)

    def test_string_int_coerced(self) -> None:
        """String integers should be coerced to int."""
        raw = {
            "last_run_duration_seconds": "42",
            "total_runs": "10",
        }
        result = _build_run_stats_view(raw)
        self.assertEqual(result.last_run_duration_seconds, 42)
        self.assertEqual(result.total_runs, 10)

    def test_invalid_string_int_coerced_to_zero_or_none(self) -> None:
        """Invalid string integers should be coerced appropriately."""
        raw = {
            "last_run_duration_seconds": "not a number",
            "total_runs": "also invalid",
        }
        result = _build_run_stats_view(raw)
        # total_runs uses _coerce_int which returns 0 for invalid strings
        self.assertEqual(result.total_runs, 0)
        # last_run_duration_seconds uses _coerce_optional_int which returns None
        self.assertIsNone(result.last_run_duration_seconds)


class BuildLLMStatsViewTests(unittest.TestCase):
    """Tests for _build_llm_stats_view() function."""

    def test_none_returns_defaults(self) -> None:
        """None should return LLMStatsView with default values."""
        result = _build_llm_stats_view(None)
        self.assertIsInstance(result, LLMStatsView)
        self.assertEqual(result.total_calls, 0)
        self.assertEqual(result.successful_calls, 0)
        self.assertEqual(result.failed_calls, 0)
        self.assertIsNone(result.last_call_timestamp)
        self.assertIsNone(result.p50_latency_ms)
        self.assertIsNone(result.p95_latency_ms)
        self.assertIsNone(result.p99_latency_ms)
        self.assertEqual(result.provider_breakdown, ())
        self.assertEqual(result.scope, "current_run")

    def test_non_mapping_returns_defaults(self) -> None:
        """Non-mapping values should return defaults."""
        result = _build_llm_stats_view("not a dict")
        self.assertEqual(result.total_calls, 0)
        self.assertEqual(result.provider_breakdown, ())

    def test_full_data(self) -> None:
        """Full data should populate all fields."""
        raw = {
            "totalCalls": 100,
            "successfulCalls": 95,
            "failedCalls": 5,
            "lastCallTimestamp": "2026-01-01T00:00:00Z",
            "p50LatencyMs": 120,
            "p95LatencyMs": 220,
            "p99LatencyMs": 300,
            "providerBreakdown": [
                {"provider": "provider-a", "calls": 80, "failedCalls": 3},
                {"provider": "provider-b", "calls": 20, "failedCalls": 2},
            ],
            "scope": "current_run",
        }
        result = _build_llm_stats_view(raw)
        self.assertEqual(result.total_calls, 100)
        self.assertEqual(result.successful_calls, 95)
        self.assertEqual(result.failed_calls, 5)
        self.assertEqual(result.last_call_timestamp, "2026-01-01T00:00:00Z")
        self.assertEqual(result.p50_latency_ms, 120)
        self.assertEqual(result.p95_latency_ms, 220)
        self.assertEqual(result.p99_latency_ms, 300)
        self.assertEqual(len(result.provider_breakdown), 2)
        self.assertEqual(result.provider_breakdown[0].provider, "provider-a")
        self.assertEqual(result.provider_breakdown[0].calls, 80)
        self.assertEqual(result.provider_breakdown[0].failed_calls, 3)
        self.assertEqual(result.provider_breakdown[1].provider, "provider-b")
        self.assertEqual(result.scope, "current_run")

    def test_provider_breakdown_empty(self) -> None:
        """Empty provider breakdown should return empty tuple."""
        raw = {
            "totalCalls": 10,
            "successfulCalls": 10,
            "failedCalls": 0,
            "providerBreakdown": [],
        }
        result = _build_llm_stats_view(raw)
        self.assertEqual(result.provider_breakdown, ())

    def test_provider_breakdown_none(self) -> None:
        """None provider breakdown should return empty tuple."""
        raw = {
            "totalCalls": 10,
            "successfulCalls": 10,
            "failedCalls": 0,
            "providerBreakdown": None,
        }
        result = _build_llm_stats_view(raw)
        self.assertEqual(result.provider_breakdown, ())

    def test_provider_breakdown_invalid_entries_skipped(self) -> None:
        """Non-mapping entries in provider breakdown should be skipped."""
        raw = {
            "totalCalls": 10,
            "successfulCalls": 10,
            "failedCalls": 0,
            "providerBreakdown": [
                {"provider": "valid", "calls": 5, "failedCalls": 1},
                "invalid entry",
                42,
                None,
                {"provider": "also valid", "calls": 5, "failedCalls": 2},
            ],
        }
        result = _build_llm_stats_view(raw)
        self.assertEqual(len(result.provider_breakdown), 2)
        self.assertEqual(result.provider_breakdown[0].provider, "valid")
        self.assertEqual(result.provider_breakdown[1].provider, "also valid")

    def test_missing_scope_defaults_to_current_run(self) -> None:
        """Missing scope should default to 'current_run'."""
        raw = {
            "totalCalls": 10,
            "successfulCalls": 10,
            "failedCalls": 0,
        }
        result = _build_llm_stats_view(raw)
        self.assertEqual(result.scope, "current_run")

    def test_explicit_scope_preserved(self) -> None:
        """Explicit scope value should be preserved."""
        raw = {
            "totalCalls": 10,
            "successfulCalls": 10,
            "failedCalls": 0,
            "scope": "retained_history",
        }
        result = _build_llm_stats_view(raw)
        self.assertEqual(result.scope, "retained_history")

    def test_partial_latency_fields(self) -> None:
        """Partial latency data should only populate available fields."""
        raw = {
            "totalCalls": 10,
            "successfulCalls": 10,
            "failedCalls": 0,
            "p50LatencyMs": 100,
        }
        result = _build_llm_stats_view(raw)
        self.assertEqual(result.p50_latency_ms, 100)
        self.assertIsNone(result.p95_latency_ms)
        self.assertIsNone(result.p99_latency_ms)

    def test_string_int_fields_coerced(self) -> None:
        """String integer fields should be coerced."""
        raw = {
            "totalCalls": "100",
            "successfulCalls": "95",
            "failedCalls": "5",
            "p50LatencyMs": "120",
        }
        result = _build_llm_stats_view(raw)
        self.assertEqual(result.total_calls, 100)
        self.assertEqual(result.successful_calls, 95)
        self.assertEqual(result.failed_calls, 5)
        self.assertEqual(result.p50_latency_ms, 120)


class BuildOptionalLLMStatsViewTests(unittest.TestCase):
    """Tests for _build_optional_llm_stats_view() function."""

    def test_none_returns_none(self) -> None:
        """None should return None (not a default LLMStatsView)."""
        result = _build_optional_llm_stats_view(None)
        self.assertIsNone(result)

    def test_non_mapping_returns_none(self) -> None:
        """Non-mapping values should return None."""
        result = _build_optional_llm_stats_view("not a dict")
        self.assertIsNone(result)

    def test_mapping_returns_llm_stats_view(self) -> None:
        """Mapping should return LLMStatsView."""
        raw = {
            "totalCalls": 10,
            "successfulCalls": 10,
            "failedCalls": 0,
        }
        result = _build_optional_llm_stats_view(raw)
        self.assertIsInstance(result, LLMStatsView)
        view: LLMStatsView = result  # type: ignore[assignment]
        self.assertEqual(view.total_calls, 10)


if __name__ == "__main__":
    unittest.main()
