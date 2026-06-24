"""Constants and patterns for golden-case providers.

This module contains shared constants used across golden-case providers.
"""

from __future__ import annotations

import re

__all__ = [
    "_FORBIDDEN_PRIMARY_CAUSE_PATTERNS",
    "_READINESS_PROBE_PATTERNS",
]


# Forbidden diagnosis keywords (readiness case should NOT cite these)
_FORBIDDEN_PRIMARY_CAUSE_PATTERNS = [
    re.compile(r"\bImagePullBackOff\b", re.IGNORECASE),
    re.compile(r"\bErrImagePull\b", re.IGNORECASE),
    re.compile(r"\bPVC\b", re.IGNORECASE),
    re.compile(r"\bPersistentVolumeClaim\b", re.IGNORECASE),
    re.compile(r"\bpv-claim\b", re.IGNORECASE),
    re.compile(r"\bFailedScheduling\b", re.IGNORECASE),
    re.compile(r"\bregistry.*auth\b", re.IGNORECASE),
    re.compile(r"\bcnpg.*operator.*fail\b", re.IGNORECASE),
]

# Readiness probe success patterns
_READINESS_PROBE_PATTERNS = [
    re.compile(r"readiness\s+probe\s+failed", re.IGNORECASE),
    re.compile(r"readiness\s+probe\s+failing", re.IGNORECASE),
    re.compile(r"Unhealthy", re.IGNORECASE),
    re.compile(r"NotReady", re.IGNORECASE),
    re.compile(r"Ready\s*:\s*False", re.IGNORECASE),
    re.compile(r"0/1.*Running", re.IGNORECASE),
    re.compile(r"probe.*exit\s+code\s+1", re.IGNORECASE),
    re.compile(r"/bin/false", re.IGNORECASE),
]
