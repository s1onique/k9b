#!/usr/bin/env python3
"""Wrapper script for SEAM01 promotion-diagnosis handoff verifier.

This script delegates to the actual verifier implementation at:
    scripts/verifiers/promotion_diagnosis_handoff.py

Exit codes:
  0 -- no violations found
  1 -- violations found
  2 -- verification infrastructure failure

Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01
"""

import sys
from pathlib import Path

# Handle imports for both script and module execution
_verifiers_dir = Path(__file__).parent / "verifiers"
if str(_verifiers_dir) not in sys.path:
    sys.path.insert(0, str(_verifiers_dir))

from promotion_diagnosis_handoff import main

if __name__ == "__main__":
    sys.exit(main())
