#!/usr/bin/env python3
"""Shared fixtures for backend health gate dependency tests.

This module contains helper methods used across multiple test modules
for creating mock backend diagnostics, scheduler diagnostics, and
provider status data.
"""

import pytest


def _make_backend_diags(phase: str = "Running", containers: list = None) -> dict:
    """Create mock backend diagnostics.
    
    Args:
        phase: Kubernetes pod phase (e.g., "Running", "Pending", "Failed")
        containers: List of container states. Defaults to single running container.
    
    Returns:
        dict: Mock backend diagnostics structure
    """
    if containers is None:
        containers = [
            {"name": "backend", "state": "running", "reason": "", "message": "", "exit_code": None}
        ]
    return {
        "pod_k9b-backend-abc123": {
            "name": "k9b-backend-abc123",
            "phase": phase,
            "restart_count": 0,
            "containers": containers,
        }
    }


def _make_scheduler_diags(phase: str = "Running", containers: list = None) -> dict:
    """Create mock scheduler diagnostics.
    
    Args:
        phase: Kubernetes pod phase (e.g., "Running", "Pending", "Failed")
        containers: List of container states. Defaults to single running container.
    
    Returns:
        dict: Mock scheduler diagnostics structure
    """
    if containers is None:
        containers = [
            {"name": "scheduler", "state": "running", "reason": "", "message": "", "exit_code": None}
        ]
    return {
        "pod_k9b-scheduler-xyz789": {
            "name": "k9b-scheduler-xyz789",
            "phase": phase,
            "restart_count": 0,
            "containers": containers,
        }
    }


def _make_provider_status(enabled: bool = False, secret_ref: bool = False) -> dict:
    """Create mock provider status.
    
    Args:
        enabled: Whether diagnosis provider is enabled
        secret_ref: Whether secret reference is present
    
    Returns:
        dict: Mock provider status structure
    """
    return {
        "diagnosis_provider_enabled": enabled,
        "diagnosis_provider_secret_ref_present": secret_ref,
        "small_provider_secret_ref_present": False,
        "base_url_present": False,
        "model_present": False,
        "api_key_present": secret_ref,
    }
