#!/usr/bin/env python3
"""Boundary verifier for incident lifecycle domain module.

This script checks that the incident lifecycle domain module maintains proper
boundaries and does not leak IO, Kubernetes, HTTP, subprocess, or store dependencies.

Checks performed:
1. incident_lifecycle.py does not import forbidden modules (including dotted imports).
2. Transition reason strings remain in an allowlist (domain module only).
3. Direct status assignments outside allowlisted files are detected (repo-wide).
4. Domain module remains pure (no IO dependencies).
5. Store modules reference typed lifecycle core functions.

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
    2 - Script error (e.g., file not found)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from incident_lifecycle_boundary.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
