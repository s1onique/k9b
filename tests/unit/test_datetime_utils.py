"""Regression tests for datetime normalization to prevent offset-naive vs offset-aware comparison failures.

These tests verify that:
1. parse_iso_to_utc always returns timezone-aware UTC datetimes
2. All datetime comparisons in the fixed code paths are safe
3. Mixed naive/aware datetime sources are normalized before comparison

See: docs/doctrine/30-output-contracts.md for comparison safety contract.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

# Import the centralized datetime utilities
from k8s_diag_agent.datetime_utils import (
    ensure_utc,
    fromtimestamp_utc,
    now_utc,
    parse_iso_or_now,
    parse_iso_to_utc,
)


class TestParseIsoToUtc(unittest.TestCase):
    """Tests for parse_iso_to_utc function."""

    def test_parses_utc_offset(self) -> None:
        """Parse timestamp with explicit +00:00 offset."""
        result = parse_iso_to_utc("2024-01-15T10:30:00+00:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.tzinfo, UTC)  # type: ignore[union-attr]

    def test_parses_negative_offset(self) -> None:
        """Parse timestamp with negative timezone offset."""
        result = parse_iso_to_utc("2024-01-15T10:30:00-05:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.tzinfo, UTC)  # type: ignore[union-attr]
        # -5 hours from UTC
        self.assertEqual(result.hour, 15)  # type: ignore[union-attr]

    def test_parses_z_suffix(self) -> None:
        """Parse timestamp with Z suffix (ISO 8601 legacy)."""
        result = parse_iso_to_utc("2024-01-15T10:30:00Z")
        self.assertIsNotNone(result)
        self.assertEqual(result.tzinfo, UTC)  # type: ignore[union-attr]

    def test_parses_naive_timestamp(self) -> None:
        """Parse naive timestamp (no timezone) - assumes UTC."""
        result = parse_iso_to_utc("2024-01-15T10:30:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.tzinfo, UTC)  # type: ignore[union-attr]

    def test_parses_microseconds(self) -> None:
        """Parse timestamp with microseconds."""
        result = parse_iso_to_utc("2024-01-15T10:30:00.123456+00:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.tzinfo, UTC)  # type: ignore[union-attr]

    def test_returns_none_for_none(self) -> None:
        """Returns None for None input."""
        result = parse_iso_to_utc(None)
        self.assertIsNone(result)

    def test_returns_none_for_empty_string(self) -> None:
        """Returns None for empty string."""
        result = parse_iso_to_utc("")
        self.assertIsNone(result)

    def test_returns_none_for_invalid_format(self) -> None:
        """Returns None for invalid timestamp format."""
        result = parse_iso_to_utc("not-a-timestamp")
        self.assertIsNone(result)

    def test_returns_none_for_non_string(self) -> None:
        """Returns None for non-string input."""
        result = parse_iso_to_utc(12345)
        self.assertIsNone(result)

    def test_parses_offset_without_colon(self) -> None:
        """Parse timestamp with timezone offset without colon (e.g., +0000)."""
        result = parse_iso_to_utc("2024-01-15T10:30:00+0000")
        self.assertIsNotNone(result)
        self.assertEqual(result.tzinfo, UTC)  # type: ignore[union-attr]

    def test_parses_negative_offset_without_colon(self) -> None:
        """Parse timestamp with negative timezone offset without colon (e.g., -0500)."""
        result = parse_iso_to_utc("2024-01-15T10:30:00-0500")
        self.assertIsNotNone(result)
        self.assertEqual(result.tzinfo, UTC)  # type: ignore[union-attr]
        # -5 hours from UTC
        self.assertEqual(result.hour, 15)  # type: ignore[union-attr]


class TestEnsureUtc(unittest.TestCase):
    """Tests for ensure_utc function."""

    def test_preserves_already_utc(self) -> None:
        """Preserves UTC-aware datetime."""
        aware_dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        result = ensure_utc(aware_dt)
        self.assertEqual(result.tzinfo, UTC)
        self.assertEqual(result, aware_dt)

    def test_converts_other_timezone_to_utc(self) -> None:
        """Converts aware datetime from other timezone to UTC."""
        from datetime import timedelta, timezone
        est = timezone(timedelta(hours=-5))
        est_dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=est)
        result = ensure_utc(est_dt)
        self.assertEqual(result.tzinfo, UTC)
        # 10:30 EST = 15:30 UTC
        self.assertEqual(result.hour, 15)

    def test_attaches_utc_to_naive(self) -> None:
        """Attaches UTC to naive datetime (assumes it's UTC)."""
        naive_dt = datetime(2024, 1, 15, 10, 30, 0)
        result = ensure_utc(naive_dt)
        self.assertEqual(result.tzinfo, UTC)
        self.assertEqual(result.year, naive_dt.year)
        self.assertEqual(result.month, naive_dt.month)
        self.assertEqual(result.day, naive_dt.day)


class TestNowUtc(unittest.TestCase):
    """Tests for now_utc function."""

    def test_returns_utc_aware(self) -> None:
        """Returns timezone-aware UTC datetime."""
        result = now_utc()
        self.assertEqual(result.tzinfo, UTC)


class TestFromtimestampUtc(unittest.TestCase):
    """Tests for fromtimestamp_utc function."""

    def test_returns_utc_aware(self) -> None:
        """Returns timezone-aware UTC datetime from timestamp."""
        # POSIX timestamp for 2024-01-15 10:30:00 UTC
        timestamp = 1705315800
        result = fromtimestamp_utc(timestamp)
        self.assertEqual(result.tzinfo, UTC)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 15)


class TestParseIsoOrNow(unittest.TestCase):
    """Tests for parse_iso_or_now function."""

    def test_parses_valid_timestamp(self) -> None:
        """Returns parsed UTC-aware datetime for valid input."""
        result = parse_iso_or_now("2024-01-15T10:30:00+00:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.tzinfo, UTC)

    def test_returns_now_for_invalid(self) -> None:
        """Returns current UTC time for invalid input."""
        before = now_utc()
        result = parse_iso_or_now("invalid")
        after = now_utc()
        self.assertEqual(result.tzinfo, UTC)
        self.assertGreaterEqual(result, before)
        self.assertLessEqual(result, after)


class TestSafeComparisons(unittest.TestCase):
    """Regression tests to ensure datetime comparisons don't fail with mixed naive/aware."""

    def test_parsed_vs_parsed_comparison(self) -> None:
        """Two parsed datetimes can be safely compared."""
        dt1 = parse_iso_to_utc("2024-01-15T10:30:00+00:00")
        dt2 = parse_iso_to_utc("2024-01-15T11:00:00Z")
        self.assertIsNotNone(dt1)
        self.assertIsNotNone(dt2)
        self.assertTrue(dt1 < dt2)  # type: ignore[operator]

    def test_parsed_vs_now_comparison(self) -> None:
        """Parsed datetime can be safely compared with now_utc()."""
        dt = parse_iso_to_utc("2024-01-15T10:30:00+00:00")
        now = now_utc()
        self.assertIsNotNone(dt)
        # Historical timestamp should be less than now
        self.assertTrue(dt < now)  # type: ignore[operator]

    def test_parsed_naive_vs_aware_comparison(self) -> None:
        """Naive parsed datetime can be safely compared with aware datetime."""
        # This would fail before the fix with:
        # TypeError: can't compare offset-naive and offset-aware datetimes
        naive_dt = parse_iso_to_utc("2024-01-15T10:30:00")  # No timezone = naive
        aware_dt = parse_iso_to_utc("2024-01-15T11:00:00+00:00")
        self.assertIsNotNone(naive_dt)
        self.assertIsNotNone(aware_dt)
        # Both should now be UTC-aware
        self.assertEqual(naive_dt.tzinfo, UTC)  # type: ignore[union-attr]
        self.assertEqual(aware_dt.tzinfo, UTC)  # type: ignore[union-attr]
        # Safe to compare
        self.assertTrue(naive_dt < aware_dt)  # type: ignore[operator]


class TestFromJsonRoundTrip(unittest.TestCase):
    """Tests simulating the artifact from_dict JSON round-trip scenario."""

    def test_fromisoformat_returns_naive(self) -> None:
        """Demonstrate that datetime.fromisoformat returns naive for naive strings."""
        # This is the root cause of the bug - simulating it here
        naive_string = "2024-01-15T10:30:00"  # No timezone
        dt = datetime.fromisoformat(naive_string)
        # BEFORE FIX: dt.tzinfo would be None (naive)
        # AFTER FIX: parse_iso_to_utc normalizes to UTC-aware
        self.assertIsNone(dt.tzinfo)  # This is the bug - naive datetime

    def test_parse_iso_to_utc_normalizes_naive(self) -> None:
        """parse_iso_to_utc normalizes naive strings to UTC-aware."""
        naive_string = "2024-01-15T10:30:00"
        dt = parse_iso_to_utc(naive_string)
        # AFTER FIX: dt.tzinfo is UTC
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, UTC)  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
