#!/usr/bin/env python
"""Thin shim for documentation claim candidate backlog reporter.

This module delegates to the report_docs_claim_candidate_backlog package.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent directory to path for package imports
sys.path.insert(0, str(Path(__file__).parent))

from report_docs_claim_candidate_backlog.__main__ import main

if __name__ == "__main__":
    sys.exit(main())