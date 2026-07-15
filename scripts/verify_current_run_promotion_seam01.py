#!/usr/bin/env python3
"""Wrapper script for the ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01 verifier.

This is a thin wrapper that delegates to the actual verifier at
``scripts/verifiers/current_run_promotion_seam01.py``. Exit codes
mirror the underlying verifier.

Suggested by: ACT-K9B-HULK-CURRENT-RUN-PROMOTION-SEAM01
"""

import sys
from pathlib import Path

_verifiers_dir = Path(__file__).parent / "verifiers"
if str(_verifiers_dir) not in sys.path:
    sys.path.insert(0, str(_verifiers_dir))

from current_run_promotion_seam01 import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
