# Test Exclusions Policy

This document tracks test files that are excluded from sharded test execution due to import errors or other collection failures.

## Excluded Files

### `tests/test_rollout_classifier_extended.py`
- **Reason**: ImportError - `cannot import name '_check_deployment_progress_deadline' from 'scripts.k9b_cnpg_live_lab_bootstrap'`
- **Status**: Broken import (missing symbol)
- **Discovered**: 2026-06-27

### `tests/unit/test_property_checks.py`
- **Reason**: ModuleNotFoundError - `No module named 'hypothesis'`
- **Status**: Missing optional dependency
- **Discovered**: 2026-06-27

## Expected Test Count

When collection works correctly:
- Full collection (no ignore): ~7795 tests (includes the above files but they fail to import)
- Sharded collection (with ignore): 7793 tests (excluding broken files)
- Difference: 2 tests (these files contribute 0 tests due to import errors)

## Verification

Run the exclusion verification:
```bash
python scripts/verify_test_exclusions.py
```

This script compares:
1. Full pytest collection (with errors) - expected ~7795 lines
2. Sharded collection (ignores broken files) - expected 7793 nodeids
3. Fails if non-allowlisted files are missing from sharded collection
