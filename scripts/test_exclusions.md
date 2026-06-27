# Test Exclusions Policy

This document tracks test files that are excluded from sharded test execution due to import errors or other collection failures.

## Single Source of Truth

The exclusion policy is enforced by the `test_collection.py` module which provides:
- `ALLOWED_COLLECTION_EXCLUSIONS`: The canonical list of excluded files
- `verify_no_hard_coded_ignores()`: Regression guard against hard-coded `--ignore` literals
- `collect_test_nodeids()`: Shared collection helper used by both `shard_tests.py` and `verify_test_exclusions.py`

## Excluded Files

_None currently._ All test files collect successfully.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    test_collection.py                               │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  ALLOWED_COLLECTION_EXCLUSIONS: set[str]  (single source)  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  collect_test_nodeids()  (shared collection helper)        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  verify_no_hard_coded_ignores()  (regression guard)        │   │
│  └─────────────────────────────────────────────────────────────┘   │
└───────────────────────────┬───────────────────────────────────────┘
                            │
          ┌─────────────────┴─────────────────┐
          │                                   │
          ▼                                   ▼
┌─────────────────────┐           ┌─────────────────────────┐
│   shard_tests.py    │           │ verify_test_exclusions.py│
│   (for execution)   │           │   (for verification)    │
└─────────────────────┘           └─────────────────────────┘
```

## Collection Policy

1. **No raw `--ignore=tests/...` literals** are allowed in collection code
2. Any file-specific exclusions must be added to `ALLOWED_COLLECTION_EXCLUSIONS`
3. The exclusion must be documented in this file
4. The verifier checks that allowlisted files actually have import errors

## Expected Test Count

When collection works correctly:
- Full collection (no ignore): ~7845 tests
- Sharded collection (same method): ~7845 tests
- No exclusions

## Verification

Run the exclusion verification:
```bash
python scripts/verify_test_exclusions.py
```

This script:
1. Runs the regression guard (checks for hard-coded `--ignore=tests/...`)
2. Compares full pytest collection with sharded collection
3. Verifies allowlisted files actually have import errors
4. Fails if non-allowlisted files are missing from sharded collection
5. Fails if allowlisted files are no longer broken (stale exclusions)

## Regression Guard

The regression guard catches hard-coded `--ignore=tests/...` patterns in:
- `scripts/shard_tests.py`
- `scripts/verify_test_exclusions.py`
- `scripts/test_collection.py`

Adding a raw `--ignore` will cause:
1. `verify_test_exclusions.py` to fail immediately
2. Unit tests in `TestRegressionGuard` to fail

To add an exclusion properly:
1. Add the file to `ALLOWED_COLLECTION_EXCLUSIONS` in `test_collection.py`
2. Document it in this file
3. Run `python scripts/verify_test_exclusions.py` to verify

## History

### 2026-06-27
- Created `test_collection.py` as single source of truth for collection
- Moved `ALLOWLISTED_EXCLUSIONS` to `ALLOWED_COLLECTION_EXCLUSIONS`
- Added `verify_no_hard_coded_ignores()` regression guard
- Added `TestRegressionGuard` unit tests
- `shard_tests.py` and `verify_test_exclusions.py` now use shared collection helper

### 2026-06-27 (earlier)
- `tests/unit/test_property_checks.py`: Removed from exclusions. Hypothesis
  (`hypothesis>=6.9,<7`) is now properly declared in `pyproject.toml` under
  `[project.optional-dependencies] dev`. The file now collects successfully
  with 3 property-based tests.
