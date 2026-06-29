#!/usr/bin/env python3
"""Constants for K8s incident discovery verification.

This module contains configuration constants for the P3c detection phase:
- Polling timeouts and intervals
- Accepted candidate classes
- Pattern matching rules
- Backend API configuration
"""

from __future__ import annotations

# =============================================================================
# Constants for detection
# =============================================================================

# Polling configuration
DEFAULT_DETECTION_TIMEOUT_SECONDS = 120
DEFAULT_DETECTION_POLL_INTERVAL_SECONDS = 10
DEFAULT_MAX_DETECTION_ATTEMPTS = 12

# Backend configuration
DEFAULT_BACKEND_PORT = 8080

# Accepted candidate classes for K8s-native incident
ACCEPTED_CANDIDATE_CLASSES = frozenset([
    "pending_pod",
    "deployment_unavailable",
    "warning_event_burst",
])

# Evidence matching patterns - must match shipping specifically
SHIPPING_MATCH_PATTERNS = [
    "shipping",  # Deployment name or evidence mention
]

# FailedScheduling patterns - require shipping context
FAILED_SCHEDULING_PATTERNS = [
    "FailedScheduling",
    "Unschedulable",
]
