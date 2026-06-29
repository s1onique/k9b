#!/usr/bin/env python3
"""Types and constants for K8s incident injection.

This module contains the dataclass result types and configuration
constants for the P2b injection phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# =============================================================================
# Constants for K8s-native incident injection
# =============================================================================

# Polling configuration
DEFAULT_POLL_INTERVAL_SECONDS = 10
DEFAULT_MAX_POLL_ATTEMPTS = 30
DEFAULT_TIMEOUT_SECONDS = 300


# =============================================================================
# Injection result dataclass
# =============================================================================

@dataclass
class K8sInjectionResult:
    """Result of Kubernetes-native incident injection."""
    
    success: bool
    scenario: str
    method: str
    deployment: str
    previous_template: dict[str, Any] | None
    evidence: dict[str, Any]
    error: str | None = None
