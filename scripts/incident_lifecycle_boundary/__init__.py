"""Incident lifecycle boundary verifier package.

This package verifies that the incident lifecycle domain module maintains proper
boundaries and does not leak IO, Kubernetes, HTTP, subprocess, or store dependencies.

Modules:
- common: Shared path constants and file reading helpers
- forbidden_imports: Checks for forbidden module imports
- rejection_reasons: Type alias and Literal extraction checks
- status_projection: Status assignment boundary checks
- transition_adapter_calls: Lifecycle core call verification
- cli: Main entrypoint and orchestration
"""

from __future__ import annotations

__all__ = []
