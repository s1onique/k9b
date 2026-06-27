# Test Exclusions Policy

This document tracks test files that are excluded from sharded test execution due to import errors or other collection failures.

## Excluded Files

_None currently._

## Expected Test Count

When collection works correctly:
- Full collection (no ignore): ~7845 tests
- Sharded collection (with ignore): ~7845 tests
- No exclusions

## Verification

Run the exclusion verification:
```bash
python scripts/verify_test_exclusions.py
```

This script compares:
1. Full pytest collection (with errors) - expected ~7845 lines
2. Sharded collection (ignores broken files) - expected ~7845 nodeids
3. Fails if non-allowlisted files are missing from sharded collection
4. Fails if allowlisted files are no longer broken (stale exclusions)

## History

### 2026-06-27
- `tests/unit/test_property_checks.py`: Removed from exclusions. Hypothesis
  (`hypothesis>=6.9,<7`) is now properly declared in `pyproject.toml` under
  `[project.optional-dependencies] dev`. The file now collects successfully
  with 3 property-based tests. ALLOWLISTED_EXCLUSIONS is now empty.
