"""Constants for automatic diagnosis loop.

This module provides constants used across the automatic diagnosis loop system:
- Environment variable names
- Scheduler deployment constants
- Status constants for eligibility model

Architecture note:
    The automatic diagnosis loop is a SCHEDULER feature, not a backend feature.
"""

from __future__ import annotations

# Environment variable for enabling automatic diagnosis loop
_AUTOMATIC_LOOP_ENV_VAR = "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED"

# Environment variable for k9b control-plane namespace
_K9B_NAMESPACE_ENV_VAR = "K9B_NAMESPACE"

# Scheduler deployment constants
_SCHEDULER_DEPLOYMENT = "k9b-scheduler"
_SCHEDULER_CONTAINER = "scheduler"

# Default k9b namespace
DEFAULT_K9B_NAMESPACE = "k9b"
